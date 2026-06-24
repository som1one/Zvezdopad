import logging
import aiohttp

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID, TelegramAPIError


# Импортируем нужные функции и переменные
from database import get_channels_db, get_sponsor_buttons, get_user_lang
from settings import ADMIN_IDS, REQUEST_API_KEY, REQUEST_OP_DELAY_HOURS, REQUEST_OP_DELAY_MINUTES
from utils import t, format_datetime, get_sponsors
from database import get_user_registration_time, mark_onboarding_completed
from datetime import datetime, timedelta

log = logging.getLogger('handlers.common')


async def request_op(user_id, chat_id, bot_instance: Bot, gender=None, age=None):
    """Отправляет запрос на проверку ОП в SubGram API."""
    registration_time_str = get_user_registration_time(user_id)
    if not registration_time_str:
        log.warning(f"No registration time found for user {user_id}, skipping OP request.")
        return "ok"

    try:
        registration_time = datetime.strptime(registration_time_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        log.error(f"Could not parse registration time '{registration_time_str}' for user {user_id}.")
        return "ok"

    current_time = datetime.now()
    delay_seconds = (REQUEST_OP_DELAY_HOURS * 3600) + (REQUEST_OP_DELAY_MINUTES * 60)

    if (current_time - registration_time).total_seconds() < delay_seconds:
        log.info(f"Skipping OP request for user {user_id}, delay not passed.")
        return "ok"

    headers = {
        'Content-Type': 'application/json',
        'Auth': REQUEST_API_KEY,
        'Accept': 'application/json',
    }
    data = {'UserId': user_id, 'ChatId': chat_id}
    if gender: data['Gender'] = gender
    if age: data['Age'] = age

    url = 'https://api.subgram.ru/request-op/'
    log.info(f"Sending OP request for user {user_id} to {url} with data: {data}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                response_text = await response.text()
                log.debug(f"SubGram API response for {user_id}: Status={response.status}, Body={response_text}")

                if not response.ok:
                    log.error(
                        f'SubGram API request failed for {user_id}: Status {response.status}, Response: {response_text}')
                    return "ok"

                try:
                    response_json = await response.json()
                except aiohttp.ContentTypeError:
                    log.error(f"SubGram API returned non-JSON response for {user_id}: {response_text}")
                    return "ok"

                status = response_json.get("status")
                message = response_json.get("message", "")
                log.info(f"SubGram API result for {user_id}: status={status}, message='{message}'")

                if status == 'warning':
                    links = response_json.get("links", [])
                    if not links:
                        log.warning(f"SubGram API returned 'warning' for {user_id} but no links provided.")
                        return "ok"

                    markup = InlineKeyboardMarkup(row_width=2)
                    unique_links = list(set(links))
                    buttons = [InlineKeyboardButton(f'Спонсор №{idx}', url=url) for idx, url in
                               enumerate(unique_links, start=1)]
                    markup.add(*buttons)
                    check_button = InlineKeyboardButton(t(user_id, 'check_subscribe'), callback_data='check_subs')
                    markup.add(check_button)
                    subscribe_text = t(user_id, 'start_subscribe')
                    image_path = "images/check.jpg"

                    try:
                        with open(image_path, "rb") as photo:
                            await bot_instance.send_photo(user_id, photo=photo, caption=subscribe_text,
                                                          reply_markup=markup)
                        log.info(f"Subscription request sent to user {user_id} via SubGram.")
                        return False
                    except FileNotFoundError:
                        log.error(f"Image file not found: {image_path}. Sending text message instead.")
                        await bot_instance.send_message(user_id, subscribe_text, reply_markup=markup)
                        return False
                    except Exception as e:
                        log.exception(f"Failed to send subscription message to user {user_id}: {e}")
                        return "ok"

                elif status == 'ok':
                    log.info(f"User {user_id} passed SubGram OP check.")
                    return "ok"
                else:
                    log.warning(f"Unknown status '{status}' received from SubGram API for user {user_id}.")
                    return "ok"

    except aiohttp.ClientConnectorError as e:
        log.error(f"SubGram API connection error for user {user_id}: {e}")
        return "ok"
    except Exception as e:
        log.exception(f"Unexpected error during SubGram OP request for user {user_id}: {e}")
        return "ok"


async def check_subscription(bot: Bot, user_id: int, chat_id: int):
    """Проверяет подписку пользователя на обязательные каналы и SubGram OP/спонсоры."""
    if user_id in ADMIN_IDS:
        log.debug(f"User {user_id} is admin, skipping subscription check.")
        return True

    # --- SubGram get-sponsors (новый API) ---
    sponsors = await get_sponsors(user_id, chat_id)
    if sponsors:
        # Если get-sponsors вернул список каналов для подписки — показываем их
        markup = InlineKeyboardMarkup(row_width=1)
        has_unsubscribed = False

        for idx, sponsor in enumerate(sponsors, start=1):
            # Формат спонсора может быть разным: dict с url/name/title или просто строка-ссылка
            if isinstance(sponsor, dict):
                sponsor_url = sponsor.get("url") or sponsor.get("link") or sponsor.get("invite_link") or ""
                sponsor_name = sponsor.get("name") or sponsor.get("title") or f"Спонсор №{idx}"
                channel_id = sponsor.get("channel_id") or sponsor.get("chat_id")

                # Если есть channel_id — проверяем подписку
                if channel_id:
                    try:
                        chat_member = await bot.get_chat_member(int(channel_id), user_id)
                        if chat_member.status in ['member', 'administrator', 'creator']:
                            continue  # Уже подписан, пропускаем
                    except Exception as e:
                        log.debug(f"Cannot check membership for sponsor channel {channel_id}: {e}")

                if sponsor_url:
                    markup.add(InlineKeyboardButton(sponsor_name, url=sponsor_url))
                    has_unsubscribed = True
            elif isinstance(sponsor, str):
                # Просто URL
                markup.add(InlineKeyboardButton(f"Спонсор №{idx}", url=sponsor))
                has_unsubscribed = True

        if has_unsubscribed:
            check_button = InlineKeyboardButton(t(user_id, 'check_subscribe'), callback_data='check_subs')
            markup.add(check_button)
            subscribe_text = t(user_id, 'start_subscribe')
            image_path = "images/check.jpg"

            try:
                with open(image_path, "rb") as photo:
                    await bot.send_photo(user_id, photo=photo, caption=subscribe_text,
                                         reply_markup=markup, parse_mode="HTML")
                log.info(f"SubGram get-sponsors: subscription request sent to user {user_id}.")
                return False
            except FileNotFoundError:
                log.error(f"Image file not found: {image_path}. Sending text message instead.")
                await bot.send_message(user_id, subscribe_text, reply_markup=markup, parse_mode="HTML")
                return False
            except Exception as e:
                log.exception(f"Failed to send sponsors message to user {user_id}: {e}")
                # Продолжаем проверку через request_op как fallback

    # --- SubGram request-op (старый API, fallback) ---
    op_status = await request_op(user_id, chat_id, bot)
    if op_status == False:
        log.info(f"User {user_id} needs to subscribe via SubGram. Check failed.")
        return False
    elif op_status != "ok":
        log.warning(f"SubGram OP check for user {user_id} returned status: {op_status}. Proceeding.")

    channel_ids = get_channels_db()
    sponsor_buttons_data = get_sponsor_buttons()

    if not channel_ids and not sponsor_buttons_data:
        log.debug(f"No mandatory channels or sponsor buttons configured, skipping check for user {user_id}.")
        return True

    markup = InlineKeyboardMarkup(row_width=1)
    missing_subscriptions = False
    channels_list_text = ""

    for channel_id_int in channel_ids:
        try:
            log.debug(f"Checking subscription for user {user_id} to channel {channel_id_int}...")
            chat_member = await bot.get_chat_member(channel_id_int, user_id)
            if chat_member.status not in ['member', 'administrator', 'creator']:
                missing_subscriptions = True
                try:
                    chat = await bot.get_chat(channel_id_int)
                    invite_link = await bot.create_chat_invite_link(channel_id_int, member_limit=1)
                    subscribe_button = InlineKeyboardButton(chat.title, url=invite_link.invite_link)
                    markup.add(subscribe_button)
                    channels_list_text += f"• <a href='{invite_link.invite_link}'>{chat.title}</a>\n"
                    log.info(f"User {user_id} is NOT subscribed to mandatory channel {channel_id_int} ({chat.title}).")
                except Exception as e_inner:
                    log.error(
                        f"Failed to get info or create link for channel {channel_id_int}: {e_inner}. Skipping this channel for user {user_id}.")
            else:
                log.debug(f"User {user_id} IS subscribed to mandatory channel {channel_id_int}.")
        except Exception as e:
            log.error(f"Error checking subscription for user {user_id} on channel {channel_id_int}: {e}")

    if sponsor_buttons_data:
        markup.row_width = 2
        sponsor_buttons_list = []
        for name, url in sponsor_buttons_data:
            sponsor_buttons_list.append(InlineKeyboardButton(name, url=url))
        markup.add(*sponsor_buttons_list)
        markup.row_width = 1

    if missing_subscriptions or sponsor_buttons_data:
        check_button = InlineKeyboardButton(t(user_id, 'check_subscribe'), callback_data="check_subs")
        markup.add(check_button)
        subscribe_text = t(user_id, 'start_subscribe')
        if channels_list_text:
            subscribe_text += "\n" + channels_list_text.strip()
        elif sponsor_buttons_data:
            subscribe_text = "💜 Пожалуйста, ознакомьтесь с ресурсами наших спонсоров:"

        image_path = "images/check.jpg"
        try:
            with open(image_path, "rb") as photo:
                await bot.send_photo(user_id, photo=photo, caption=subscribe_text, reply_markup=markup,
                                     parse_mode="HTML")
            log.info(f"Subscription request sent to user {user_id} (DB channels/sponsors).")
            return False
        except FileNotFoundError:
            log.error(f"Image file not found: {image_path}. Sending text message instead.")
            await bot.send_message(user_id, subscribe_text, reply_markup=markup, parse_mode="HTML")
            return False
        except Exception as e:
            log.exception(f"Failed to send subscription message to user {user_id}: {e}")
            return True

    log.info(f"User {user_id} passed all subscription checks.")
    await mark_onboarding_completed(user_id)
    return True


async def handle_check_subscription_callback(callback_query: types.CallbackQuery, bot: Bot):
    """Обрабатывает нажатие кнопки 'Проверить подписки'."""
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    # --- ИЗМЕНЕНИЕ: Обработка InvalidQueryID ---
    try:
        await callback_query.answer()  # Отвечаем на колбэк, чтобы убрать "часики"
    except InvalidQueryID:
        log.warning(f"InvalidQueryID caught for user {user_id} in {callback_query.data} (check_subs).")
        # Прерываем, так как дальнейшая проверка бессмысленна без ответа
        return
    except Exception as e:
        log.error(f"Error answering callback query for user {user_id} in {callback_query.data} (check_subs): {e}")
        return
    # ---------------------------------------

    # Повторно проверяем подписку
    subscribed = await check_subscription(bot, user_id, chat_id)

    if subscribed:
        log.info(f"User {user_id} confirmed subscription via callback.")
        # await callback_query.answer(t(user_id, 'subscribed_successfully'), show_alert=True) # Ответ уже был
        await bot.send_message(user_id, t(user_id, 'subscribed_successfully'))  # Уведомляем в чат
        try:
            await callback_query.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        from handlers.user_menu import show_main_menu
        await show_main_menu(callback_query.message, user_id, bot, edit=False)
        from handlers.user_commands import award_referral
        await award_referral(user_id, bot)
    else:
        log.info(f"User {user_id} failed subscription check via callback.")
        # await callback_query.answer(t(user_id, 'not_subscribed'), show_alert=True) # Ответ уже был
        await bot.send_message(user_id, t(user_id, 'not_subscribed'))  # Уведомляем в чат


async def hide_message_callback(call: CallbackQuery, bot: Bot):
    """Обрабатывает колбэк для скрытия сообщения."""
    user_id = call.from_user.id  # Получаем ID для логов
    try:
        await call.message.delete()
        # --- ИЗМЕНЕНИЕ: Обработка InvalidQueryID ---
        try:
            await call.answer("Сообщение скрыто.", show_alert=False)
        except InvalidQueryID:
            log.warning(f"InvalidQueryID caught for user {user_id} in {call.data} (hide_message) after delete.")
        except Exception as e_ans:
            log.error(f"Error answering hide_message callback for user {user_id}: {e_ans}")
        # ---------------------------------------
        log.debug(f"Message {call.message.message_id} hidden by user {user_id}")
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        # --- ИЗМЕНЕНИЕ: Обработка InvalidQueryID ---
        try:
            await call.answer("Не удалось скрыть (уже удалено?).", show_alert=False)
        except InvalidQueryID:
            log.warning(f"InvalidQueryID caught for user {user_id} in {call.data} (hide_message - already deleted).")
        except Exception as e_ans:
            log.error(f"Error answering hide_message (already deleted) callback for user {user_id}: {e_ans}")
        # ---------------------------------------
    except Exception as e:
        log.error(f"Error hiding message {call.message.message_id} for user {user_id}: {e}")
        # --- ИЗМЕНЕНИЕ: Обработка InvalidQueryID ---
        try:
            await call.answer("Ошибка при скрытии сообщения.", show_alert=True)
        except InvalidQueryID:
            log.warning(f"InvalidQueryID caught for user {user_id} in {call.data} (hide_message - error).")
        except Exception as e_ans:
            log.error(f"Error answering hide_message (error) callback for user {user_id}: {e_ans}")
        # ---------------------------------------


def register_common_handlers(dp: Dispatcher, bot: Bot):
    """Регистрирует общие обработчики."""
    dp.register_callback_query_handler(
        lambda call: handle_check_subscription_callback(call, bot),
        lambda c: c.data == "check_subs",
        state="*"
    )
    dp.register_callback_query_handler(
        lambda call: hide_message_callback(call, bot),
        lambda c: c.data.startswith("hide_message_") or c.data == "hide_preview",
        state="*"
    )
    log.info("Common handlers registered.")
