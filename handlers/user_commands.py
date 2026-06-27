import logging
import re
import random
import asyncpg
from html import escape
import datetime

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID
from datetime import timezone
import database
from settings import (
    ADMIN_IDS, USER_BOT, LINK_BOT, LOG_CH_USER, MAX_REF_REWARD_X2,
    MIN_REF_REWARD, CLICK_MAX_REWARD_X2, SUP_LOGIN, LOG_VER_USER
)
from utils import t, mask_id, mask_username, sanitize_username, format_datetime
from keyboards import create_back_button
from handlers.user_menu import show_main_menu

log = logging.getLogger('handlers.user_commands')


async def award_referral(user_id: int, bot: Bot):
    if not await database.are_referrals_enabled():
        log.info(f"Referral program disabled. Skipping award referral for user {user_id}.")
        return

    try:
        user_data = await database.get_user(user_id)
        if not user_data:
            log.warning(f"Cannot award referral: User {user_id} not found in DB.")
            return

        referral_id = user_data['referral_id']
        ref_rewarded = user_data['ref_rewarded']
        special_code = user_data['special_ref']

        if not referral_id or ref_rewarded == 1 or user_id == referral_id:
            log.debug(
                f"Conditions not met for awarding referral for user {user_id}. Ref: {referral_id}, Rewarded: {ref_rewarded}")
            return

        min_reward, max_reward = await database.get_referral_reward_range(referral_id)
        reward = round(random.uniform(min_reward, max_reward), 2)

        await database.add_stars(referral_id, reward)
        log.info(f"Awarded {reward} stars to referrer {referral_id} for verified user {user_id}.")

        await database.update_user_ref_rewarded(user_id, True)

        ref_link = f"https://t.me/{USER_BOT}?start={referral_id}"
        try:
            referrer_lang = await database.get_user_lang(referral_id)
            notify_text = t(referrer_lang, 'referral_notify').format(reward=reward)
            await bot.send_message(referral_id, notify_text)
        except Exception as e:
            log.error(f"Failed to send referral notification to {referral_id}: {e}")

        pool = database.db_pool
        if not pool: log.error("DB pool not available for referral logging."); return
        async with pool.acquire() as conn:
            try:
                ref_info_text = "Нет"
                ref_username_text = "-"
                if referral_id:
                    ref_username_text = await conn.fetchval("SELECT username FROM users WHERE id = $1",
                                                            referral_id) or "-"
                    ref_info_text = f"<a href='tg://user?id={referral_id}'>Профиль</a> (@{escape(ref_username_text)})"
                else:
                    ref_info_text = f"ID: <code>{referral_id}</code> (не найден)"

                user_full_name = escape(user_data['username'] or f"id_{user_id}")
                user_telegram_link = f"<a href='tg://user?id={user_id}'>{user_full_name}</a>"
                log_message = (
                    f"✅ <b>Верифицирован новый пользователь!</b>\n\n"
                    f"👤 <b>Пользователь:</b> {user_telegram_link}\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                    f"🔗 <b>Пригласивший:</b> {ref_info_text}\n"
                    f"{f'🔖 <b>Спец. ссылка:</b> <code>{escape(special_code)}</code>' if special_code else ''}\n\n"
                    f"💰 <b>Награда рефереру:</b> <code>{reward:.2f}⭐️</code>"
                )
                inline_kb = InlineKeyboardMarkup().add(
                    InlineKeyboardButton(text="Профиль пользователя", url=f"tg://user?id={user_id}")
                )
                if referral_id:
                    inline_kb.add(InlineKeyboardButton(text="Профиль реферера", url=f"tg://user?id={referral_id}"))

                if LOG_VER_USER:
                    try:
                        await bot.send_message(LOG_VER_USER, log_message, reply_markup=inline_kb, parse_mode="HTML",
                                               disable_web_page_preview=True)
                        log.info(f"Sent verified user notification to log channel {LOG_VER_USER} for user {user_id}")
                    except Exception as e:
                        log.error(f"Failed to send verified user log message to {LOG_VER_USER}: {e}")
                else:
                    log.warning("LOG_VER_USER not set in settings.")
            except Exception as e:
                log.exception(f"Error during verified user logging for {user_id}: {e}")

    except Exception as e:
        log.exception(f"Unexpected error awarding referral for user {user_id}: {e}")


async def handle_start(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = escape(message.from_user.full_name or "")
    chat_id = message.chat.id
    log.info(f"Processing /start for user: id={user_id}, username={username}, full_name='{full_name}'")

    if re.search(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]', full_name):
        log.warning(f"Potential spam detected from user {user_id} (Arabic script in name). Ignoring.")
        return

    args = message.text.split()
    referral_id = None
    special_ref = None
    existing_user_data = await database.get_user(user_id)
    is_new_user = not existing_user_data
    referrals_on = await database.are_referrals_enabled()

    if len(args) > 1:
        param = args[1]
        log.debug(f"Start command parameter for user {user_id}: {param}")
        if is_new_user and referrals_on:
            if param.isdigit() and int(param) != user_id:
                ref_id_candidate = int(param)
                if await database.user_exists(ref_id_candidate):
                    referral_id = ref_id_candidate
                    log.info(f"User {user_id} referred by user {referral_id}")
                else:
                    log.warning(f"Referrer ID {ref_id_candidate} not found for user {user_id}.")
            elif param.startswith("ref_"):
                special_ref = param
                log.info(f"User {user_id} potentially referred by special link: {special_ref}")
                pool = database.db_pool
                if pool:
                    async with pool.acquire() as conn:
                        try:
                            async with conn.transaction():
                                ref_owner_id = await conn.fetchval(
                                    "SELECT user_id FROM special_links WHERE special_code = $1", special_ref)
                                if ref_owner_id:
                                    log.info(f"Special link {special_ref} belongs to user {ref_owner_id}.")
                                    if referral_id is None:
                                        referral_id = ref_owner_id
                                        log.info(f"Setting referrer for {user_id} to special link owner {ref_owner_id}")

                                    await conn.execute(
                                        "UPDATE special_links SET total_visits = total_visits + 1 WHERE special_code = $1",
                                        special_ref)
                                    visit_time = datetime.now(timezone.utc)
                                    res_insert = await conn.execute(
                                        "INSERT INTO special_link_visits (user_id, special_code, visit_time) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                                        user_id, special_ref, visit_time)
                                    if res_insert and int(res_insert.split()[-1]) > 0:
                                        await conn.execute(
                                            "UPDATE special_links SET unique_visits = unique_visits + 1 WHERE special_code = $1",
                                            special_ref)
                                        log.info(
                                            f"Recorded unique visit for user {user_id} via special link {special_ref}.")
                                    else:
                                        log.debug(f"User {user_id} already visited via special link {special_ref}.")
                                else:
                                    log.warning(f"Special link code {special_ref} not found.")
                                    special_ref = None
                        except Exception as e:
                            log.exception(
                                f"Database error processing special link {special_ref} for user {user_id}: {e}")
                            special_ref = None
                else:
                    log.error("DB pool not available for special link processing.")
            else:
                log.warning(f"Invalid start parameter '{param}' for user {user_id}.")
        elif is_new_user and not referrals_on:
            log.info(f"User {user_id} is new, but referral program is disabled. Ignoring parameter '{param}'.")
        else:
            log.info(f"User {user_id} is not new, ignoring start parameter '{param}'.")

    if is_new_user:
        log.info(f"User {user_id} is new. Adding to database.")
        username_to_db = username or f"id_{user_id}"
        await database.add_user(user_id, username_to_db, referral_id=referral_id, lang='ru',
                                special_ref=special_ref)

        pool = database.db_pool
        if pool:
            async with pool.acquire() as conn:
                try:
                    user_count = await conn.fetchval("SELECT COUNT(*) FROM users") or 0

                    ref_info_text = "Нет"
                    if referral_id:
                        ref_username = await conn.fetchval("SELECT username FROM users WHERE id = $1",
                                                           referral_id) or "-"
                        ref_info_text = f"<a href='tg://user?id={referral_id}'>Профиль</a> (@{escape(ref_username)})"
                    elif special_ref:
                        ref_info_text = f"(Спец. ссылка: <code>{escape(special_ref)}</code>)"

                    user_display_name = full_name if full_name else username_to_db
                    user_telegram_link = f"<a href='tg://user?id={user_id}'>{user_display_name}</a>"
                    log_message = (
                        f"🚨 <b>Новый пользователь №{user_count}</b>\n\n"
                        f"👤 <b>Пользователь:</b> {user_telegram_link}\n"
                        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                        f"📛 <b>Username:</b> @{username if username else '-'}\n\n"
                        f"🔗 <b>Пригласивший:</b> {ref_info_text}\n"
                        f"{f'🔖 <b>Спец. ссылка:</b> <code>{escape(special_ref)}</code>' if special_ref and not referral_id else ''}"
                    )
                    inline_kb = InlineKeyboardMarkup().add(
                        InlineKeyboardButton(text="Профиль пользователя", url=f"tg://user?id={user_id}"))
                    if referral_id:
                        inline_kb.add(InlineKeyboardButton(text="Профиль реферера", url=f"tg://user?id={referral_id}"))

                    if LOG_CH_USER:
                        try:
                            await bot.send_message(LOG_CH_USER, log_message, reply_markup=inline_kb, parse_mode="HTML",
                                                   disable_web_page_preview=True)
                        except Exception as e:
                            log.error(f"Failed to send new user log message to {LOG_CH_USER}: {e}")
                    else:
                        log.warning("LOG_CH_USER not set in settings.")
                except Exception as e:
                    log.exception(f"Error during new user logging for {user_id}: {e}")
        else:
            log.error("DB pool not available for new user logging.")
    else:
        log.info(f"User {user_id} already exists.")
        current_username_db = existing_user_data['username']
        telegram_username = username
        if current_username_db != telegram_username:
            username_to_update = telegram_username or f"id_{user_id}"
            await database.update_user_username(user_id, username_to_update)
            log.info(
                f"Updated existing user {user_id} username from '{current_username_db}' to '{username_to_update}'.")

    from handlers.common import check_subscription
    subscribed = await check_subscription(bot, user_id, chat_id)
    if subscribed:
        # --- Капча при /start (inline-кнопки) ---
        import random as _rnd
        ops = [('+', lambda a, b: a+b), ('-', lambda a, b: a-b), ('×', lambda a, b: a*b)]
        sym, func = _rnd.choice(ops)
        if sym == '×':
            a, b = _rnd.randint(2, 9), _rnd.randint(2, 9)
        elif sym == '-':
            a = _rnd.randint(5, 20); b = _rnd.randint(1, a)
        else:
            a, b = _rnd.randint(1, 20), _rnd.randint(1, 20)
        correct = func(a, b)
        # Генерируем 3 неправильных ответа
        wrong = set()
        while len(wrong) < 3:
            w = correct + _rnd.randint(-5, 5)
            if w != correct and w not in wrong:
                wrong.add(w)
        answers = [correct] + list(wrong)
        _rnd.shuffle(answers)

        markup = InlineKeyboardMarkup(row_width=4)
        buttons = [
            InlineKeyboardButton(str(ans), callback_data=f"captcha_start:{ans}:{correct}")
            for ans in answers
        ]
        markup.row(*buttons)

        await bot.send_message(
            chat_id,
            f"🤖 <b>Проверка: Вы не бот?</b>\n\n"
            f"Реши пример: <code>{a} {sym} {b} = ?</code>",
            parse_mode="HTML", reply_markup=markup
        )


async def handle_start_captcha_answer(call: CallbackQuery, bot: Bot):
    """Обработка ответа на капчу при /start."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        parts = call.data.split(":")
        user_answer = int(parts[1])
        correct_answer = int(parts[2])
    except (ValueError, IndexError):
        await call.answer("Ошибка", show_alert=True)
        return

    if user_answer == correct_answer:
        await call.answer("✅ Верно!")
        try:
            await call.message.delete()
        except:
            pass
        await show_main_menu(call.message, user_id, bot, edit=False)
    else:
        await call.answer("❌ Неверно! Попробуй ещё раз.", show_alert=True)


async def handle_why(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    if await database.user_exists(user_id):
        ref_link = f"https://t.me/{USER_BOT}?start={user_id}"
        why_text = t(user_id, 'why_stars').format(
            ref_link=ref_link,
            MAX_REF_REWARD_X2=MAX_REF_REWARD_X2,
            MIN_REF_REWARD=MIN_REF_REWARD,
            CLICK_MAX_REWARD_X2=CLICK_MAX_REWARD_X2,
            SUP_LOGIN=SUP_LOGIN
        )
        await message.answer(why_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.answer(t(user_id, 'no_registration'))


async def back_to_main(call: types.CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"IQID fail back_to_main user {user_id}")
    except Exception as e:
        log.error(f"Error answering cb back_to_main: {e}")
    # Передаем user_id напрямую
    await show_main_menu(call.message, user_id, bot, edit=True)


async def handle_link_stats(message: types.Message):
    user_id = message.from_user.id
    links = []
    pool = database.db_pool
    if not pool:
        await message.reply("Ошибка: Пул БД не инициализирован.")
        return
    async with pool.acquire() as conn:
        try:
            links = await conn.fetch("""
                SELECT special_code, total_visits, unique_visits, completed_onboarding
                FROM special_links WHERE user_id = $1 ORDER BY id DESC
            """, user_id)
        except Exception as e:
            log.exception(f"Database error getting link stats for user {user_id}: {e}")
            await message.reply("Произошла ошибка при получении статистики.")
            return

    if not links:
        await message.reply("У вас нет созданных специальных ссылок.")
        return

    text = "📊 <b>Статистика ваших спецссылок:</b>\n\n"
    base_link = f"https://t.me/{USER_BOT}?start="
    for link_data in links:
        code = link_data['special_code']
        total = link_data['total_visits']
        unique = link_data['unique_visits']
        onboarding = link_data['completed_onboarding']
        full_link = f"{base_link}{escape(code)}"
        text += (f"🔗 <code>{full_link}</code>\n"
                 f"    🔄 Всего запусков: {total}\n"
                 f"    👥 Уникальных запусков: {unique}\n"
                 f"    ✅ Прошли ОП: {onboarding}\n\n")

    await message.reply(text, parse_mode="HTML", disable_web_page_preview=True)


def register_user_command_handlers(dp: Dispatcher, bot: Bot):
    dp.register_message_handler(lambda msg: handle_start(msg, bot), commands=['start'], state="*")
    dp.register_message_handler(lambda msg: handle_why(msg, bot), commands=['why'], state="*")
    dp.register_message_handler(handle_link_stats, commands=['linkstats'], state="*")
    dp.register_callback_query_handler(lambda call: back_to_main(call, bot), lambda c: c.data == "back_main", state="*")
    dp.register_callback_query_handler(lambda call: handle_start_captcha_answer(call, bot),
                                       lambda c: c.data.startswith("captcha_start:"), state="*")
    log.info("User command handlers registered.")
