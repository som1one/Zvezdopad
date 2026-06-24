# Содержимое файла: handlers/common.py (С таймаутом и обработкой ошибок SubGram)
import logging
import time
import aiohttp  # Убедись, что импортирован
import asyncio  # Убедись, что импортирован
import json  # Добавлен для обработки ошибок JSON
from datetime import datetime, timedelta, timezone
from html import escape
from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID, TelegramAPIError

import database
from settings import ADMIN_IDS, REQUEST_API_KEY, REQUEST_OP_DELAY_HOURS, REQUEST_OP_DELAY_MINUTES
from utils import t, get_sponsors

log = logging.getLogger('handlers.common')


# --- ИЗМЕНЕННАЯ ФУНКЦИЯ request_op ---
async def request_op(user_id: int, chat_id: int, bot_instance: Bot, gender=None, age=None) -> bool | str:
    """
    Делает запрос к SubGram API для проверки обязательной подписки.
    Возвращает:
        - False: Если нужно показать пользователю кнопки для подписки.
        - "ok": Если проверка пройдена, не требуется или произошла ошибка API (чтобы не блокировать).
    """
    log.debug(f"User {user_id}: Starting OP request...")
    registration_time_dt = await database.get_user_registration_time(user_id)
    if not registration_time_dt:
        log.warning(f"User {user_id}: No registration time found, skipping OP request.")
        return "ok"  # Считаем пройденным, если нет времени регистрации

    current_time_utc = datetime.now(timezone.utc)
    delay_seconds = (REQUEST_OP_DELAY_HOURS * 3600) + (REQUEST_OP_DELAY_MINUTES * 60)

    # Убедимся, что время регистрации имеет таймзону для сравнения
    if registration_time_dt.tzinfo is None:
        # Предполагаем UTC, если таймзона отсутствует (как было в SQLite)
        registration_time_dt = registration_time_dt.replace(tzinfo=timezone.utc)

    if (current_time_utc - registration_time_dt).total_seconds() < delay_seconds:
        log.debug(f"User {user_id}: Skipping OP request, delay not passed.")
        return "ok"  # Проверка еще не нужна

    if not REQUEST_API_KEY or "YOUR" in REQUEST_API_KEY:
        log.warning("SubGram API key not configured. Skipping OP check, returning 'ok'.")
        return "ok"  # Пропускаем проверку, если ключ не задан

    headers = {'Content-Type': 'application/json', 'Auth': REQUEST_API_KEY, 'Accept': 'application/json'}
    data = {'UserId': user_id, 'ChatId': chat_id}
    if gender: data['Gender'] = gender
    if age: data['Age'] = age

    url = 'https://api.subgram.ru/request-op/'
    log.debug(f"User {user_id}: Sending OP request to {url} with data: {data}")

    # --- УСТАНОВКА ТАЙМАУТА ---
    timeout = aiohttp.ClientTimeout(total=5)  # Общий таймаут 5 секунд
    # -----------------------

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:  # <--- Передаем таймаут
            async with session.post(url, headers=headers, json=data) as response:
                response_text = await response.text()
                log.debug(f"User {user_id}: SubGram API response status={response.status}")

                # --- ОБРАБОТКА ОШИБОК 5xx и других HTTP ошибок ---
                if not response.ok:
                    # Логируем 5xx/4xx как WARNING, но ВОЗВРАЩАЕМ "ok", чтобы не блокировать
                    log.warning(
                        f'SubGram API request failed user {user_id}: Status {response.status}, Response: {response_text[:300]}...')
                    return "ok"
                # -----------------------------------

                try:
                    # Используем response.json(content_type=None), чтобы обработать любой content_type
                    response_json = await response.json(content_type=None)
                    if not isinstance(response_json, dict):  # Проверка, что получили словарь
                        raise ValueError("Response is not a JSON object")
                except (aiohttp.ContentTypeError, json.JSONDecodeError, ValueError) as json_err:
                    # Если ответ не JSON, логируем и возвращаем "ok"
                    log.warning(
                        f"SubGram API returned non-JSON/invalid JSON user {user_id}: {json_err}. Response: {response_text[:300]}...")
                    return "ok"

                status = response_json.get("status")
                message_api = response_json.get("message", "")  # Переименовали переменную, чтобы не конфликтовать
                log.info(f"User {user_id}: SubGram API result: status={status}, message='{message_api}'")

                if status == 'warning':
                    links = response_json.get("links", [])
                    if not links:
                        log.warning(f"User {user_id}: SubGram API 'warning' but no links.")
                        return "ok"  # Считаем пройденным, если ссылок нет

                    markup = InlineKeyboardMarkup(row_width=2)
                    unique_links_dict = {link: None for link in links}  # Сохраняем порядок уникальных ссылок
                    buttons = [InlineKeyboardButton(f'Спонсор №{idx}', url=url) for idx, url in
                               enumerate(unique_links_dict.keys(), start=1)]
                    markup.add(*buttons)
                    check_button = InlineKeyboardButton(t(user_id, 'check_subscribe'), callback_data='check_subs')
                    markup.add(check_button)
                    subscribe_text = t(user_id, 'start_subscribe')
                    image_path = "images/check.jpg"

                    try:
                        photo_input = types.InputFile(image_path)
                        await bot_instance.send_photo(user_id, photo=photo_input, caption=subscribe_text,
                                                      reply_markup=markup, parse_mode="HTML")
                        log.info(f"User {user_id}: Subscription request sent via SubGram.")
                        return False  # Нужна подписка
                    except FileNotFoundError:
                        log.error(f"Image file not found: {image_path}. Sending text for sub request user {user_id}.")
                        await bot_instance.send_message(user_id, subscribe_text, reply_markup=markup, parse_mode="HTML")
                        return False  # Нужна подписка
                    except Exception as send_err:
                        log.exception(f"Failed send subscription message user {user_id}: {send_err}")
                        return "ok"  # Считаем пройденным при ошибке отправки

                elif status == 'ok':
                    log.info(f"User {user_id}: Passed SubGram OP check.")
                    return "ok"
                else:
                    log.warning(f"Unknown status '{status}' SubGram API user {user_id}. Returning 'ok'.")
                    return "ok"

    # --- ОБРАБОТКА ТАЙМАУТА и Ошибок Соединения ---
    except asyncio.TimeoutError:
        log.error(f"SubGram API timeout for user {user_id}. Returning 'ok'.")
        return "ok"  # Считаем пройденным при таймауте
    except aiohttp.ClientConnectorError as e:
        log.error(f"SubGram connection error user {user_id}: {e}. Returning 'ok'.")
        return "ok"  # Считаем пройденным при ошибке соединения
    # ------------------------------------------
    except Exception as e:
        log.exception(f"Unexpected error SubGram OP request user {user_id}: {e}. Returning 'ok'.")
        return "ok"  # Считаем пройденным при любой другой ошибке


# --- КОНЕЦ ИЗМЕНЕННОЙ ФУНКЦИИ ---


async def check_subscription(bot: Bot, user_id: int, chat_id: int) -> bool:
    """
    Проверяет подписку пользователя на обязательные каналы И через SubGram OP/спонсоры.
    Возвращает True, если все подписки есть, иначе False и отправляет сообщение с кнопками.
    """
    if user_id in ADMIN_IDS:
        log.debug(f"User {user_id} is admin, skipping subscription check.")
        return True

    # --- SubGram get-sponsors (новый API) ---
    sponsors = await get_sponsors(user_id, chat_id)
    if sponsors:
        markup = InlineKeyboardMarkup(row_width=1)
        has_unsubscribed = False

        for idx, sponsor in enumerate(sponsors, start=1):
            if isinstance(sponsor, dict):
                sponsor_url = sponsor.get("url") or sponsor.get("link") or sponsor.get("invite_link") or ""
                sponsor_name = sponsor.get("name") or sponsor.get("title") or f"Спонсор №{idx}"
                channel_id_sp = sponsor.get("channel_id") or sponsor.get("chat_id")

                if channel_id_sp:
                    try:
                        chat_member = await bot.get_chat_member(int(channel_id_sp), user_id)
                        if chat_member.status in ['member', 'administrator', 'creator']:
                            continue
                    except Exception as e:
                        log.debug(f"Cannot check membership for sponsor channel {channel_id_sp}: {e}")

                if sponsor_url:
                    markup.add(InlineKeyboardButton(sponsor_name, url=sponsor_url))
                    has_unsubscribed = True
            elif isinstance(sponsor, str):
                markup.add(InlineKeyboardButton(f"Спонсор №{idx}", url=sponsor))
                has_unsubscribed = True

        if has_unsubscribed:
            check_button = InlineKeyboardButton(t(user_id, 'check_subscribe'), callback_data='check_subs')
            markup.add(check_button)
            subscribe_text = t(user_id, 'start_subscribe')
            image_path = "images/check.jpg"
            try:
                photo_input = types.InputFile(image_path)
                await bot.send_photo(user_id, photo=photo_input, caption=subscribe_text,
                                     reply_markup=markup, parse_mode="HTML")
                log.info(f"SubGram get-sponsors: sent to user {user_id}.")
                return False
            except FileNotFoundError:
                await bot.send_message(user_id, subscribe_text, reply_markup=markup, parse_mode="HTML")
                return False
            except Exception as e:
                log.exception(f"Failed to send sponsors message to user {user_id}: {e}")

    # --- СНАЧАЛА ПРОВЕРКА SubGram OP ---
    start_op_check = time.monotonic()
    op_status = await request_op(user_id, chat_id, bot)
    duration_op_check = time.monotonic() - start_op_check
    log.info(f"User {user_id}: SubGram OP check result: {op_status}. Duration: {duration_op_check:.3f}s")

    if op_status is False:
        # Сообщение с кнопками подписки уже отправлено из request_op
        log.info(f"User {user_id} needs to subscribe via SubGram. Check failed.")
        return False
    elif op_status != "ok":
        # Если была ошибка SubGram (не False), то пока пропускаем пользователя
        log.warning(f"User {user_id}: SubGram OP check returned status: {op_status}. Allowing user for now.")
        pass  # Не делаем return True сразу, проверим каналы БД ниже
    # Если op_status == "ok", продолжаем проверку каналов из БД
    # --- КОНЕЦ ПРОВЕРКИ SubGram OP ---

    log.debug(f"User {user_id}: Checking DB channel subscriptions...")  # Лог
    start_db_check = time.monotonic()

    channel_ids = await database.get_channels_db()
    sponsor_buttons_data = await database.get_sponsor_buttons()

    if not channel_ids and not sponsor_buttons_data:
        log.debug(f"No mandatory channels or sponsor buttons configured, skipping DB check for user {user_id}.")
        await database.mark_onboarding_completed(user_id)
        return True  # Проверять нечего

    markup = InlineKeyboardMarkup(row_width=1)
    missing_subscriptions = False
    channels_list_text = ""
    channels_checked_count = 0

    # --- ПРОВЕРКА КАНАЛОВ ИЗ БД ---
    tasks = []
    valid_channel_ids = []  # Сохраняем ID каналов, для которых будем получать информацию

    # Шаг 1: Проверяем членство асинхронно
    for channel_id_int in channel_ids:
        async def check_membership(cid):
            try:
                chat_member = await bot.get_chat_member(cid, user_id)
                if chat_member.status not in ['member', 'administrator', 'creator']:
                    return cid, False  # Пользователь не подписан
                else:
                    return cid, True  # Пользователь подписан
            except Exception as e:
                log.error(f"Error checking subscription for user {user_id} on channel {cid}: {e}")
                return cid, None  # Ошибка проверки

        tasks.append(check_membership(channel_id_int))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    log.debug(f"User {user_id}: DB Channel membership check results: {results}")

    missing_channel_ids = []
    for result in results:
        if isinstance(result, Exception):
            log.error(f"User {user_id}: Exception during gather membership check: {result}")
            continue  # Пропускаем канал с ошибкой проверки членства
        channel_id, is_member = result
        if is_member is False:
            missing_subscriptions = True
            missing_channel_ids.append(channel_id)
        # Если is_member is None (ошибка), пока считаем, что подписка есть (не блокируем)

    # Шаг 2: Получаем информацию только для каналов, на которые НУЖНО подписаться
    if missing_channel_ids:
        info_tasks = []
        for channel_id_int in missing_channel_ids:
            async def get_channel_info(cid):
                try:
                    chat = await bot.get_chat(cid)
                    title = chat.title or f"Канал ID {cid}"
                    invite_link = chat.invite_link
                    if not invite_link:  # Пытаемся создать временную, если нет основной
                        invite_link_obj = await bot.create_chat_invite_link(cid, member_limit=1)
                        invite_link = invite_link_obj.invite_link
                    return cid, title, invite_link
                except Exception as e_inner:
                    log.error(
                        f"Failed get info or create link for channel {cid}: {e_inner}. Skipping btn user {user_id}.")
                    return cid, None, None

            info_tasks.append(get_channel_info(channel_id_int))

        info_results = await asyncio.gather(*info_tasks, return_exceptions=True)
        log.debug(f"User {user_id}: DB Channel info results for missing subs: {info_results}")

        for result in info_results:
            if isinstance(result, Exception):
                log.error(f"User {user_id}: Exception during gather channel info: {result}")
                continue
            channel_id, title, link = result
            if title and link:
                subscribe_button = InlineKeyboardButton(title, url=link)
                markup.add(subscribe_button)
                channels_list_text += f"• <a href='{link}'>{escape(title)}</a>\n"
            else:
                log.warning(
                    f"User {user_id}: Could not get info/link for missing channel {channel_id}. Button skipped.")

    # --- КОНЕЦ ПРОВЕРКИ КАНАЛОВ ИЗ БД ---

    duration_db_check = time.monotonic() - start_db_check
    log.info(
        f"User {user_id}: DB Channel check finished. Missing subs: {missing_subscriptions}. Duration: {duration_db_check:.3f}s")

    # --- ДОБАВЛЕНИЕ СПОНСОРСКИХ КНОПОК (если есть) ---
    if sponsor_buttons_data:
        markup.row_width = 2  # Можно сделать 2 в ряд для спонсоров
        sponsor_buttons_list = []
        for button_record in sponsor_buttons_data:
            try:
                sponsor_buttons_list.append(InlineKeyboardButton(button_record['name'], url=button_record['url']))
            except Exception as btn_err:
                log.error(f"Error creating sponsor button {button_record}: {btn_err}")
        if sponsor_buttons_list:
            markup.add(*sponsor_buttons_list)
        markup.row_width = 1  # Возвращаем ширину по умолчанию
        missing_subscriptions = True  # Если есть спонсорские кнопки, всегда показываем кнопку "Проверить"

    # --- ОТПРАВКА СООБЩЕНИЯ, ЕСЛИ НУЖНА ПОДПИСКА ---
    if missing_subscriptions:
        check_button = InlineKeyboardButton(t(user_id, 'check_subscribe'), callback_data="check_subs")
        markup.add(check_button)
        subscribe_text = t(user_id, 'start_subscribe')
        if channels_list_text:
            subscribe_text += "\n" + channels_list_text.strip()
        elif sponsor_buttons_data and not channel_ids:  # Если только спонсоры
            subscribe_text = "💜 Пожалуйста, ознакомьтесь с ресурсами наших спонсоров:"

        image_path = "images/check.jpg"
        try:
            photo_input = types.InputFile(image_path)
            await bot.send_photo(user_id, photo=photo_input, caption=subscribe_text, reply_markup=markup,
                                 parse_mode="HTML")
            log.info(f"User {user_id}: Subscription request sent (DB channels/sponsors).")
            return False  # Нужна подписка
        except FileNotFoundError:
            log.error(f"Image file not found: {image_path}. Sending text message instead user {user_id}.")
            await bot.send_message(user_id, subscribe_text, reply_markup=markup, parse_mode="HTML")
            return False  # Нужна подписка
        except Exception as e:
            log.exception(f"Failed send subscription message user {user_id}: {e}")
            # Если не удалось отправить сообщение с требованием подписки,
            # временно считаем, что подписка есть, чтобы не блокировать пользователя
            await database.mark_onboarding_completed(user_id)
            return True

    # Если не было пропущено из-за SubGram и не найдено отсутствующих подписок на каналы БД
    log.info(f"User {user_id}: Passed all subscription checks (SubGram 'ok' or skipped, DB channels ok).")
    await database.mark_onboarding_completed(user_id)
    return True


async def handle_check_subscription_callback(callback_query: types.CallbackQuery, bot: Bot):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    log.info(f"User {user_id}: Received 'check_subs' callback.")  # Лог

    try:
        # Отвечаем на колбэк как можно быстрее
        await callback_query.answer("Проверяю подписки...")
    except InvalidQueryID:
        log.warning(f"IQID fail handle_check_subscription_callback user {user_id}"); return
    except Exception as e:
        log.error(f"Error answering cb handle_check_subscription_callback: {e}"); return

    # Запускаем проверку
    start_check = time.monotonic()
    subscribed = await check_subscription(bot, user_id, chat_id)
    duration_check = time.monotonic() - start_check
    log.info(
        f"User {user_id}: Result of 'check_subs' callback check: {subscribed}. Duration: {duration_check:.3f}s")  # Лог

    if subscribed:
        log.info(f"User {user_id}: Confirmed subscription via callback.")
        # Удаляем сообщение с кнопками подписки
        try:
            await callback_query.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        except Exception as del_err:
            log.warning(f"Error deleting sub prompt message user {user_id}: {del_err}")

        await bot.send_message(user_id, t(user_id, 'subscribed_successfully'))

        # Показываем главное меню (импортируем здесь, чтобы избежать циклического импорта)
        from handlers.user_menu import show_main_menu
        await show_main_menu(callback_query.message, user_id, bot, edit=False)  # Отправляем новое меню

        # Проверяем и награждаем реферера (импортируем здесь)
        from handlers.user_commands import award_referral
        await award_referral(user_id, bot)
    else:
        log.info(f"User {user_id}: Failed subscription check via callback.")
        # Сообщение с кнопками подписки уже должно было быть отправлено из check_subscription
        # Можно дополнительно отправить короткое сообщение
        await bot.send_message(user_id, t(user_id, 'not_subscribed'))  # Или 'still_not_subscribed'


async def hide_message_callback(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    log.debug(f"User {user_id}: Received hide message callback: {call.data}")  # Лог
    try:
        await call.message.delete()
        try:
            await call.answer()  # Отвечаем тихо, без текста
        except InvalidQueryID:
            log.warning(f"IQID fail hide_message_callback (after delete) user {user_id}")
        except Exception as e_ans:
            log.error(f"Error answering hide_message cb: {e_ans}")
        log.debug(f"Message {call.message.message_id} hidden by user {user_id}")
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        log.debug(f"Message {call.message.message_id} already deleted for user {user_id}.")
        try:
            await call.answer()  # Все равно отвечаем на колбэк
        except InvalidQueryID:
            log.warning(f"IQID fail hide_message_callback (already deleted) user {user_id}")
        except Exception as e_ans:
            log.error(f"Error answering hide_message (already deleted) cb: {e_ans}")
    except Exception as e:
        log.error(f"Error hiding message {call.message.message_id} for user {user_id}: {e}")
        try:
            await call.answer("Ошибка при скрытии сообщения.", show_alert=True)
        except InvalidQueryID:
            log.warning(f"IQID fail hide_message_callback (error) user {user_id}")
        except Exception as e_ans:
            log.error(f"Error answering hide_message (error) cb: {e_ans}")


def register_common_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(lambda call: handle_check_subscription_callback(call, bot),
                                       lambda c: c.data == "check_subs", state="*")
    dp.register_callback_query_handler(lambda call: hide_message_callback(call, bot),
                                       lambda c: c.data.startswith("hide_message_") or c.data == "hide_preview",
                                       state="*")
    log.info("Common handlers registered.")
