# Содержимое файла: handlers/admin_maintenance.py
# Режим тех. работ: включение/выключение, настройка текстов, рассылка по окончанию
import logging
import asyncio

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext

from database import (
    is_maintenance_mode, set_maintenance_mode,
    get_maintenance_message, set_maintenance_message,
    get_maintenance_end_text, set_maintenance_end_text,
    get_all_user_ids
)
from settings import ADMIN_IDS
from states import MaintenanceState
from keyboards import create_admin_cancel_markup

log = logging.getLogger('handlers.admin_maintenance')


def create_maintenance_menu_markup():
    """Создает клавиатуру меню тех. работ."""
    markup = InlineKeyboardMarkup(row_width=1)
    enabled = is_maintenance_mode()

    if enabled:
        toggle_btn = InlineKeyboardButton("🟢 Выключить тех. работы", callback_data="maintenance_off")
    else:
        toggle_btn = InlineKeyboardButton("🔴 Включить тех. работы", callback_data="maintenance_on")

    edit_msg_btn = InlineKeyboardButton("✏️ Текст во время тех. работ", callback_data="maintenance_edit_msg")
    edit_end_btn = InlineKeyboardButton("✏️ Текст рассылки по окончанию", callback_data="maintenance_edit_end")
    back_btn = InlineKeyboardButton("👑 Админ-меню", callback_data="adminpanel")

    status_text = "🔴 ВКЛ" if enabled else "🟢 ВЫКЛ"
    markup.add(toggle_btn)
    markup.add(edit_msg_btn)
    markup.add(edit_end_btn)
    markup.add(back_btn)
    return markup, status_text


async def show_maintenance_menu(call: CallbackQuery, bot: Bot):
    """Показывает меню управления тех. работами."""
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()

    markup, status_text = create_maintenance_menu_markup()
    current_msg = get_maintenance_message()
    current_end = get_maintenance_end_text()

    text = (
        f"🔧 <b>Режим тех. работ</b>\n\n"
        f"Статус: <b>{status_text}</b>\n\n"
        f"📝 <b>Текст во время тех. работ:</b>\n"
        f"<i>{current_msg}</i>\n\n"
        f"📢 <b>Текст рассылки по окончанию:</b>\n"
        f"<i>{current_end}</i>"
    )

    try:
        await call.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        await bot.send_message(call.message.chat.id, text, reply_markup=markup, parse_mode="HTML")


async def maintenance_on_callback(call: CallbackQuery, bot: Bot):
    """Включает режим тех. работ."""
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer("🔴 Тех. работы включены!", show_alert=True)
    set_maintenance_mode(True)
    log.warning(f"Admin {call.from_user.id} ENABLED maintenance mode.")
    await show_maintenance_menu(call, bot)


async def maintenance_off_callback(call: CallbackQuery, bot: Bot):
    """Выключает режим тех. работ и запускает рассылку."""
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer("🟢 Тех. работы выключены! Запускаю рассылку...", show_alert=True)
    set_maintenance_mode(False)
    log.warning(f"Admin {call.from_user.id} DISABLED maintenance mode. Starting broadcast...")

    # Обновляем меню
    await show_maintenance_menu(call, bot)

    # Запускаем рассылку в фоне
    asyncio.create_task(broadcast_maintenance_end(bot, call.from_user.id))


async def broadcast_maintenance_end(bot: Bot, admin_id: int):
    """Рассылает текст об окончании тех. работ всем пользователям."""
    end_text = get_maintenance_end_text()
    user_ids = get_all_user_ids()

    if not user_ids:
        log.info("No users to broadcast maintenance end.")
        return

    log.info(f"Broadcasting maintenance end to {len(user_ids)} users...")
    success = 0
    failed = 0

    for user_id in user_ids:
        try:
            await bot.send_message(user_id, end_text, parse_mode="HTML")
            success += 1
        except Exception:
            failed += 1

        # Антифлуд: 25 сообщений в секунду
        if (success + failed) % 25 == 0:
            await asyncio.sleep(1)

    log.info(f"Maintenance end broadcast complete: {success} sent, {failed} failed.")

    # Уведомляем админа о результатах
    try:
        await bot.send_message(
            admin_id,
            f"📢 Рассылка завершена!\n\n"
            f"✅ Доставлено: {success}\n"
            f"❌ Ошибок: {failed}\n"
            f"📊 Всего: {len(user_ids)}"
        )
    except Exception as e:
        log.error(f"Failed to notify admin about broadcast results: {e}")


async def maintenance_edit_msg_callback(call: CallbackQuery, state: FSMContext):
    """Запрашивает новый текст сообщения для тех. работ."""
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    current = get_maintenance_message()
    markup = create_admin_cancel_markup("admin_maintenance")
    await call.message.edit_text(
        f"Текущий текст:\n<i>{current}</i>\n\n"
        f"Отправьте новый текст сообщения, которое будет отдаваться пользователям во время тех. работ:",
        reply_markup=markup, parse_mode="HTML"
    )
    await MaintenanceState.waiting_for_message.set()


async def maintenance_edit_msg_input(message: types.Message, state: FSMContext, bot: Bot):
    """Сохраняет новый текст сообщения для тех. работ."""
    if message.from_user.id not in ADMIN_IDS:
        await state.finish()
        return

    new_text = message.text or message.caption or ""
    if not new_text.strip():
        await message.reply("❌ Текст не может быть пустым. Попробуйте еще раз.")
        return

    set_maintenance_message(new_text)
    await state.finish()
    log.info(f"Admin {message.from_user.id} updated maintenance message.")

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔧 Тех. работы", callback_data="admin_maintenance"))
    markup.add(InlineKeyboardButton("👑 Админ-меню", callback_data="adminpanel"))
    await message.answer("✅ Текст тех. работ обновлен!", reply_markup=markup)


async def maintenance_edit_end_callback(call: CallbackQuery, state: FSMContext):
    """Запрашивает новый текст рассылки по окончанию тех. работ."""
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    current = get_maintenance_end_text()
    markup = create_admin_cancel_markup("admin_maintenance")
    await call.message.edit_text(
        f"Текущий текст рассылки:\n<i>{current}</i>\n\n"
        f"Отправьте новый текст рассылки, которая будет отправлена ВСЕМ по окончанию тех. работ:",
        reply_markup=markup, parse_mode="HTML"
    )
    await MaintenanceState.waiting_for_end_text.set()


async def maintenance_edit_end_input(message: types.Message, state: FSMContext, bot: Bot):
    """Сохраняет новый текст рассылки по окончанию тех. работ."""
    if message.from_user.id not in ADMIN_IDS:
        await state.finish()
        return

    new_text = message.text or message.caption or ""
    if not new_text.strip():
        await message.reply("❌ Текст не может быть пустым. Попробуйте еще раз.")
        return

    set_maintenance_end_text(new_text)
    await state.finish()
    log.info(f"Admin {message.from_user.id} updated maintenance end broadcast text.")

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔧 Тех. работы", callback_data="admin_maintenance"))
    markup.add(InlineKeyboardButton("👑 Админ-меню", callback_data="adminpanel"))
    await message.answer("✅ Текст рассылки по окончанию обновлен!", reply_markup=markup)


def register_admin_maintenance_handlers(dp: Dispatcher, bot: Bot):
    """Регистрирует обработчики для режима тех. работ."""
    dp.register_callback_query_handler(
        lambda call: show_maintenance_menu(call, bot),
        lambda c: c.data == "admin_maintenance", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: maintenance_on_callback(call, bot),
        lambda c: c.data == "maintenance_on", state="*"
    )
    dp.register_callback_query_handler(
        lambda call: maintenance_off_callback(call, bot),
        lambda c: c.data == "maintenance_off", state="*"
    )
    dp.register_callback_query_handler(
        maintenance_edit_msg_callback,
        lambda c: c.data == "maintenance_edit_msg", state="*"
    )
    dp.register_callback_query_handler(
        maintenance_edit_end_callback,
        lambda c: c.data == "maintenance_edit_end", state="*"
    )
    dp.register_message_handler(
        lambda msg, state: maintenance_edit_msg_input(msg, state, bot),
        state=MaintenanceState.waiting_for_message
    )
    dp.register_message_handler(
        lambda msg, state: maintenance_edit_end_input(msg, state, bot),
        state=MaintenanceState.waiting_for_end_text
    )
    log.info("Admin maintenance handlers registered.")
