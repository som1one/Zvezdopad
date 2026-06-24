import logging
import asyncio

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext

import database
from settings import ADMIN_IDS
from states import MaintenanceState
from keyboards import create_admin_cancel_markup

log = logging.getLogger('handlers.admin_maintenance')


def create_maintenance_menu_markup(is_enabled: bool):
    markup = InlineKeyboardMarkup(row_width=1)
    if is_enabled:
        toggle_btn = InlineKeyboardButton("🟢 Выключить тех. работы", callback_data="maintenance_off")
    else:
        toggle_btn = InlineKeyboardButton("🔴 Включить тех. работы", callback_data="maintenance_on")
    markup.add(toggle_btn)
    markup.add(InlineKeyboardButton("✏️ Текст во время тех. работ", callback_data="maintenance_edit_msg"))
    markup.add(InlineKeyboardButton("✏️ Текст рассылки по окончанию", callback_data="maintenance_edit_end"))
    markup.add(InlineKeyboardButton("👑 Админ-меню", callback_data="adminpanel"))
    return markup


async def show_maintenance_menu(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()

    enabled = await database.is_maintenance_mode()
    current_msg = await database.get_maintenance_message()
    current_end = await database.get_maintenance_end_text()
    status_text = "🔴 ВКЛ" if enabled else "🟢 ВЫКЛ"

    text = (
        f"🔧 <b>Режим тех. работ</b>\n\n"
        f"Статус: <b>{status_text}</b>\n\n"
        f"📝 <b>Текст во время тех. работ:</b>\n"
        f"<i>{current_msg}</i>\n\n"
        f"📢 <b>Текст рассылки по окончанию:</b>\n"
        f"<i>{current_end}</i>"
    )
    markup = create_maintenance_menu_markup(enabled)
    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")


async def maintenance_on_callback(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer("🔴 Тех. работы включены!", show_alert=True)
    await database.set_maintenance_mode(True)
    log.warning(f"Admin {call.from_user.id} ENABLED maintenance mode.")
    await show_maintenance_menu(call, bot)


async def maintenance_off_callback(call: CallbackQuery, bot: Bot):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer("🟢 Тех. работы выключены! Рассылка...", show_alert=True)
    await database.set_maintenance_mode(False)
    log.warning(f"Admin {call.from_user.id} DISABLED maintenance mode. Broadcasting...")
    await show_maintenance_menu(call, bot)
    asyncio.create_task(broadcast_maintenance_end(bot, call.from_user.id))


async def broadcast_maintenance_end(bot: Bot, admin_id: int):
    end_text = await database.get_maintenance_end_text()
    user_ids = await database.get_all_user_ids()
    if not user_ids:
        return
    log.info(f"Broadcasting maintenance end to {len(user_ids)} users...")
    success = 0
    failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, end_text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1
        if (success + failed) % 25 == 0:
            await asyncio.sleep(1)
    log.info(f"Maintenance broadcast done: {success} sent, {failed} failed.")
    try:
        await bot.send_message(admin_id,
            f"📢 Рассылка завершена!\n✅ Доставлено: {success}\n❌ Ошибок: {failed}\n📊 Всего: {len(user_ids)}")
    except Exception:
        pass


async def maintenance_edit_msg_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    current = await database.get_maintenance_message()
    markup = create_admin_cancel_markup("admin_maintenance")
    await call.message.edit_text(
        f"Текущий текст:\n<i>{current}</i>\n\nОтправьте новый текст для тех. работ:",
        reply_markup=markup, parse_mode="HTML")
    await MaintenanceState.waiting_for_message.set()


async def maintenance_edit_msg_input(message: types.Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        await state.finish(); return
    new_text = message.text or ""
    if not new_text.strip():
        await message.reply("❌ Текст не может быть пустым."); return
    await database.set_maintenance_message(new_text)
    await state.finish()
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔧 Тех. работы", callback_data="admin_maintenance"))
    await message.answer("✅ Текст тех. работ обновлен!", reply_markup=markup)


async def maintenance_edit_end_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    current = await database.get_maintenance_end_text()
    markup = create_admin_cancel_markup("admin_maintenance")
    await call.message.edit_text(
        f"Текущий текст рассылки:\n<i>{current}</i>\n\nОтправьте новый текст рассылки по окончанию:",
        reply_markup=markup, parse_mode="HTML")
    await MaintenanceState.waiting_for_end_text.set()


async def maintenance_edit_end_input(message: types.Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        await state.finish(); return
    new_text = message.text or ""
    if not new_text.strip():
        await message.reply("❌ Текст не может быть пустым."); return
    await database.set_maintenance_end_text(new_text)
    await state.finish()
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔧 Тех. работы", callback_data="admin_maintenance"))
    await message.answer("✅ Текст рассылки обновлен!", reply_markup=markup)


def register_admin_maintenance_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(lambda c: show_maintenance_menu(c, bot), lambda c: c.data == "admin_maintenance", state="*")
    dp.register_callback_query_handler(lambda c: maintenance_on_callback(c, bot), lambda c: c.data == "maintenance_on", state="*")
    dp.register_callback_query_handler(lambda c: maintenance_off_callback(c, bot), lambda c: c.data == "maintenance_off", state="*")
    dp.register_callback_query_handler(maintenance_edit_msg_callback, lambda c: c.data == "maintenance_edit_msg", state="*")
    dp.register_callback_query_handler(maintenance_edit_end_callback, lambda c: c.data == "maintenance_edit_end", state="*")
    dp.register_message_handler(lambda msg, state: maintenance_edit_msg_input(msg, state, bot), state=MaintenanceState.waiting_for_message)
    dp.register_message_handler(lambda msg, state: maintenance_edit_end_input(msg, state, bot), state=MaintenanceState.waiting_for_end_text)
    log.info("Admin maintenance handlers registered.")
