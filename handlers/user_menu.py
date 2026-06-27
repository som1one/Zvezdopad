import logging
from html import escape
import os
# Убедитесь, что все импорты aiogram соответствуют версии 2.x
from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputFile, InputMediaPhoto
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, MessageNotModified, \
    CantParseEntities, BadRequest, InvalidQueryID

# Ваши импорты
import database
import settings  # Ваш settings.py
from utils import t, get_user_info, sanitize_username, mask_id, mask_username, format_datetime  # Ваши утилиты
# Импортируем клавиатуры, включая новую для перенаправления и PAYMENT_BOT_USERNAME
from keyboards import (
    get_main_menu_markup,
    create_back_button,
    generate_pagination_buttons,
    get_redirect_to_payment_bot_keyboard  # Новая клавиатура
)
# Из settings или keyboards должен быть доступен PAYMENT_BOT_USERNAME
# Если он в settings:
# from settings import PAYMENT_BOT_USERNAME
# Если он в keyboards (как я предложил в предыдущем ответе):
from keyboards import PAYMENT_BOT_USERNAME

log = logging.getLogger('handlers.user_menu')


# --- Ваша функция _send_or_edit_photo_message ---
# Я оставлю ее как есть, предполагая, что она у вас работает для aiogram 2.x
# Важно, чтобы она корректно обрабатывала и message, и callback_query
async def _send_or_edit_photo_message(message_or_call, user_id: int,
                                      image_path, caption, markup, parse_mode="HTML",
                                      disable_preview=False):
    target_message = None
    chat_id = None
    bot_instance = None

    if isinstance(message_or_call, types.CallbackQuery):
        target_message = message_or_call.message
        if not target_message:
            log.error(f"Cannot process callback without message object. User: {user_id}")
            return
        chat_id = target_message.chat.id
        bot_instance = target_message.bot  # Для aiogram 2.x это Bot.get_current() или переданный экземпляр
        if not bot_instance: bot_instance = Bot.get_current()
    elif isinstance(message_or_call, types.Message):
        target_message = message_or_call
        chat_id = target_message.chat.id
        bot_instance = target_message.bot
        if not bot_instance: bot_instance = Bot.get_current()
    else:
        log.error(f"Unsupported type in _send_or_edit: {type(message_or_call)}")
        return

    if not user_id:
        log.error("User ID is missing in _send_or_edit_photo_message call.")
        if hasattr(message_or_call, 'from_user') and message_or_call.from_user:
            user_id = message_or_call.from_user.id
        else:
            return
    if not bot_instance: log.error(f"Bot instance not found in _send_or_edit for user {user_id}"); return
    if not chat_id: chat_id = user_id  # Фоллбэк для колбэков без message.chat.id (хотя обычно он есть)

    is_callback = isinstance(message_or_call, types.CallbackQuery)
    can_edit_media = is_callback and target_message and hasattr(target_message, 'photo') and target_message.photo
    can_edit_text = is_callback and target_message and not can_edit_media and hasattr(target_message, 'text')
    send_new = not is_callback

    photo_bytes_local = None
    use_photo_local = False
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                photo_bytes_local = f.read()
            if photo_bytes_local:
                use_photo_local = True
            else:
                log.error(f"Helper: Image file is empty: {image_path}")
        except Exception as e:
            log.error(f"Helper: Failed to read image file {image_path}: {e}")
    elif image_path:
        log.error(f"Helper: Image file not found: {image_path}")

    try:
        if is_callback and not send_new:
            if can_edit_media and use_photo_local and photo_bytes_local:
                try:
                    media = InputMediaPhoto(media=photo_bytes_local, caption=caption, parse_mode=parse_mode)
                    await target_message.edit_media(media=media, reply_markup=markup)
                    return
                except MessageNotModified:
                    return
                except Exception as edit_err:
                    log.warning(f"Helper: Edit media failed: {edit_err}. Send new."); send_new = True
            elif can_edit_text and not use_photo_local:
                try:
                    await target_message.edit_text(caption, reply_markup=markup, parse_mode=parse_mode,
                                                   disable_web_page_preview=disable_preview)
                    return
                except MessageNotModified:
                    return
                except Exception as edit_err:
                    log.warning(f"Helper: Edit text failed: {edit_err}. Send new."); send_new = True
            else:
                send_new = True

        if send_new:
            if is_callback and target_message:
                try:
                    await target_message.delete()
                except (MessageCantBeDeleted, MessageToDeleteNotFound):
                    pass
            if use_photo_local and photo_bytes_local:
                await bot_instance.send_photo(chat_id, photo=photo_bytes_local, caption=caption, reply_markup=markup,
                                              parse_mode=parse_mode)
            else:
                await bot_instance.send_message(chat_id, caption, reply_markup=markup, parse_mode=parse_mode,
                                                disable_web_page_preview=disable_preview)
    except Exception as e:
        log.error(f"Helper: Error in _send_or_edit_photo_message chat {chat_id}, user {user_id}: {e}")
        try:
            await bot_instance.send_message(chat_id, caption, reply_markup=markup, parse_mode=None,
                                            disable_web_page_preview=disable_preview)
        except Exception as final_err:
            log.error(f"Helper: Final fallback send failed: {final_err}")


async def show_main_menu(message_event: types.Message | types.CallbackQuery, user_id: int, bot: Bot,
                         edit: bool = False):
    """ Отображает главное меню. message_event может быть Message или CallbackQuery. """
    menu_text = t(user_id, 'welcome_msg')
    markup = get_main_menu_markup(user_id)  # Эта функция должна быть в keyboards.py и возвращать нужную клавиатуру
    image_path = "images/menu.jpg"  # Убедитесь, что путь к файлу корректен

    # Используем вашу универсальную функцию _send_or_edit_photo_message
    await _send_or_edit_photo_message(message_event, user_id, image_path, menu_text, markup)


# --- НОВЫЙ ОБРАБОТЧИК для кнопки "Пополнить баланс/купить буст" ---
async def redirect_to_payment_bot_handler(callback_query: types.CallbackQuery, bot: Bot):  # Добавил bot в аргументы
    await callback_query.answer()
    user_id = callback_query.from_user.id

    # PAYMENT_BOT_USERNAME должен быть импортирован из settings или keyboards
    # и содержать имя пользователя (@username) вашего платежного бота.
    redirect_text = t(user_id, 'redirect_to_payment_bot_text')
    if redirect_text == "MISSING_TEXT_redirect_to_payment_bot_text":  # Фоллбэк текст
        redirect_text = (
            "✨ Для управления балансом через Telegram Stars или покупки бустов, "
            "пожалуйста, воспользуйтесь нашим специальным ботом.\n\n"
            "Выберите желаемое действие:"
        )

    # Клавиатура с прямыми ссылками на платежного бота
    markup = get_redirect_to_payment_bot_keyboard(user_id)

    try:
        # Пытаемся отредактировать текущее сообщение
        if callback_query.message:
            await callback_query.message.edit_text(redirect_text, reply_markup=markup, parse_mode="HTML")
    except MessageNotModified:
        log.debug(f"Message not modified for payment redirect (user: {user_id}).")
    except Exception as e:
        log.warning(
            f"Could not edit message for payment bot redirect (user: {user_id}), error: {e}. Sending new message.")
        # Если редактирование не удалось, отправляем новое сообщение
        await bot.send_message(callback_query.from_user.id, redirect_text, reply_markup=markup, parse_mode="HTML")


# --- Обработчик для кнопки "Назад в меню" ---
async def back_to_main_handler(callback_query: types.CallbackQuery, bot: Bot):  # Добавил bot
    await callback_query.answer()
    # user_id передается в show_main_menu из callback_query.from_user.id
    await show_main_menu(callback_query, callback_query.from_user.id, bot, edit=True)


# --- Ваши существующие обработчики для других кнопок меню ---
async def handle_earn_stars(call: CallbackQuery, bot: Bot):  # Добавил bot
    user_id = call.from_user.id
    chat_id = call.message.chat.id  # Не используется в примере, но может быть нужен
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"IQID fail handle_earn_stars user {user_id}"); return
    except Exception as e:
        log.error(f"Error answering cb handle_earn_stars: {e}"); return

    # Проверка на то, включены ли рефералы (если есть такая настройка)
    if not await database.are_referrals_enabled():  # Предполагается, что эта функция есть
        log.warning(f"User {user_id} tried get ref link while referrals disabled.")
        markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        disabled_text = t(user_id, 'referrals_disabled_message')  # Добавьте этот текст
        if disabled_text == "MISSING_TEXT_referrals_disabled_message":
            disabled_text = "❌ Реферальная программа временно недоступна."
        await _send_or_edit_photo_message(call, user_id, None, disabled_text, markup)
        return

    ref_link = f"https://t.me/{settings.USER_BOT}?start={user_id}"  # USER_BOT из settings - это username вашего ОСНОВНОГО бота
    share_button = InlineKeyboardButton(text='👉 Отправить приглашение другу', switch_inline_query=ref_link)
    markup = InlineKeyboardMarkup(row_width=1).add(share_button, create_back_button(user_id))
    image_path = "images/referalka.jpg"
    text_content = t(user_id, 'earn_stars_text').format(ref_link=ref_link)
    await _send_or_edit_photo_message(call, user_id, image_path, text_content, markup, disable_preview=True)


async def show_profile(call: CallbackQuery, bot: Bot, page: int = 1):  # Добавил bot
    user_id = call.from_user.id
    per_page = 5  # Количество рефералов на странице
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"IQID fail show_profile user {user_id}, page {page}"); return
    except Exception as e:
        log.error(f"Error answering cb show_profile: {e}"); return

    if await database.is_user_blocked(user_id):
        admin_contact_button = InlineKeyboardButton("Связаться с администратором",
                                                    url=f"https://t.me/{settings.SUP_LOGIN}")
        block_keyboard = InlineKeyboardMarkup().add(admin_contact_button)
        block_caption = "❌ <b>Вы заблокированы</b>...\n(Свяжитесь с поддержкой для разъяснений)"
        await _send_or_edit_photo_message(call, user_id, None, block_caption, block_keyboard)
        return

    user_data = await database.get_user(user_id)
    if not user_data:
        await bot.send_message(user_id, t(user_id, 'no_registration'))  # Используем bot для отправки нового сообщения
        return

    stars = user_data['stars']
    full_name = escape(call.from_user.full_name or f"ID:{user_id}")
    all_referrals, total_refs, weekly_refs = await database.get_user_referrals(
        user_id)  # Эта функция должна возвращать и список, и счетчики
    exchange_req = await database.get_exchange_referral_req()
    exchange_status_key = 'exchange_status_available' if weekly_refs >= exchange_req else 'exchange_status_unavailable'
    # Добавьте тексты 'exchange_status_available' и 'exchange_status_unavailable' в texts.py
    exchange_status_text_template = t(user_id, exchange_status_key)
    if "MISSING_TEXT" in exchange_status_text_template:  # Фоллбэк
        exchange_status_text = "✅ <b>Доступен</b>" if weekly_refs >= exchange_req else f"❌ <b>Не доступен ({weekly_refs}/{exchange_req} реф. за неделю)</b>"
    else:
        exchange_status_text = exchange_status_text_template.format(current=weekly_refs, required=exchange_req)

    profile_text = (
        f"✨ <b>Профиль</b>\n{'─' * 14}\n"
        f"👤 <b>Имя:</b> {full_name}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n{'─' * 14}\n"
        f"💰 <b>Баланс:</b> {stars:.2f}⭐\n"
        f"👥 <b>Всего рефералов:</b> {total_refs}\n"
        f"📅 <b>За неделю:</b> {weekly_refs}\n{'─' * 14}\n"
        f"🔄 <b>Обмен звезд (обычный):</b> {exchange_status_text}\n{'─' * 14}\n"  # Уточнил, что это обычный обмен
        f"<i>⬇️ Используй кнопки ниже для действий.</i>"
    )

    total_pages = (total_refs + per_page - 1) // per_page if total_refs > 0 else 1
    page = max(1, min(page, total_pages))  # Убедимся, что страница в допустимых пределах
    # generate_pagination_buttons должна быть в keyboards.py
    buttons_markup = generate_pagination_buttons(user_id, page, total_pages)
    image_path = "images/profile.jpg"
    await _send_or_edit_photo_message(call, user_id, image_path, profile_text, buttons_markup)


async def handle_referrals_page(call: types.CallbackQuery, bot: Bot):  # Добавил bot
    try:
        page = int(call.data.split(":")[1])
        await show_profile(call, bot, page=page)  # Передаем bot
    except (ValueError, IndexError):
        log.error(f"Invalid pagination callback data: {call.data}")
        try:
            await call.answer("Ошибка пагинации.", show_alert=True)
        except InvalidQueryID:
            log.warning(f"IQID fail handle_referrals_page user {call.from_user.id}")
        except Exception as e:
            log.error(f"Error answering cb handle_referrals_page: {e}")


async def show_faq(call: CallbackQuery, bot: Bot):  # Добавил bot
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"IQID fail show_faq user {user_id}"); return
    except Exception as e:
        log.error(f"Error answering cb show_faq: {e}"); return

    if await database.is_user_blocked(user_id):
        admin_contact_button = InlineKeyboardButton("Связаться с администратором",
                                                    url=f"https://t.me/{settings.SUP_LOGIN}")
        block_keyboard = InlineKeyboardMarkup().add(admin_contact_button)
        await _send_or_edit_photo_message(call, user_id, None, "❌ <b>Вы заблокированы</b>...", block_keyboard)
        return

    # Убедитесь, что все ключи форматирования присутствуют в texts.py для 'why_stars'
    faq_text = t(user_id, 'why_stars').format(
        MIN_REF_REWARD=settings.MIN_REF_REWARD,  # Из вашего settings.py
        MAX_REF_REWARD_X2=settings.MAX_REF_REWARD_X2,
        CLICK_MAX_REWARD_X2=settings.CLICK_MAX_REWARD_X2,
        SUP_LOGIN=settings.SUP_LOGIN
    )
    # Добавляем дополнительную информацию, если она у вас была
    faq_text += f"""

<b>❓ Дополнительные вопросы:</b>
<blockquote>🔸 <b>Как вывести звезды?</b>
👉 Инструкцию по выводу звёзд (не Telegram Stars, а обычный вывод) ты найдёшь на <a href='{settings.TELEGRAPH2}'>этой странице</a>.
Для операций с Telegram Stars используй кнопку "💰 Баланс/Буст (Stars)".
</blockquote>
❗ <b>Обратите внимание:</b>
<blockquote>Заявка на обычный вывод может быть отклонена, если вы не подписаны на какой-либо канал или чат проекта.
📩 В таком случае свяжитесь с <a href='t.me/{settings.SUP_LOGIN}'>Администрацией</a>, указав:
— Ссылку на пост с выплатой (если есть)
— Ваш ID из бота (указан в '👤 Профиль')</blockquote>
<b>Наши медиа:</b>
<a href='{settings.LINK_1}'>Канал</a> | <a href='{settings.LINK_2}'>Чат</a> | <a href='{settings.LINK_5}'>Отзывы</a>
"""
    markup = InlineKeyboardMarkup().add(create_back_button(user_id))
    image_path = "images/faq.jpg"
    await _send_or_edit_photo_message(call, user_id, image_path, faq_text, markup, disable_preview=True)


async def show_referral_top(call: CallbackQuery, bot: Bot, period: str):  # Добавил bot
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"IQID fail show_referral_top user {user_id}"); return
    except Exception as e:
        log.error(f"Error answering cb show_referral_top: {e}"); return

    period_map = {
        'day': ('day', 'Топ-5 рефералов за 24 часа'),
        'week': ('week', 'Топ-5 рефералов за неделю'),
        'month': ('month', 'Топ-5 рефералов за месяц')
    }
    period_code, period_title = period_map.get(period, ('day', 'Топ-5 рефералов за 24 часа'))

    try:
        top_referrals_data = await database.get_referral_top_by_period(period_code)
    except Exception as e:
        log.exception(f"Error fetching top {period_code}: {e}");
        await bot.send_message(user_id, "Ошибка загрузки топа.");
        return  # Используем bot для отправки нового

    top_text = f"<b>{period_title}:</b>\n\n"
    medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣']
    user_pos_info, user_ref_count_period, user_in_top = "", 0, False

    if not top_referrals_data:
        top_text += "<i>Топ пока пуст. Приглашайте друзей!</i>"
    else:
        processed_count = 0
        for rank, ref_data in enumerate(top_referrals_data, 1):
            ref_id, count = ref_data.get('referral_id'), ref_data.get('ref_count')  # Используем .get() для безопасности
            if not ref_id or count is None: continue

            is_cur_user = (ref_id == user_id)
            if is_cur_user: user_ref_count_period = count

            if rank <= 5:
                try:
                    # Получаем username асинхронно
                    username_db = await database.get_user_username(ref_id)
                    display_name = sanitize_username(mask_username(username_db)) or f"ID: {mask_id(ref_id)}"
                    top_text += f"{medals[rank - 1]} {escape(display_name)} | Реф: <code>{count}</code>\n"
                    processed_count += 1
                    if is_cur_user: user_in_top = True
                except Exception as e_user:
                    log.error(f"Error processing top entry for user {ref_id}: {e_user}")
                    continue
        if processed_count == 0 and top_referrals_data:  # Если были данные, но не смогли обработать топ-5
            top_text += "<i>Не удалось загрузить данные для отображения топа.</i>"
        elif processed_count == 0 and not top_referrals_data:  # Если изначально не было данных
            top_text += "<i>Топ пока пуст. Приглашайте друзей!</i>"

    if not user_in_top:  # Если текущий пользователь не в топ-5
        # Получаем его результат за период отдельно, если это не текущий день (для дня уже есть из get_referral_top_by_period)
        if period_code != 'day':  # Для недели и месяца нужно пересчитать конкретно для этого юзера
            if period_code == 'week':
                user_ref_count_period = await database.get_referrals_count_week(user_id)
            elif period_code == 'month':
                # Вам понадобится функция get_referrals_count_month(user_id) в database.py
                # Для примера, если такой функции нет:
                # user_ref_count_period = await database.get_referrals_count_for_period(user_id, 30)
                # Пока что поставим 0, если функции нет
                user_total_refs = await database.get_referrals_count(user_id)  # Это общее число, не за месяц!
                log.warning(
                    f"Function get_referrals_count_month not implemented, showing total refs {user_total_refs} for user {user_id} in monthly top placeholder.")
                user_ref_count_period = 0  # Заглушка, так как нет функции для месяца

        user_pos_info = f"\n🚫 Вы не в Топ-5. Реф. за период: <code>{user_ref_count_period}</code>."
    elif user_in_top:  # Если пользователь в топ-5
        user_pos_info = f"\n<b>🏅 Ваши реф. за период:</b> <code>{user_ref_count_period}</code>."
    top_text += user_pos_info

    markup = InlineKeyboardMarkup(row_width=3)
    btns = []
    if period != 'day': btns.append(InlineKeyboardButton("📅 День", callback_data="top_ref_day"))
    if period != 'week': btns.append(InlineKeyboardButton("📅 Неделя", callback_data="top_ref_week"))
    if period != 'month': btns.append(InlineKeyboardButton("📅 Месяц", callback_data="top_ref_month"))
    if btns: markup.row(*btns)
    markup.add(InlineKeyboardButton("⭐ Топ по звёздам", callback_data="top_stars"))
    markup.add(create_back_button(user_id))
    image_path = "images/tops.jpg"
    await _send_or_edit_photo_message(call, user_id, image_path, top_text, markup, disable_preview=True)


async def show_stars_top(call: CallbackQuery, bot: Bot):
    """Показывает топ-10 по звёздам."""
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        return
    except Exception:
        return

    top_users = await database.get_top_users()
    top_text = "<b>🏆 Топ-10 по звёздам:</b>\n\n"
    medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

    if not top_users:
        top_text += "<i>Топ пока пуст.</i>"
    else:
        for rank, u in enumerate(top_users[:10], 1):
            uid = u['id']
            stars = u['stars']
            username_db = u.get('username') or f"id_{uid}"
            display_name = sanitize_username(mask_username(username_db)) or f"ID: {mask_id(uid)}"
            medal = medals[rank - 1] if rank <= 10 else f"{rank}."
            is_me = " ← ты" if uid == user_id else ""
            top_text += f"{medal} {escape(display_name)} | <code>{stars:.2f}⭐</code>{is_me}\n"

    # Проверяем позицию юзера
    user_data = await database.get_user(user_id)
    if user_data:
        user_stars = user_data['stars']
        top_text += f"\n💰 <b>Твой баланс:</b> <code>{user_stars:.2f}⭐</code>"

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("👥 Топ рефералов", callback_data="top_5"))
    markup.add(create_back_button(user_id))
    image_path = "images/tops.jpg"
    await _send_or_edit_photo_message(call, user_id, image_path, top_text, markup, disable_preview=True)


def register_user_menu_handlers(dp: Dispatcher, bot: Bot):  # Передаем bot
    # Регистрация кнопки для редиректа в платежного бота
    dp.register_callback_query_handler(
        lambda query: redirect_to_payment_bot_handler(query, bot),  # Передаем bot
        lambda c: c.data == "redirect_to_payment_bot",
        state="*"
    )
    # Обработчик для кнопки "Назад в меню"
    dp.register_callback_query_handler(
        lambda call: back_to_main_handler(call, bot),  # Передаем bot
        lambda c: c.data == "back_main",
        state="*"
    )
    # Ваши существующие обработчики
    dp.register_callback_query_handler(lambda call: handle_earn_stars(call, bot), lambda c: c.data == "earn_stars",
                                       state="*")
    dp.register_callback_query_handler(lambda call: show_profile(call, bot), lambda c: c.data == "my_balance",
                                       state="*")
    dp.register_callback_query_handler(lambda call: handle_referrals_page(call, bot),
                                       lambda c: c.data.startswith("referrals_page:"), state="*")
    dp.register_callback_query_handler(lambda call: show_faq(call, bot), lambda c: c.data == "faq", state="*")

    # Топы
    dp.register_callback_query_handler(lambda call: show_referral_top(call, bot, period='day'),
                                       lambda c: c.data == "top_5" or c.data == "top_ref_day", state="*")
    dp.register_callback_query_handler(lambda call: show_referral_top(call, bot, period='week'),
                                       lambda c: c.data == "top_ref_week", state="*")
    dp.register_callback_query_handler(lambda call: show_referral_top(call, bot, period='month'),
                                       lambda c: c.data == "top_ref_month", state="*")
    dp.register_callback_query_handler(lambda call: show_stars_top(call, bot),
                                       lambda c: c.data == "top_stars", state="*")

    log.info("User menu handlers registered (main bot).")
