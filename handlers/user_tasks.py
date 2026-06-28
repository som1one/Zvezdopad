import logging
import asyncpg
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputFile
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID

import database  # <-- Наш async database
from settings import CLICK_MIN_REWARD_X2, CLICK_MAX_REWARD_X2
from utils import t, create_temp_invite_link  # create_temp_invite_link тоже должен стать async
from keyboards import create_back_button
from handlers.common import check_subscription  # check_subscription стала async
from handlers.user_menu import show_main_menu

log = logging.getLogger('handlers.user_tasks')


async def get_tasks_for_user(user_id: int) -> list[asyncpg.Record]:  # Возвращает список asyncpg.Record
    all_tasks = await database.get_tasks()  # await
    user_tasks = []
    for task in all_tasks:
        task_id = task['id']
        if not await database.user_completed_task(user_id, task_id):  # await
            user_tasks.append(task)
    return user_tasks


async def show_tasks_handler(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"InvalidQueryID handling show_tasks for user {user_id}")
    except Exception as e:
        log.error(f"Error answering callback query in show_tasks: {e}")

    if not await check_subscription(bot, user_id, chat_id):  # await
        try:
            await call.answer(t(user_id, "not_subscribed"), show_alert=True)
        except InvalidQueryID:
            log.warning(f"InvalidQueryID showing 'not_subscribed' alert for user {user_id}")
        except Exception as e:
            log.error(f"Error answering 'not_subscribed' callback: {e}")
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        return

    available_tasks = await get_tasks_for_user(user_id)  # await
    back_button_markup = InlineKeyboardMarkup(row_width=1)
    back_button_markup.add(InlineKeyboardButton("📋 Задания спонсоров", callback_data="flyer_tasks"))
    back_button_markup.add(create_back_button(user_id))
    image_path = "images/task.jpg"

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        log.debug(f"Could not delete previous message user {user_id} in show_tasks.")

    if not available_tasks:
        log.info(f"No available tasks found for user {user_id}.")
        try:
            with open(image_path, "rb") as photo:
                await call.message.answer_photo(photo=photo, caption=t(user_id, 'no_tasks'),
                                                reply_markup=back_button_markup)
        except FileNotFoundError:
            log.error(f"Task image file not found at: {image_path}")
            await call.message.answer(t(user_id, 'no_tasks'), reply_markup=back_button_markup)
        except Exception as e:
            log.exception(f"Error sending 'no tasks' message to user {user_id}: {e}")
        return

    task = available_tasks[0]
    task_id = task['id']
    channel_id_or_link = task['channel_id']
    reward = task['reward']
    task_type = task['task_type']

    markup = InlineKeyboardMarkup(row_width=1)
    chat_title = "Задание"
    task_description = ""

    if task_type == "nosub":
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
    else:  # task_type == "sub"
        try:
            channel_id = int(channel_id_or_link)
            invite_link = None
            chat_title = f"Канал/группа ID: {channel_id}"
            try:
                chat = await bot.get_chat(channel_id)
                chat_title = chat.title or chat_title
                invite_link = chat.invite_link
                log.debug(
                    f"Task {task_id}: Got chat info for {channel_id}: '{escape(chat_title)}', link: {'Yes' if invite_link else 'No'}")
            except Exception as chat_err:
                log.warning(
                    f"Could not get chat info for channel {channel_id} (task {task_id}): {chat_err}. Will try creating link.")

            if not invite_link:
                try:
                    # create_temp_invite_link должна стать async, если ее нет
                    # invite_link = await create_temp_invite_link(bot, channel_id)
                    invite_link_obj = await bot.create_chat_invite_link(channel_id,
                                                                        member_limit=1)  # Используем aiogram напрямую
                    invite_link = invite_link_obj.invite_link
                    log.debug(f"Created temporary invite link for channel {channel_id} (task {task_id}).")
                except Exception as link_err:
                    log.error(
                        f"Failed to get or create invite link for channel {channel_id} (task {task_id}): {link_err}")

            if invite_link:
                subscribe_btn_text = f"✅ Подписаться на '{escape(chat_title[:20])}'"
                markup.add(InlineKeyboardButton(subscribe_btn_text, url=invite_link))
                task_description = f"📢 <b>Канал/группа:</b> <a href='{invite_link}'>{escape(chat_title)}</a>"
            else:
                task_description = f"📢 <b>Канал/группа:</b> {escape(chat_title)} <small>(Ошибка: не удалось получить/создать ссылку)</small>"

            check_btn_text = "🔎 Проверить подписку"
            markup.add(InlineKeyboardButton(check_btn_text, callback_data=f"task_check:{task_id}"))
        except ValueError:
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

    markup.add(InlineKeyboardButton("📋 Ещё задания", callback_data="flyer_tasks"))
    markup.add(create_back_button(user_id))
    task_message_text = (
        f"✨ <b>Новое задание!</b> ✨\n\n"
        f"{task_description}\n"
        f"💎 <b>Награда:</b> {reward:.2f} ⭐\n\n"
        f"📌 Выполни задание и нажми кнопку ниже, чтобы получить награду."
    )

    try:
        with open(image_path, "rb") as photo:
            await call.message.answer_photo(photo=photo, caption=task_message_text, reply_markup=markup,
                                            parse_mode="HTML")
    except FileNotFoundError:
        log.error(f"Task image file not found at: {image_path}. Sending text only.")
        await call.message.answer(task_message_text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        log.exception(f"Error sending task message (photo/text) to user {user_id}: {e}")


async def handle_task_check(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    try:
        task_id = int(call.data.split(":")[1])
    except (IndexError, ValueError):
        log.error(f"Invalid task check callback data for user {user_id}: {call.data}")
        await call.answer("Ошибка данных задания.", show_alert=True);
        return

    log.info(f"User {user_id} checking task {task_id}")

    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"InvalidQueryID handling task_check for user {user_id}, task {task_id}")
    except Exception as e:
        log.error(f"Error answering callback query in handle_task_check: {e}"); return

    task_data = None
    pool = database.db_pool
    if not pool: log.error("DB pool not initialized!"); await bot.send_message(user_id, "Ошибка БД."); return

    async with pool.acquire() as conn:
        try:
            task_data = await conn.fetchrow("SELECT * FROM tasks WHERE id=$1 AND active=1", task_id)  # await
        except Exception as e:
            log.exception(f"Database error fetching task {task_id} for user {user_id}: {e}")
            await bot.send_message(user_id, "Ошибка при получении данных задания.");
            return

    if not task_data:
        log.warning(f"Task {task_id} not found or inactive when checked by user {user_id}.")
        await bot.send_message(user_id, "Это задание больше неактивно или не найдено.")
        try:
            await show_tasks_handler(call, bot)  # await
        except Exception as show_err:
            log.error(f"Error showing next task after task {task_id} not found: {show_err}")
        return

    channel_id_or_link = task_data['channel_id']
    reward = task_data['reward']
    completed_count = task_data['completed_count']
    max_completions = task_data['max_completions']
    task_type = task_data['task_type']

    if await database.user_completed_task(user_id, task_id):  # await
        log.info(f"User {user_id} tried to check already completed task {task_id}.")
        await bot.send_message(user_id, "Вы уже выполнили это задание!")
        try:
            await show_tasks_handler(call, bot)  # await
        except Exception as show_err:
            log.error(f"Error showing next task after task {task_id} already completed: {show_err}")
        return

    if completed_count >= max_completions:
        log.info(
            f"Task {task_id} completion limit reached ({completed_count}/{max_completions}). User {user_id} check failed.")
        await bot.send_message(user_id, "Лимит выполнений для этого задания исчерпан.")
        try:
            await show_tasks_handler(call, bot)  # await
        except Exception as show_err:
            log.error(f"Error showing next task after task {task_id} limit reached: {show_err}")
        return

    task_passed = False
    if task_type == "nosub":
        task_passed = True
        log.info(f"Task {task_id} (type 'nosub') passed for user {user_id} upon check.")
    elif task_type == "sub":
        try:
            channel_id = int(channel_id_or_link)
            chat_member = await bot.get_chat_member(channel_id, user_id)
            if chat_member.status in ['member', 'administrator', 'creator']:
                task_passed = True
                log.info(f"User {user_id} IS subscribed to channel {channel_id} (task {task_id}). Check passed.")
            else:
                log.info(
                    f"User {user_id} NOT subscribed to channel {channel_id} (task {task_id}). Status: {chat_member.status}. Check failed.")
                await bot.send_message(user_id,
                                       f"❌ Вы не подписаны на канал/группу задания! Подпишитесь и проверьте снова.")
                return
        except ValueError:
            log.error(f"Invalid channel_id '{channel_id_or_link}' in DB for 'sub' task {task_id} during check.")
            await bot.send_message(user_id, "Ошибка проверки: неверный ID канала.");
            return
        except Exception as e:
            log.error(f"Error checking subscription user {user_id}, channel {channel_id_or_link}, task {task_id}: {e}")
            await bot.send_message(user_id, "Не удалось проверить подписку. Попробуйте позже.");
            return
    else:
        log.warning(f"Unknown task_type '{task_type}' for task {task_id}. Assuming passed.")
        task_passed = True

    if task_passed:
        final_reward = reward
        try:
            await database.add_stars(user_id, final_reward)  # await
            await database.mark_task_completed(user_id, task_id)  # await

            # Обновляем счетчик выполнений задачи ВНЕ транзакции mark_task_completed
            pool_count = database.db_pool
            if pool_count:
                async with pool_count.acquire() as conn_count:
                    try:
                        await conn_count.execute('UPDATE tasks SET completed_count = completed_count + 1 WHERE id = $1',
                                                 task_id)
                    except Exception as count_err:
                        log.error(f"Failed increment completed_count task {task_id}: {count_err}")
            else:
                log.error("DB pool not available for incrementing task count.")

            log.info(f"Task {task_id} completed user {user_id}. Awarded {final_reward:.2f} stars.")
            await bot.send_message(user_id, f"✅ Задание выполнено! Вы получили {final_reward:.2f} ⭐!")
            try:
                await show_tasks_handler(call, bot)  # await
            except Exception as show_err:
                log.error(f"Error showing next task after task {task_id} completion: {show_err}")

        except Exception as e:
            log.exception(f"CRITICAL: Error finalizing task {task_id} completion for user {user_id}: {e}")
            await bot.send_message(user_id, f"Критическая ошибка зачисления награды! Поддержка ID задания: {task_id}.")


def register_user_task_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(lambda call: show_tasks_handler(call, bot), lambda c: c.data == "tasks",
                                       state="*")
    dp.register_callback_query_handler(lambda call: handle_task_check(call, bot),
                                       lambda c: c.data.startswith("task_check:"), state="*")
    log.info("User task handlers registered successfully.")
