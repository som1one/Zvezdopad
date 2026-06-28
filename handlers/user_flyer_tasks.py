# Содержимое файла: handlers/user_flyer_tasks.py
# Задания через FlyerBot — пользователь получает задания (подписки/ссылки) из сервиса FlyerBot
import logging

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputFile
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID

from database import add_stars, get_db_connection
from settings import FLYER_API_KEY
from utils import t
from keyboards import create_back_button
from handlers.common import check_subscription

log = logging.getLogger('handlers.user_flyer_tasks')

# Инициализация FlyerBot API
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


async def show_flyer_tasks(call: CallbackQuery, bot: Bot):
    """
    Показывает задания FlyerBot пользователю.
    Если пользователь не выполнил все задания — FlyerBot сам отправит ему сообщение с заданиями.
    Если все выполнены — начисляем награду.
    """
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    language_code = call.from_user.language_code or 'ru'

    try:
        await call.answer()
    except (InvalidQueryID, Exception) as e:
        log.warning(f"Error answering callback in show_flyer_tasks for user {user_id}: {e}")

    # Проверяем подписку на основные каналы
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

    # Проверяем, настроен ли FlyerBot
    if not flyer:
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        await call.message.answer(
            "⚠️ Задания FlyerBot временно недоступны. Попробуйте позже.",
            reply_markup=back_markup
        )
        return

    # Удаляем предыдущее сообщение
    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass

    # Проверяем, выполнил ли пользователь все задания FlyerBot
    try:
        # flyer.check() возвращает True если пользователь выполнил все задания,
        # False если нет (и FlyerBot сам отправит ему сообщение с заданиями)
        custom_message = {
            'text': '📋 <b>Выполни задания спонсоров</b>\n\nПодпишись на каналы ниже и получи награду ⭐️',
            'button_bot': '✅ Проверить',
            'button_channel': '📢 Подписаться',
            'button_url': '🔗 Перейти',
        }

        is_completed = await flyer.check(
            user_id,
            language_code=language_code,
            message=custom_message
        )

        if is_completed:
            # Пользователь выполнил все задания FlyerBot
            # Проверяем, не получал ли он уже награду за текущую сессию
            reward_given = await _check_and_give_flyer_reward(user_id)

            back_markup = InlineKeyboardMarkup(row_width=1)
            back_markup.add(
                InlineKeyboardButton("🔄 Проверить ещё раз", callback_data="flyer_tasks"),
                create_back_button(user_id)
            )

            if reward_given:
                await call.message.answer(
                    f"✅ Все задания выполнены! Награда начислена: {reward_given:.2f} ⭐",
                    reply_markup=back_markup
                )
            else:
                await call.message.answer(
                    "✅ Все задания выполнены! Вы уже получили награду.\n\n"
                    "🔄 Новые задания появятся позже.",
                    reply_markup=back_markup
                )
        else:
            # FlyerBot сам отправил пользователю задания
            # Показываем кнопку для повторной проверки
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(
                InlineKeyboardButton("✅ Я выполнил задания", callback_data="flyer_check"),
                create_back_button(user_id)
            )
            await call.message.answer(
                "📋 <b>Задания FlyerBot</b>\n\n"
                "Выполни задания спонсоров выше ☝️ и нажми кнопку проверки, чтобы получить награду ⭐",
                reply_markup=markup,
                parse_mode="HTML"
            )

    except Exception as e:
        log.exception(f"Error checking FlyerBot tasks for user {user_id}: {e}")
        back_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
        await call.message.answer(
            "❌ Произошла ошибка при загрузке заданий. Попробуйте позже.",
            reply_markup=back_markup
        )


async def handle_flyer_check(call: CallbackQuery, bot: Bot):
    """Обрабатывает кнопку 'Я выполнил задания' для FlyerBot."""
    user_id = call.from_user.id
    language_code = call.from_user.language_code or 'ru'

    try:
        await call.answer("🔄 Проверяю выполнение заданий...")
    except (InvalidQueryID, Exception):
        pass

    if not flyer:
        await call.answer("⚠️ Сервис временно недоступен", show_alert=True)
        return

    try:
        is_completed = await flyer.check(
            user_id,
            language_code=language_code
        )

        if is_completed:
            # Задания выполнены — начисляем награду
            reward_given = await _check_and_give_flyer_reward(user_id)

            back_markup = InlineKeyboardMarkup(row_width=1)
            back_markup.add(
                InlineKeyboardButton("🔄 Проверить ещё раз", callback_data="flyer_tasks"),
                create_back_button(user_id)
            )

            try:
                await call.message.delete()
            except (MessageCantBeDeleted, MessageToDeleteNotFound):
                pass

            if reward_given:
                await call.message.answer(
                    f"✅ Все задания выполнены! Награда начислена: {reward_given:.2f} ⭐",
                    reply_markup=back_markup
                )
            else:
                await call.message.answer(
                    "✅ Все задания выполнены! Вы уже получили награду.\n\n"
                    "🔄 Новые задания появятся позже.",
                    reply_markup=back_markup
                )
        else:
            # Не все задания выполнены
            try:
                await call.answer("❌ Не все задания выполнены! Подпишитесь на все каналы.", show_alert=True)
            except (InvalidQueryID, Exception):
                pass

    except Exception as e:
        log.exception(f"Error in handle_flyer_check for user {user_id}: {e}")
        try:
            await call.answer("❌ Ошибка проверки. Попробуйте позже.", show_alert=True)
        except (InvalidQueryID, Exception):
            pass


# --- Награда за задания FlyerBot ---

FLYER_TASK_REWARD = 1.0  # Награда за выполнение заданий FlyerBot (в звёздах)


async def _check_and_give_flyer_reward(user_id: int) -> float | None:
    """
    Проверяет, получал ли пользователь награду за задания FlyerBot сегодня.
    Если нет — начисляет и возвращает сумму награды.
    Если уже получал — возвращает None.
    """
    from datetime import datetime

    today = datetime.now().strftime('%Y-%m-%d')
    conn = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Проверяем таблицу (создаём если не существует)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flyer_completions (
                user_id INTEGER NOT NULL,
                completed_date TEXT NOT NULL,
                reward REAL NOT NULL,
                PRIMARY KEY (user_id, completed_date)
            )
        ''')

        # Проверяем, получал ли пользователь награду сегодня
        cursor.execute(
            'SELECT 1 FROM flyer_completions WHERE user_id = ? AND completed_date = ?',
            (user_id, today)
        )
        already_rewarded = cursor.fetchone()

        if already_rewarded:
            log.debug(f"User {user_id} already received FlyerBot reward today.")
            return None

        # Начисляем награду
        reward = FLYER_TASK_REWARD
        add_stars(user_id, reward)

        # Записываем в таблицу
        cursor.execute(
            'INSERT INTO flyer_completions (user_id, completed_date, reward) VALUES (?, ?, ?)',
            (user_id, today, reward)
        )
        conn.commit()

        log.info(f"User {user_id} completed FlyerBot tasks. Reward: {reward} stars.")
        return reward

    except Exception as e:
        log.exception(f"Error giving FlyerBot reward to user {user_id}: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()


# --- Регистрация обработчиков ---
def register_user_flyer_handlers(dp: Dispatcher, bot: Bot):
    """Регистрирует обработчики для заданий FlyerBot."""
    # Показ заданий FlyerBot
    dp.register_callback_query_handler(
        lambda call: show_flyer_tasks(call, bot),
        lambda c: c.data == "flyer_tasks",
        state="*"
    )
    # Проверка выполнения заданий FlyerBot
    dp.register_callback_query_handler(
        lambda call: handle_flyer_check(call, bot),
        lambda c: c.data == "flyer_check",
        state="*"
    )
    log.info("User FlyerBot task handlers registered.")
