# Содержимое файла: handlers/admin_op.py (Адаптировано для asyncpg)
import logging
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified

import database  # Наш async database
from settings import ADMIN_IDS
from utils import t
from keyboards import create_admin_cancel_markup
from states import ButtonState

log = logging.getLogger('handlers.admin_op')


async def op_menu(callback_query: CallbackQuery):
    if callback_query.from_user.id not in ADMIN_IDS: return
    await callback_query.answer()
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("➕ Добавить кнопку", callback_data="add_noop"))
    markup.add(InlineKeyboardButton("❌ Удалить кнопку", callback_data="dell_noop"))
    markup.add(InlineKeyboardButton("👁️ Посмотреть все кнопки", callback_data="view_noop"))
    cancel_markup = create_admin_cancel_markup()
    if cancel_markup.inline_keyboard:
        for row in cancel_markup.inline_keyboard: markup.row(*row)

    try:
        await callback_query.message.edit_text("Управление кнопками 'ОП без проверки':", reply_markup=markup)
    except MessageNotModified:
        pass
    except Exception as e:
        log.error(f"Error editing op_menu message: {e}")


async def view_noop_buttons(callback_query: CallbackQuery, bot: Bot):
    if callback_query.from_user.id not in ADMIN_IDS: return
    await callback_query.answer()
    buttons = await database.get_sponsor_buttons()  # await

    markup = InlineKeyboardMarkup(row_width=1)
    cancel_markup = create_admin_cancel_markup()  # Кнопка "Назад"

    if not buttons:
        message_text = "Нет добавленных кнопок 'ОП без проверки'."
    else:
        message_text = "<b>Список кнопок 'ОП без проверки':</b>\n(Нажмите для удаления)\n\n"
        for btn_data in buttons:
            name = btn_data['name']
            url = btn_data['url']
            callback_data = f"delete_op_btn_{name}_url_{url}"
            display_text = f"{escape(name)} ({escape(url)[:30]}...) ❌"
            markup.add(InlineKeyboardButton(display_text, callback_data=callback_data))

    markup.add(InlineKeyboardButton("➕ Добавить кнопку", callback_data="add_noop"))
    if cancel_markup.inline_keyboard:
        for row in cancel_markup.inline_keyboard: markup.row(*row)  # Добавляем кнопку назад

    try:
        await callback_query.message.edit_text(message_text, reply_markup=markup, parse_mode="HTML",
                                               disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except Exception as e:
        log.error(f"Error editing view_noop_buttons message: {e}")


async def delete_op_button_from_list(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: await call.answer("Нет доступа!", show_alert=True); return

    try:
        data_part = call.data[len("delete_op_btn_"):]
        name, url = data_part.split("_url_", 1)
    except (IndexError, ValueError):
        await call.answer("Ошибка данных кнопки.", show_alert=True); log.error(
            f"Could not parse delete_op_btn callback data: {call.data}"); return

    try:
        deleted = await database.remove_sponsor_button(name, url)  # await
        if deleted:
            log.info(f"Admin {admin_id} deleted OP button: name='{name}', url='{url}'")
            await call.answer(f"Кнопка '{escape(name)}' удалена.", show_alert=False)
        else:
            log.warning(f"Admin {admin_id} tried to delete non-existent OP button: name='{name}', url='{url}'")
            await call.answer(f"Кнопка '{escape(name)}' не найдена.", show_alert=True)
        await view_noop_buttons(call, bot)  # await
    except Exception as e:
        log.exception(f"Error deleting OP button '{name}': {e}")
        await call.answer("Ошибка при удалении кнопки.", show_alert=True)


async def add_noop_start(callback_query: CallbackQuery):
    if callback_query.from_user.id not in ADMIN_IDS: return
    await callback_query.answer()
    markup = create_admin_cancel_markup()
    await callback_query.message.edit_text("Введите название и URL кнопки (НАЗВАНИЕ:URL):", reply_markup=markup)
    await ButtonState.adding.set()


async def delete_noop_start(callback_query: CallbackQuery):
    if callback_query.from_user.id not in ADMIN_IDS: return
    await callback_query.answer()
    markup = create_admin_cancel_markup()
    await callback_query.message.edit_text("Введите точное название и URL кнопки для удаления (НАЗВАНИЕ:URL):",
                                           reply_markup=markup)
    await ButtonState.removing.set()


async def handle_add_op_button_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    if ':' not in message.text: await message.reply("❌ Неверный формат. Используйте: <code>НАЗВАНИЕ:URL</code>",
                                                    reply_markup=markup, parse_mode="HTML"); return

    name, url = message.text.split(":", 1)
    name = name.strip();
    url = url.strip()
    if not name or not url or not (url.startswith('http') or url.startswith('tg')): await message.reply(
        "❌ Название/URL не могут быть пустыми, URL должен начинаться с http или tg.", reply_markup=markup); return

    try:
        await database.add_sponsor_button(name, url)  # await
        log.info(f"Admin {admin_id} added OP button: name='{name}', url='{url}'")
        await message.answer(f"✅ Кнопка '{escape(name)}' добавлена.", reply_markup=markup)
        await state.finish()
    except Exception as e:
        log.exception(f"Error adding OP button admin {admin_id}: {e}")
        await message.answer("❌ Ошибка при добавлении кнопки.", reply_markup=markup);
        await state.finish()


async def handle_remove_op_button_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    if ':' not in message.text: await message.reply("❌ Неверный формат. Используйте: <code>НАЗВАНИЕ:URL</code>",
                                                    reply_markup=markup, parse_mode="HTML"); return

    name, url = message.text.split(":", 1)
    name = name.strip();
    url = url.strip()
    if not name or not url: await message.reply("❌ Название и URL не могут быть пустыми.", reply_markup=markup); return

    try:
        deleted = await database.remove_sponsor_button(name, url)  # await
        log.info(f"Admin {admin_id} attempted remove OP button: name='{name}', url='{url}'")
        if deleted:
            await message.answer(f"✅ Кнопка '{escape(name)}' удалена.", reply_markup=markup)
        else:
            await message.answer(f"ℹ️ Кнопка '{escape(name)}' с URL '{escape(url)}' не найдена.", reply_markup=markup)
        await state.finish()
    except Exception as e:
        log.exception(f"Error removing OP button admin {admin_id}: {e}")
        await message.answer("❌ Ошибка при удалении кнопки.", reply_markup=markup);
        await state.finish()


def register_admin_op_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(op_menu, lambda c: c.data == "op", state="*")
    dp.register_callback_query_handler(lambda call: view_noop_buttons(call, bot), lambda c: c.data == "view_noop",
                                       state="*")
    dp.register_callback_query_handler(add_noop_start, lambda c: c.data == "add_noop", state="*")
    dp.register_callback_query_handler(delete_noop_start, lambda c: c.data == "dell_noop", state="*")
    dp.register_callback_query_handler(lambda call: delete_op_button_from_list(call, bot),
                                       lambda c: c.data.startswith("delete_op_btn_"), state="*")
    dp.register_message_handler(handle_add_op_button_input, state=ButtonState.adding)
    dp.register_message_handler(handle_remove_op_button_input, state=ButtonState.removing)
    log.info("Admin OP management handlers registered.")
