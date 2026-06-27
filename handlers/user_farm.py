import logging
import random
import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID

import database
from settings import (
    CLICK_MIN_REWARD_X2, CLICK_MAX_REWARD_X2, MIN_GIFT, MAX_GIFT, MIN_GIFT_L, MAX_GIFT_L, SUP_LOGIN
)
from utils import t, show_advert
from keyboards import create_back_button
from handlers.common import check_subscription

log = logging.getLogger('handlers.user_farm')


async def delete_message_after_delay(message: types.Message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


async def handle_click_star(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    current_time_utc = datetime.now(timezone.utc)

    try:
        await call.answer()
    except InvalidQueryID:
        return
    except Exception:
        return

    if not await check_subscription(bot, user_id, chat_id):
        sent_msg = await bot.send_message(chat_id, t(user_id, "not_subscribed"))
        asyncio.create_task(delete_message_after_delay(sent_msg, 5))
        try:
            await call.message.delete()
        except:
            pass
        return

    if await database.is_user_blocked(user_id):
        sent_msg = await bot.send_message(chat_id, "❌ Вы заблокированы!")
        asyncio.create_task(delete_message_after_delay(sent_msg, 5))
        return

    try:
        current_username = call.from_user.username
        stored_username = await database.get_user_username(user_id)
        if stored_username != current_username:
            await database.update_user_username(user_id, current_username)
    except Exception as e:
        log.error(f"Error updating username for {user_id}: {e}")

    # --- Огонёк (Streak) — обновляем при каждом клике ---
    try:
        streak_result = await database.update_user_streak(user_id)
        if streak_result['reward_given']:
            streak_text = (
                f"🔥 <b>Серия {streak_result['streak']} дней подряд!</b>\n"
                f"💰 Награда: <code>+{streak_result['reward_amount']:.2f}⭐</code>"
            )
            sent_msg = await bot.send_message(chat_id, streak_text, parse_mode="HTML")
            asyncio.create_task(delete_message_after_delay(sent_msg, 5))
    except Exception as e:
        log.error(f"Error updating streak for user {user_id}: {e}")
    # ---------------------------------------------------

    last_click_time_db = await database.get_last_click_time(user_id)
    click_cooldown = 240
    if last_click_time_db:
        time_diff_seconds = (current_time_utc - last_click_time_db).total_seconds()
        if time_diff_seconds < click_cooldown:
            time_left_seconds = click_cooldown - time_diff_seconds
            minutes_left = int(time_left_seconds // 60)
            seconds_left = int(time_left_seconds % 60)
            cooldown_text = f"⏳ Подожди еще {minutes_left} мин {seconds_left} сек"
            sent_msg = await bot.send_message(chat_id, cooldown_text)
            asyncio.create_task(delete_message_after_delay(sent_msg, 3))
            return

    base_min_reward, base_max_reward = await database.get_custom_reward_from_db(user_id)
    is_lucky = await database.is_lucky_time_now()
    if is_lucky:
        base_min_reward, base_max_reward = CLICK_MIN_REWARD_X2, CLICK_MAX_REWARD_X2

    farm_speed_multiplier = await database.get_active_farm_speed_multiplier(user_id)
    actual_min_reward = base_min_reward * farm_speed_multiplier
    actual_max_reward = base_max_reward * farm_speed_multiplier

    random_stars = round(random.uniform(actual_min_reward, actual_max_reward), 2)

    try:
        await database.add_stars(user_id, random_stars)
        await database.increment_click_count(user_id)
        await database.update_last_click_time(user_id)
        await database.add_game_history_record(user_id, 'clicker', random_stars, "Награда за клик")
    except Exception as e:
        log.exception(f"Database error during click processing for user {user_id}: {e}")
        sent_msg = await bot.send_message(chat_id, "Ошибка при обработке клика.")
        asyncio.create_task(delete_message_after_delay(sent_msg, 3))
        return

    success_text = f"🎉 Ты получил {random_stars:.2f}⭐"
    if farm_speed_multiplier > 1.0:
        success_text += f" (буст x{farm_speed_multiplier:.1f} активен!)"

    sent_msg = await bot.send_message(chat_id, success_text)
    asyncio.create_task(delete_message_after_delay(sent_msg, 3))
    await show_advert(user_id)


async def handle_gift_day(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    current_time_utc = datetime.now(timezone.utc)

    try:
        await call.answer()
    except InvalidQueryID:
        return
    except Exception:
        return

    if await database.is_user_blocked(user_id):
        sent_msg = await bot.send_message(chat_id, "❌ Вы заблокированы!")
        asyncio.create_task(delete_message_after_delay(sent_msg, 5))
        return

    last_gift_time_db = await database.get_last_gift(user_id)
    gift_cooldown = timedelta(days=1)
    if last_gift_time_db:
        time_diff = current_time_utc - last_gift_time_db
        if time_diff < gift_cooldown:
            time_left = gift_cooldown - time_diff
            hours_left = int(time_left.total_seconds() // 3600)
            minutes_left = int((time_left.total_seconds() % 3600) // 60)
            seconds_left = int(time_left.total_seconds() % 60)
            cooldown_msg_text = f"⏳ Осталось: {hours_left}ч {minutes_left}м {seconds_left}с"
            sent_msg = await bot.send_message(chat_id, text=cooldown_msg_text)
            asyncio.create_task(delete_message_after_delay(sent_msg, 3))
            return

    min_gift_reward, max_gift_reward = MIN_GIFT, MAX_GIFT
    is_lucky = await database.is_lucky_time_now()
    if is_lucky:
        min_gift_reward, max_gift_reward = MIN_GIFT_L, MAX_GIFT_L

    farm_speed_multiplier = await database.get_active_farm_speed_multiplier(user_id)
    actual_min_reward = min_gift_reward * farm_speed_multiplier
    actual_max_reward = max_gift_reward * farm_speed_multiplier

    random_stars = round(random.uniform(actual_min_reward, actual_max_reward), 2)

    try:
        await database.add_stars(user_id, random_stars)
        await database.increment_gift_count(user_id)
        await database.update_last_gift(user_id)
        await database.add_game_history_record(user_id, 'gift', random_stars, "Ежедневный подарок")
    except Exception as e:
        log.exception(f"Database error during gift processing for user {user_id}: {e}")
        sent_msg = await bot.send_message(chat_id, "Ошибка при получении подарка.")
        asyncio.create_task(delete_message_after_delay(sent_msg, 3))
        return

    success_msg_text = f"🎁 Ежедневный бонус: +{random_stars:.2f}⭐"
    if farm_speed_multiplier > 1.0:
        success_msg_text += f" (буст x{farm_speed_multiplier:.1f} активен!)"

    sent_msg = await bot.send_message(chat_id, text=success_msg_text)
    asyncio.create_task(delete_message_after_delay(sent_msg, 3))
    await show_advert(user_id)


def register_user_farm_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(lambda call: handle_click_star(call, bot), lambda c: c.data == "click_star",
                                       state="*")
    dp.register_callback_query_handler(lambda call: handle_gift_day(call, bot), lambda c: c.data == "giftday",
                                       state="*")
    log.info("User farming handlers registered.")
