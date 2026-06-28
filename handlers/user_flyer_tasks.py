import logging
from datetime import datetime

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID

import database
from settings import FLYER_API_KEY
from utils import t
from keyboards import create_back_button
from handlers.common import check_subscription

log = logging.getLogger('handlers.user_flyer_tasks')

flyer = None
if FLYER_API_KEY:
    try:
        from flyerapi import Flyer
        flyer = Flyer(FLYER_API_KEY)
        log.info("FlyerBot API initialized successfully.")
    except ImportError:
        log.error("flyerapi package not installed! Run: pip install flyerapi")
    except Exception as e:
        log.error(f"Failed to initialize FlyerBot API: {e}")
else:
    log.warning("FLYER_API_KEY not configured. FlyerBot tasks will be disabled.")

FLYER_TASK_REWARD = 1.0


async def _check_and_give_flyer_reward(user_id: int) -> float | None:
    today = datetime.now().strftime('%Y-%m-%d')
    pool = database.db_pool
    if not pool:
        log.error("DB pool not available for flyer reward")
        return None

    async with pool.acquire() as conn:
        try:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS flyer_completions (
                    user_id BIGINT NOT NULL,
                    completed_date TEXT NOT NULL,
                    reward REAL NOT NULL,
                    PRIMARY KEY (user_id, completed_date)
                )
            ''')

            row = await conn.fetchrow(
                'SELECT 1 FROM flyer_completions WHERE user_id=$1 AND completed_date=$2',
                user_id, today
            )
            if row:
                return None

            await database.add_stars(user_id, FLYER_TASK_REWARD)
            await conn.execute(
                'INSERT INTO flyer_completions (user_id, completed_date, reward) VALUES ($1, $2, $3)',
                user_id, today, FLYER_TASK_REWARD
            )
            log.info(f"User {user_id} completed FlyerBot tasks. Reward: {FLYER_TASK_REWARD}")
            return FLYER_TASK_REWARD
        except Exception as e:
            log.exception(f"Error giving FlyerBot reward to user {user_id}: {e}")
            return None


async def show_flyer_tasks(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    language_code = call.from_user.language_code or 'ru'

    try:
        await call.answer()
    except (InvalidQueryID, Exception):
        pass

    if not await check_subscription(bot, user_id, chat_id):
        try:
            await call.answer(t(user_id, "not_subscribed"), show_alert=True)
        except (InvalidQueryID, Exception):
            pass
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        return

    if not flyer:
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        await call.message.answer(
            "⚠️ Задания FlyerBot временно недоступны.",
            reply_markup=back_markup
        )
        return

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass

    try:
        custom_message = {
            'text': '<b>Выполни задания спонсоров</b>\n\nПодпишись на каналы ниже и получи награду',
            'button_bot': 'Проверить',
            'button_channel': 'Подписаться',
            'button_url': 'Перейти',
        }

        is_completed = await flyer.check(
            user_id,
            language_code=language_code,
            message=custom_message
        )

        if is_completed:
            reward_given = await _check_and_give_flyer_reward(user_id)
            back_markup = InlineKeyboardMarkup(row_width=1)
            back_markup.add(
                InlineKeyboardButton("🔄 Проверить снова", callback_data="flyer_tasks"),
                create_back_button(user_id)
            )
            if reward_given:
                await call.message.answer(
                    f"✅ Задания выполнены! Награда: {reward_given:.2f} ⭐",
                    reply_markup=back_markup
                )
            else:
                await call.message.answer(
                    "✅ Задания выполнены! Вы уже получили награду.\n🔄 Новые задания появятся позже.",
                    reply_markup=back_markup
                )
        else:
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(
                InlineKeyboardButton("✅ Я выполнил задания", callback_data="flyer_check"),
                create_back_button(user_id)
            )
            await call.message.answer(
                "📋 <b>Задания FlyerBot</b>\n\n"
                "Выполни задания спонсоров выше ☝️ и нажми проверку",
                reply_markup=markup,
                parse_mode="HTML"
            )
    except Exception as e:
        log.exception(f"Error checking FlyerBot for user {user_id}: {e}")
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        await call.message.answer("❌ Ошибка загрузки заданий.", reply_markup=back_markup)


async def handle_flyer_check(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    language_code = call.from_user.language_code or 'ru'

    try:
        await call.answer("🔄 Проверяю...")
    except (InvalidQueryID, Exception):
        pass

    if not flyer:
        await call.answer("⚠️ Сервис недоступен", show_alert=True)
        return

    try:
        is_completed = await flyer.check(user_id, language_code=language_code)

        if is_completed:
            reward_given = await _check_and_give_flyer_reward(user_id)
            back_markup = InlineKeyboardMarkup(row_width=1)
            back_markup.add(
                InlineKeyboardButton("🔄 Проверить снова", callback_data="flyer_tasks"),
                create_back_button(user_id)
            )
            try:
                await call.message.delete()
            except (MessageCantBeDeleted, MessageToDeleteNotFound):
                pass
            if reward_given:
                await call.message.answer(
                    f"✅ Задания выполнены! Награда: {reward_given:.2f} ⭐",
                    reply_markup=back_markup
                )
            else:
                await call.message.answer(
                    "✅ Все выполнено! Награда уже получена.\n🔄 Новые задания позже.",
                    reply_markup=back_markup
                )
        else:
            await call.answer("❌ Не все задания выполнены!", show_alert=True)
    except Exception as e:
        log.exception(f"Error in handle_flyer_check for user {user_id}: {e}")
        await call.answer("❌ Ошибка проверки.", show_alert=True)


def register_user_flyer_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(
        lambda call: show_flyer_tasks(call, bot),
        lambda c: c.data == "flyer_tasks", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: handle_flyer_check(call, bot),
        lambda c: c.data == "flyer_check", state="*"
    )
    log.info("User FlyerBot task handlers registered.")
