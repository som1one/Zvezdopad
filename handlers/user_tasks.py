# Содержимое файла: handlers/user_tasks.py (Исправлен TypeError при вызове add_stars)
import logging
import sqlite3
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputFile
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID

# Импорты из проекта
from database import (
    get_tasks, user_completed_task, mark_task_completed,
    add_stars,  # <--- Эта функция НЕ принимает cursor
    is_lucky_time_now, get_channels_db,
    get_db_connection
)
from settings import CLICK_MIN_REWARD_X2, CLICK_MAX_REWARD_X2
from utils import t, create_temp_invite_link
from keyboards import create_back_button
from handlers.common import check_subscription
from handlers.user_menu import show_main_menu

log = logging.getLogger('handlers.user_tasks')


def get_tasks_for_user(user_id):
    """Получает список задач из БД, которые пользователь еще не выполнил."""
    all_tasks = get_tasks()
    user_tasks = []
    for task in all_tasks:
        task_id = task['id']
        if not user_completed_task(user_id, task_id):
            user_tasks.append(task)
    return user_tasks


async def show_tasks_handler(call: CallbackQuery, bot: Bot):
    """Отображает первое доступное задание пользователю."""
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    # Пытаемся ответить на коллбек, чтобы убрать "часики"
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"InvalidQueryID handling show_tasks for user {user_id}")
    except Exception as e:
        log.error(f"Error answering callback query in show_tasks: {e}")

    # Проверяем подписку на основные каналы
    if not await check_subscription(bot, user_id, chat_id):
        try:
            await call.answer(t(user_id, "not_subscribed"), show_alert=True)
        except InvalidQueryID:
            log.warning(f"InvalidQueryID showing 'not_subscribed' alert for user {user_id}")
        except Exception as e:
            log.error(f"Error answering 'not_subscribed' callback: {e}")
        # Удаляем сообщение с кнопками, если нет подписки
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        return

    available_tasks = get_tasks_for_user(user_id)
    back_button_markup = InlineKeyboardMarkup().add(create_back_button(user_id))
    image_path = "images/task.jpg"  # Путь к изображению для задач

    # Удаляем предыдущее сообщение (например, главное меню)
    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        log.debug(f"Could not delete previous message for user {user_id} in show_tasks.")
        pass

    # Если нет доступных заданий
    if not available_tasks:
        log.info(f"No available tasks found for user {user_id}.")
        # Добавляем кнопку FlyerBot заданий, даже если нет обычных
        no_tasks_markup = InlineKeyboardMarkup(row_width=1)
        from settings import FLYER_API_KEY
        if FLYER_API_KEY:
            no_tasks_markup.add(InlineKeyboardButton("📋 Задания спонсоров", callback_data="flyer_tasks"))
        no_tasks_markup.add(create_back_button(user_id))
        try:
            with open(image_path, "rb") as photo:
                await call.message.answer_photo(
                    photo=photo,
                    caption=t(user_id, 'no_tasks'),
                    reply_markup=no_tasks_markup
                )
        except FileNotFoundError:
            log.error(f"Task image file not found at: {image_path}")
            await call.message.answer(t(user_id, 'no_tasks'), reply_markup=no_tasks_markup)
        except Exception as e:
            log.exception(f"Error sending 'no tasks' message to user {user_id}: {e}")
        return

    # Берем первое доступное задание
    task = available_tasks[0]
    task_id = task['id']
    channel_id_or_link = task['channel_id']
    reward = task['reward']
    task_type = task['task_type']  # 'sub' или 'nosub'

    markup = InlineKeyboardMarkup(row_width=1)
    chat_title = "Задание"
    task_description = ""

    if task_type == "nosub":
        # Задание без проверки подписки (переход по ссылке)
        invite_link = str(channel_id_or_link)
        subscribe_btn_text = "🔗 Выполнить задание"
        check_btn_text = "✅ Забрать награду"

        if invite_link.startswith(('http://', 'https://', 't.me/')):
            markup.add(InlineKeyboardButton(subscribe_btn_text, url=invite_link))
        else:
            log.warning(f"Task {task_id} type 'nosub' has invalid URL: {invite_link}. Skipping subscribe button.")

        markup.add(InlineKeyboardButton(check_btn_text, callback_data=f"task_check:{task_id}"))
        task_description = "🔗 <b>Задание:</b> Перейти по ссылке"
        if not invite_link.startswith(('http://', 'https://', 't.me/')):
            task_description += " <small>(Ошибка: недействительная ссылка)</small>"

    else:  # task_type == "sub" (или по умолчанию считаем 'sub')
        # Задание с проверкой подписки
        try:
            channel_id = int(channel_id_or_link)
            invite_link = None
            chat_title = f"Канал/группа ID: {channel_id}"  # Default title

            # Пытаемся получить информацию о чате и ссылку
            try:
                chat = await bot.get_chat(channel_id)
                chat_title = chat.title or chat_title  # Use actual title if available
                invite_link = chat.invite_link  # Try to get existing invite link
                log.debug(
                    f"Task {task_id}: Got chat info for {channel_id}: '{escape(chat_title)}', link: {'Yes' if invite_link else 'No'}")
            except Exception as chat_err:
                log.warning(
                    f"Could not get chat info for channel {channel_id} (task {task_id}): {chat_err}. Will try creating link.")

            # Если не удалось получить ссылку, пробуем создать временную
            if not invite_link:
                try:
                    # Важно: бот должен быть админом с правом генерации ссылок в канале/группе!
                    invite_link_obj = await bot.create_chat_invite_link(channel_id, member_limit=1)
                    invite_link = invite_link_obj.invite_link
                    log.debug(f"Created temporary invite link for channel {channel_id} (task {task_id}).")
                except Exception as link_err:
                    log.error(
                        f"Failed to get or create invite link for channel {channel_id} (task {task_id}): {link_err}")

            # Формируем кнопку и описание
            if invite_link:
                subscribe_btn_text = f"✅ Подписаться на '{escape(chat_title[:20])}'"  # Limit title length
                markup.add(InlineKeyboardButton(subscribe_btn_text, url=invite_link))
                task_description = f"📢 <b>Канал/группа:</b> <a href='{invite_link}'>{escape(chat_title)}</a>"
            else:
                # Если ссылку так и не получили, показываем без кнопки подписки
                task_description = f"📢 <b>Канал/группа:</b> {escape(chat_title)} <small>(Ошибка: не удалось получить/создать ссылку)</small>"

            check_btn_text = "🔎 Проверить подписку"
            markup.add(InlineKeyboardButton(check_btn_text, callback_data=f"task_check:{task_id}"))

        except ValueError:
            # Если channel_id не число, обрабатываем как 'nosub'
            log.error(f"Invalid channel_id '{channel_id_or_link}' for 'sub' task {task_id}. Treating as 'nosub' link.")
            invite_link = str(channel_id_or_link)
            subscribe_btn_text = "🔗 Выполнить задание"
            check_btn_text = "✅ Забрать награду"
            if invite_link.startswith(('http://', 'https://', 't.me/')):
                markup.add(InlineKeyboardButton(subscribe_btn_text, url=invite_link))
            else:
                log.warning(f"Invalid URL for 'nosub' (fallback from sub) task {task_id}: {invite_link}.")
            markup.add(InlineKeyboardButton(check_btn_text, callback_data=f"task_check:{task_id}"))
            task_description = "🔗 <b>Задание:</b> Перейти по ссылке"
            if not invite_link.startswith(('http://', 'https://', 't.me/')):
                task_description += " <small>(Ошибка: ссылка недействительна)</small>"

    # Добавляем кнопку FlyerBot заданий и "Назад" ко всем заданиям
    from settings import FLYER_API_KEY
    if FLYER_API_KEY:
        markup.add(InlineKeyboardButton("📋 Ещё задания", callback_data="flyer_tasks"))
    markup.add(create_back_button(user_id))

    # Формируем полный текст сообщения
    task_message_text = (
        f"✨ <b>Новое задание!</b> ✨\n\n"
        f"{task_description}\n"
        f"💎 <b>Награда:</b> {reward:.2f} ⭐\n\n"
        f"📌 Выполни задание и нажми кнопку ниже, чтобы получить награду."
    )

    # Отправляем сообщение с заданием (с фото или без)
    try:
        with open(image_path, "rb") as photo:
            await call.message.answer_photo(
                photo=photo,
                caption=task_message_text,
                reply_markup=markup,
                parse_mode="HTML"
            )
    except FileNotFoundError:
        log.error(f"Task image file not found at: {image_path}. Sending text only.")
        await call.message.answer(
            task_message_text,
            reply_markup=markup,
            parse_mode="HTML"
        )
    except Exception as e:
        log.exception(f"Error sending task message (photo/text) to user {user_id}: {e}")


async def handle_task_check(call: CallbackQuery, bot: Bot):
    """Обрабатывает кнопку проверки выполнения задания."""
    user_id = call.from_user.id
    try:
        task_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        log.error(f"Invalid task check callback data for user {user_id}: {call.data}")
        await call.answer("Ошибка данных задания.", show_alert=True)
        return

    log.info(f"User {user_id} checking task {task_id}")

    # Отвечаем на коллбек
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"InvalidQueryID handling task_check for user {user_id}, task {task_id}")
        # Не возвращаем return, пробуем продолжить
    except Exception as e:
        log.error(f"Error answering callback query in handle_task_check: {e}")
        return  # Возвращаем, т.к. неизвестная ошибка

    task_data = None
    conn = None
    # Получаем данные задания из БД
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id=? AND active=1", (task_id,))
        task_data = cursor.fetchone()  # Возвращает dict или None
    except Exception as e:
        log.exception(f"Database error fetching task {task_id} for user {user_id}: {e}")
        await bot.send_message(user_id, "Произошла ошибка при получении данных задания. Попробуйте позже.")
        return
    finally:
        if conn:
            conn.close()

    # Проверяем, найдено ли задание
    if not task_data:
        log.warning(f"Task {task_id} not found or inactive when checked by user {user_id}.")
        await bot.send_message(user_id, "Это задание больше неактивно или не найдено.")
        # Попробуем показать следующее задание, если есть
        try:
            await show_tasks_handler(call, bot)
        except Exception as show_err:
            log.error(f"Error showing next task after task {task_id} not found: {show_err}")
        return

    # Извлекаем данные задания
    channel_id_or_link = task_data['channel_id']
    reward = task_data['reward']
    completed_count = task_data['completed_count']
    max_completions = task_data['max_completions']
    requires_subscription = task_data['requires_subscription']  # Устарело, но оставим для совместимости
    task_type = task_data['task_type']

    # Проверяем, не выполнил ли пользователь уже это задание
    if user_completed_task(user_id, task_id):
        log.info(f"User {user_id} tried to check already completed task {task_id}.")
        await bot.send_message(user_id, "Вы уже выполнили это задание!")
        # Показываем следующее задание
        try:
            await show_tasks_handler(call, bot)
        except Exception as show_err:
            log.error(f"Error showing next task after task {task_id} already completed: {show_err}")
        return

    # Проверяем лимит выполнений задания
    if completed_count >= max_completions:
        log.info(
            f"Task {task_id} completion limit reached ({completed_count}/{max_completions}). User {user_id} check failed.")
        await bot.send_message(user_id, "К сожалению, лимит выполнений для этого задания исчерпан.")
        # Опционально: можно добавить логику деактивации задания в БД
        # try:
        #     with get_db_connection() as conn_deact:
        #         conn_deact.execute("UPDATE tasks SET active = 0 WHERE id=?", (task_id,))
        #         conn_deact.commit()
        #         log.info(f"Deactivated task {task_id} due to limit reached.")
        # except Exception as deact_err:
        #     log.error(f"Failed to automatically deactivate task {task_id}: {deact_err}")
        # Показываем следующее задание
        try:
            await show_tasks_handler(call, bot)
        except Exception as show_err:
            log.error(f"Error showing next task after task {task_id} limit reached: {show_err}")
        return

    # Проверяем выполнение условия (подписка или просто переход)
    task_passed = False
    if task_type == "nosub":
        task_passed = True  # Для 'nosub' сам факт нажатия кнопки проверки достаточен
        log.info(f"Task {task_id} (type 'nosub') passed for user {user_id} upon check.")
    elif task_type == "sub":
        try:
            channel_id = int(channel_id_or_link)
            chat_member = await bot.get_chat_member(channel_id, user_id)
            # Проверяем статус участника
            if chat_member.status in ['member', 'administrator', 'creator']:
                task_passed = True
                log.info(f"User {user_id} IS subscribed to channel {channel_id} (task {task_id}). Check passed.")
            else:
                log.info(
                    f"User {user_id} NOT subscribed to channel {channel_id} (task {task_id}). Status: {chat_member.status}. Check failed.")
                await bot.send_message(user_id,
                                       f"❌ Вы не подписаны на канал/группу задания! Пожалуйста, подпишитесь и нажмите кнопку проверки снова.")
                # Не показываем следующее задание, даем шанс подписаться
                return
        except ValueError:
            log.error(f"Invalid channel_id '{channel_id_or_link}' in DB for 'sub' task {task_id} during check.")
            await bot.send_message(user_id, "Ошибка проверки задания: неверный ID канала. Обратитесь в поддержку.")
            return
        except Exception as e:
            log.error(
                f"Error checking subscription for user {user_id}, channel {channel_id_or_link}, task {task_id}: {e}")
            await bot.send_message(user_id,
                                   "Не удалось проверить вашу подписку. Пожалуйста, попробуйте еще раз через некоторое время.")
            return
    else:
        log.warning(f"Unknown task_type '{task_type}' for task {task_id}. Assuming passed.")
        task_passed = True  # На всякий случай засчитываем неизвестные типы

    # Если задание пройдено, начисляем награду и отмечаем выполнение
    if task_passed:
        final_reward = reward  # В будущем можно добавить модификаторы (x2 и т.д.)
        try:
            # --- ИСПРАВЛЕНИЕ: Убран cursor из add_stars ---
            add_stars(user_id, final_reward)
            mark_task_completed(user_id, task_id)
            # -------------------------------------------

            # Обновляем счетчик выполнений задания ОТДЕЛЬНОЙ транзакцией
            # Это менее критично, чем начисление награды, делаем после
            try:
                with get_db_connection() as conn_count:
                    cursor_count = conn_count.cursor()
                    cursor_count.execute("UPDATE tasks SET completed_count = completed_count + 1 WHERE id = ?",
                                         (task_id,))
                    conn_count.commit()
                log.info(f"Incremented completed_count for task {task_id}.")
            except Exception as count_err:
                log.error(f"Failed to increment completed_count for task {task_id}: {count_err}")
                # Не фатально, продолжаем

            log.info(
                f"Task {task_id} successfully completed by user {user_id}. Awarded {final_reward:.2f} stars. Task marked completed.")
            await bot.send_message(user_id, f"✅ Задание выполнено! Вы получили {final_reward:.2f} ⭐!")

            # Показываем следующее доступное задание
            try:
                await show_tasks_handler(call, bot)
            except Exception as show_err:
                log.error(f"Error showing next task after task {task_id} completion: {show_err}")

        except Exception as e:
            # Ошибка при начислении звезд или отметке выполнения
            log.exception(f"CRITICAL: Error finalizing task {task_id} completion for user {user_id}: {e}")
            # Важно уведомить пользователя и, возможно, админа
            await bot.send_message(user_id,
                                   "Произошла критическая ошибка при зачислении награды за задание! Пожалуйста, свяжитесь с поддержкой, указав ID задания: {task_id}.")



# --- Регистрация обработчиков ---
def register_user_task_handlers(dp: Dispatcher, bot: Bot):
    """Регистрирует обработчики для раздела заданий."""
    # Показ списка/первого задания
    dp.register_callback_query_handler(
        lambda call: show_tasks_handler(call, bot),
        lambda c: c.data == "tasks",
        state="*"
    )
    # Проверка выполнения задания
    dp.register_callback_query_handler(
        lambda call: handle_task_check(call, bot),
        lambda c: c.data.startswith("task_check:"),
        state="*"
    )
    log.info("User task handlers registered successfully.")
