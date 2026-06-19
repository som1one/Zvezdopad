# Содержимое файла: handlers/admin_channels.py (Адаптировано для asyncpg)
import logging
import time
from datetime import timedelta, datetime, timezone

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified

import database  # Наш async database
from settings import ADMIN_IDS
from utils import t
from keyboards import create_admin_cancel_markup
from states import AdminAddChannelState, AdminDeleteChannelState

log = logging.getLogger('handlers.admin_channels')


async def add_channel_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = create_admin_cancel_markup()
    await call.message.edit_text("Введите ID канала/чата для добавления (например, -100123456789):",
                                 reply_markup=markup)
    await AdminAddChannelState.waiting_for_channel_id.set()


async def add_channel_id_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    try:
        channel_id = int(message.text.strip())
        await state.update_data(channel_id_to_add=channel_id)
        await AdminAddChannelState.waiting_for_delete_time.set()
        await message.answer("Через сколько часов удалить из ОП (0 - не удалять):", reply_markup=markup)
    except ValueError:
        await message.reply("❌ Введите корректный числовой ID канала.", reply_markup=markup)


async def add_channel_delete_time_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    data = await state.get_data()
    channel_id = data.get('channel_id_to_add')

    if not channel_id:
        await message.reply("❗ Ошибка: ID канала не найден. Добавьте заново.", reply_markup=markup);
        await state.finish();
        return

    try:
        delete_hours = int(message.text.strip())
        if delete_hours < 0: raise ValueError("Время не может быть отрицательным")

        delete_timestamp_dt = None
        if delete_hours > 0:
            delete_timestamp_dt = datetime.now(timezone.utc) + timedelta(hours=delete_hours)  # Используем UTC
            log.info(
                f"Channel {channel_id} will be deleted after {delete_hours} hours (at {delete_timestamp_dt.isoformat()}).")
        else:
            log.info(f"Channel {channel_id} added without auto-deletion.")

        await database.add_channel_db(channel_id, delete_timestamp_dt)  # await

        await message.answer(
            f"✅ Канал ID {channel_id} добавлен." + (f" Удаление: {delete_hours} ч." if delete_timestamp_dt else ""),
            reply_markup=markup)
        await state.finish()

    except ValueError:
        await message.reply("❌ Введите корректное число часов (0 или больше).", reply_markup=markup)
    except Exception as e:
        log.exception(f"Error adding channel {channel_id} admin {admin_id}: {e}")
        await message.reply("❌ Ошибка при добавлении канала.", reply_markup=markup);
        await state.finish()


async def delete_channel_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = create_admin_cancel_markup()
    await call.message.edit_text("Введите ID канала/чата для удаления из списка ОП:", reply_markup=markup)
    await AdminDeleteChannelState.waiting_for_channel_id.set()


async def delete_channel_id_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    try:
        channel_id = int(message.text.strip())
        deleted = await database.delete_channel_db(channel_id)  # await

        if deleted:
            log.info(f"Admin {admin_id} deleted channel {channel_id} from subscriptions.")
            await message.answer(f"✅ Канал ID {channel_id} удален из списка ОП.", reply_markup=markup)
        else:
            await message.reply(f"❌ Канал ID {channel_id} не найден в списке.", reply_markup=markup)
        await state.finish()
    except ValueError:
        await message.reply("❌ Введите корректный числовой ID канала.", reply_markup=markup)
    except Exception as e:
        log.exception(f"Error deleting channel admin {admin_id}: {e}")
        await message.reply("❌ Ошибка при удалении канала.", reply_markup=markup);
        await state.finish()


async def list_channels(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: return
    await call.answer()

    channel_data = await database.get_channels_db(get_delete_time=True)  # await
    markup = InlineKeyboardMarkup(row_width=1)
    cancel_markup = create_admin_cancel_markup()  # Берем кнопку отмены

    if not channel_data:
        await call.message.edit_text("Список обязательных каналов пуст.", reply_markup=cancel_markup)
        return

    log.info(f"Admin {admin_id} viewing channel list.")
    message_text = "<b>Список каналов для подписки:</b>\n(Нажмите для удаления)\n\n"

    for channel_info in channel_data:
        channel_id = channel_info['channel_id']
        delete_time = channel_info['delete_time']  # Это datetime с tzinfo=UTC или None

        channel_name = f"Канал ID {channel_id}"
        delete_info = ""
        try:
            chat = await bot.get_chat(channel_id)
            channel_name = chat.title or channel_name
            if delete_time:
                # Форматируем datetime с таймзоной
                delete_info = f" (удаление: {delete_time.strftime('%d.%m.%y %H:%M %Z')})"
            else:
                delete_info = " (не удаляется)"
        except Exception as e:
            log.warning(f"Could not get info for channel {channel_id}: {e}")
            delete_info = " (ошибка инфо)"

        button_text = f"{channel_name}{delete_info} ❌"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"delete_channel_btn_{channel_id}"))

    if cancel_markup.inline_keyboard:
        for row in cancel_markup.inline_keyboard: markup.row(*row)

    try:
        await call.message.edit_text(message_text, reply_markup=markup, parse_mode="HTML",
                                     disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except Exception as e:
        log.error(f"Error editing list_channels message: {e}")


async def delete_channel_from_list(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: await call.answer("Нет доступа!", show_alert=True); return

    try:
        channel_id_to_delete = int(call.data.split("_")[-1])
    except (ValueError, IndexError):
        await call.answer("Ошибка ID канала.", show_alert=True); return

    deleted = await database.delete_channel_db(channel_id_to_delete)  # await
    if deleted:
        log.info(f"Admin {admin_id} deleted channel {channel_id_to_delete} from list view.")
        await call.answer(f"Канал {channel_id_to_delete} удален.", show_alert=False)
        await list_channels(call, bot)  # await
    else:
        await call.answer(f"Канал {channel_id_to_delete} не найден.", show_alert=True)
        await list_channels(call, bot)  # await


def register_admin_channel_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(add_channel_start, lambda c: c.data == "admin_add_channel", state="*")
    dp.register_message_handler(add_channel_id_input, state=AdminAddChannelState.waiting_for_channel_id)
    dp.register_message_handler(add_channel_delete_time_input, state=AdminAddChannelState.waiting_for_delete_time)
    dp.register_callback_query_handler(delete_channel_start, lambda c: c.data == "admin_delete_channel", state="*")
    dp.register_message_handler(delete_channel_id_input, state=AdminDeleteChannelState.waiting_for_channel_id)
    dp.register_callback_query_handler(lambda call: list_channels(call, bot), lambda c: c.data == "admin_get_channels",
                                       state="*")
    dp.register_callback_query_handler(lambda call: delete_channel_from_list(call, bot),
                                       lambda c: c.data.startswith("delete_channel_btn_"), state="*")
    log.info("Admin channel management handlers registered.")
