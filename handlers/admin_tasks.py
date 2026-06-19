# Содержимое файла: handlers/admin_tasks.py (Адаптировано для asyncpg)
import logging
import asyncpg  # <-- Добавлено
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, MessageNotModified

import database  # Наш async database
from settings import ADMIN_IDS
from utils import t, create_temp_invite_link
from keyboards import create_admin_cancel_markup
from states import AdminAddTaskState, AdminRemoveTaskState

log = logging.getLogger('handlers.admin_tasks')


async def add_task_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("✅ С проверкой подписки (канал/группа)", callback_data="task_type:sub"))
    markup.add(InlineKeyboardButton("🔗 Без проверки подписки (ссылка)", callback_data="task_type:nosub"))
    markup.add(InlineKeyboardButton("❌ Отмена", callback_data="adminpanel"))
    await call.message.edit_text("Выберите тип задания:", reply_markup=markup)
    await AdminAddTaskState.waiting_for_task_type.set()


async def add_task_type_selected(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    try:
        task_type = call.data.split(":")[1]
    except IndexError:
        return
    await state.update_data(task_type=task_type)
    markup = create_admin_cancel_markup()
    prompt = "Введите ID канала/чата:" if task_type == "sub" else "Введите URL ссылки:"
    await call.message.edit_text(prompt, reply_markup=markup)
    await AdminAddTaskState.waiting_for_channel_id.set()


async def add_task_channel_input(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    channel_id_or_link = message.text.strip()
    data = await state.get_data()
    task_type = data.get('task_type')
    if task_type == "sub":
        try:
            channel_id = int(channel_id_or_link)
        except ValueError:
            await message.reply("❌ Введите корректный числовой ID.", reply_markup=markup); return
    elif task_type == "nosub":
        if not (channel_id_or_link.startswith('http://') or channel_id_or_link.startswith(
            'https://')): await message.reply("❌ URL должен начинаться с http:// или https://",
                                              reply_markup=markup); return
    else:
        await message.reply("❗ Ошибка типа. Начните заново.", reply_markup=markup); await state.finish(); return
    await state.update_data(channel_id_or_link=channel_id_or_link)
    await message.answer("💰 Введите награду (число, например 0.5):", reply_markup=markup)
    await AdminAddTaskState.waiting_for_reward.set()


async def add_task_reward_input(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    try:
        reward = float(message.text.strip())
        if reward <= 0: raise ValueError("Reward must be positive")
    except ValueError:
        await message.reply("❌ Введите корректное полож. число.", reply_markup=markup); return
    await state.update_data(reward=reward)
    await message.answer("🎯 Введите макс. кол-во выполнений (лимит):", reply_markup=markup)
    await AdminAddTaskState.waiting_for_max_completions.set()


async def add_task_max_completions_input(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    try:
        max_completions = int(message.text.strip())
    except ValueError:
        await message.reply("❌ Введите корректное целое число.", reply_markup=markup); return
    data = await state.get_data()
    task_type = data.get('task_type');
    channel_id_or_link = data.get('channel_id_or_link');
    reward = data.get('reward')
    if not all([task_type, channel_id_or_link, reward]): await message.reply("❗ Ошибка данных. Попробуйте снова.",
                                                                             reply_markup=markup); await state.finish(); return
    requires_subscription_flag = (task_type == "sub")
    try:
        await database.add_task(channel_id_or_link, reward, max_completions,
                                requires_subscription=requires_subscription_flag)  # await
        log.info(
            f"Admin {message.from_user.id} added task: type={task_type}, target='{channel_id_or_link}', reward={reward}, limit={max_completions}")
        await message.answer(f"✅ Задание типа '{task_type}' добавлено!", reply_markup=markup)
    except Exception as e:
        log.exception(f"Error adding task DB: {e}"); await message.answer(f"❌ Ошибка БД: {e}", reply_markup=markup)
    await state.finish()


async def remove_task_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = create_admin_cancel_markup()
    await call.message.edit_text("Введите ID канала/чата или URL ссылки для удаления:", reply_markup=markup)
    await AdminRemoveTaskState.waiting_for_channel_id.set()


async def remove_task_channel_input(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    channel_id_or_link = message.text.strip()
    try:
        success = await database.remove_task(channel_id_or_link)  # await
        if success:
            log.info(f"Admin {message.from_user.id} removed task assoc. with '{channel_id_or_link}'")
            await message.answer(f"✅ Задание для '{escape(channel_id_or_link)}' удалено.",
                                 reply_markup=markup)  # escape()
        else:
            await message.reply(f"❌ Задание для '{escape(channel_id_or_link)}' не найдено.",
                                reply_markup=markup)  # escape()
    except Exception as e:
        log.exception(f"Error removing task admin {message.from_user.id}: {e}")
        await message.answer(f"❌ Ошибка удаления: {e}", reply_markup=markup)
    await state.finish()


async def show_tasks_list(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    tasks = []
    try:
        tasks = await database.get_tasks()  # await
    except Exception as e:
        log.exception("Error fetching task list DB"); await call.message.edit_text("Ошибка загрузки.",
                                                                                   reply_markup=create_admin_cancel_markup()); return

    markup = InlineKeyboardMarkup(row_width=1)
    message_text = "<b>Список всех заданий:</b>\n(Нажмите для удаления)\n\n"
    cancel_markup = create_admin_cancel_markup()

    if not tasks:
        message_text += "<i>Заданий нет.</i>"
    else:
        for task in tasks:
            task_id, ch_id, reward, active, task_type, completed, limit = task['id'], task['channel_id'], task[
                'reward'], task['active'], task['task_type'], task['completed_count'], task['max_completions']
            status = "🟩 Активно" if active else "🟥 Неактивно"
            type_str = "Ссылка" if task_type == "nosub" else "Канал/Чат"
            target_str = str(ch_id)
            display_target = target_str[:25] + ('...' if len(target_str) > 25 else '')
            button_text = f"{status} | {type_str}: {display_target} | {reward}⭐️ | {completed}/{limit} | ❌"
            markup.add(InlineKeyboardButton(button_text, callback_data=f"delete_task_btn_{task_id}"))

    if cancel_markup.inline_keyboard:
        for row in cancel_markup.inline_keyboard: markup.row(*row)
    try:
        await call.message.edit_text(message_text, reply_markup=markup, parse_mode="HTML",
                                     disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except Exception as e:
        log.error(f"Error editing message task list: {e}")


async def delete_task_from_list(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: await call.answer("Нет доступа!", show_alert=True); return
    try:
        task_id_to_delete = int(call.data.split("_")[-1])
    except (ValueError, IndexError):
        await call.answer("Ошибка ID.", show_alert=True); return

    task_info = None
    pool = database.db_pool
    if pool:
        async with pool.acquire() as conn:
            task_info = await conn.fetchrow("SELECT channel_id FROM tasks WHERE id = $1", task_id_to_delete)  # await
    else:
        log.error("DB pool not initialized!"); await call.answer("Ошибка БД.", show_alert=True); return

    if not task_info: await call.answer(f"Задание {task_id_to_delete} не найдено.",
                                        show_alert=True); await show_tasks_list(call, bot); return

    try:
        success = await database.remove_task(task_info['channel_id'])  # await
        if success:
            log.info(f"Admin {admin_id} deleted task {task_id_to_delete} from list.")
            await call.answer(f"Задание {task_id_to_delete} удалено.", show_alert=False)
        else:
            log.warning(f"Admin {admin_id} tried delete task {task_id_to_delete} not found by remove_task.")
            await call.answer(f"Задание {task_id_to_delete} не найдено (возможно, уже удалено).", show_alert=True)
        await show_tasks_list(call, bot)  # await
    except Exception as e:
        log.exception(f"Error deleting task {task_id_to_delete} from list: {e}")
        await call.answer("Ошибка при удалении.", show_alert=True)


async def show_tasks_progress(call: types.CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    active_tasks = await database.get_tasks()  # await
    markup = InlineKeyboardMarkup(row_width=1)
    cancel_markup = create_admin_cancel_markup()

    if not active_tasks:
        if cancel_markup.inline_keyboard:
            for row in cancel_markup.inline_keyboard: markup.row(*row)
        await call.message.edit_text("Нет активных задач.", reply_markup=markup);
        return

    response = "<b>Прогресс выполнения активных задач:</b>\n\n"
    for task in active_tasks:
        task_id, channel_id_str, reward, completed, limit, task_type = task['id'], task['channel_id'], task['reward'], \
        task['completed_count'], task['max_completions'], task['task_type']
        target_name = str(channel_id_str)
        if task_type == 'sub':
            try:
                chat = await bot.get_chat(int(channel_id_str))
                target_name = f"{escape(chat.title)} ({channel_id_str})"
            except ValueError:
                target_name = f"Ошибка ID: {escape(channel_id_str)}"
            except Exception:
                target_name = f"Канал/Чат ({channel_id_str})"

        progress_percent = (completed / limit * 100) if limit > 0 else 0
        response += f"📌 <b>{target_name[:30]}...</b>\n   💰{reward:.2f}⭐️ | 📊{completed}/{limit} ({progress_percent:.1f}%)\n\n"

    if cancel_markup.inline_keyboard:
        for row in cancel_markup.inline_keyboard: markup.row(*row)

    try:
        await call.message.edit_text(response, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except Exception as e:
        log.error(f"Error editing message task progress: {e}")


def register_admin_task_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(add_task_start, lambda c: c.data == "admin_add_task", state="*")
    dp.register_callback_query_handler(add_task_type_selected, state=AdminAddTaskState.waiting_for_task_type)
    dp.register_message_handler(add_task_channel_input, state=AdminAddTaskState.waiting_for_channel_id)
    dp.register_message_handler(add_task_reward_input, state=AdminAddTaskState.waiting_for_reward)
    dp.register_message_handler(add_task_max_completions_input, state=AdminAddTaskState.waiting_for_max_completions)
    dp.register_callback_query_handler(remove_task_start, lambda c: c.data == "admin_remove_task", state="*")
    dp.register_message_handler(remove_task_channel_input, state=AdminRemoveTaskState.waiting_for_channel_id)
    dp.register_callback_query_handler(lambda call: show_tasks_list(call, bot), lambda c: c.data == "show_tasks",
                                       state="*")
    dp.register_callback_query_handler(lambda call: delete_task_from_list(call, bot),
                                       lambda c: c.data.startswith("delete_task_btn_"), state="*")
    dp.register_callback_query_handler(lambda call: show_tasks_progress(call, bot), lambda c: c.data == "taskslist",
                                       state="*")
    log.info("Admin task management handlers registered.")
