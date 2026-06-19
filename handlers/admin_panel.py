import logging
import asyncio

from aiogram import types, Bot, Dispatcher
from aiogram.types import CallbackQuery
from aiogram.utils.exceptions import MessageNotModified, TelegramAPIError, InvalidQueryID

import database
from settings import ADMIN_IDS
from utils import get_subbalance
from keyboards import create_admin_panel_markup, create_admin_cancel_markup

log = logging.getLogger('handlers.admin_panel')


async def show_admin_panel(message: types.Message | types.CallbackQuery, bot: Bot, app):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        if isinstance(message, types.Message):
            await message.reply("⛔ У вас нет доступа к админ-панели.")
        else:
            try:
                await message.answer("Нет доступа", show_alert=True)
            except (TelegramAPIError, InvalidQueryID) as e:
                log.warning(f"Failed answer callback query non-admin {user_id}: {e}")
        return

    target_message = None
    target_chat_id = None
    is_callback = isinstance(message, types.CallbackQuery)
    send_new = False

    if is_callback:
        try:
            await message.answer()
            log.info(f"Admin {user_id} accessed admin panel via callback.")
            target_message = message.message
            target_chat_id = target_message.chat.id
        except InvalidQueryID:
            log.warning(f"Callback query expired for admin {user_id} accessing panel (InvalidQueryID). Sending new.")
            target_chat_id = message.message.chat.id
            send_new = True
            target_message = None
        except TelegramAPIError as e:
            log.warning(f"Callback query error for admin {user_id} accessing panel: {e}. Sending new.")
            target_chat_id = message.message.chat.id
            send_new = True
            target_message = None
    else:
        log.info(f"Admin {user_id} accessed admin panel via command.")
        target_message = message
        target_chat_id = target_message.chat.id
        send_new = True

    if not target_chat_id:
        log.error(f"Could not determine target_chat_id for admin panel request from user {user_id}.")
        return

    try:
        subgram_balance_str = await get_subbalance()
        if "ошибка" in subgram_balance_str.lower() or "таймаут" in subgram_balance_str.lower() or "Тех. работы" in subgram_balance_str:
            log.warning(f"SubGram balance fetch issue: {subgram_balance_str}")
            subgram_balance_str = "Ошибка"

        pyrogram_balance_str = "N/A"
        if app and app.is_connected:
            try:
                pyrogram_balance = await app.get_stars_balance()
                pyrogram_balance_str = f"{pyrogram_balance}" if pyrogram_balance is not None else "Ошибка"
            except Exception as e:
                log.error(f"Failed to get Pyrogram stars balance: {e}")
                pyrogram_balance_str = "Ошибка"
        elif not app:
            log.warning("Pyrogram client (app) not passed to show_admin_panel.")
        else:
            log.warning("Pyrogram client (app) is not connected.");
            pyrogram_balance_str = "Откл."

        user_stats = await database.get_user_counts()
        total_users = user_stats.get("total", 0)
        daily_users = user_stats.get("daily", 0)
        monthly_users = user_stats.get("monthly", 0)

        day_spent = await database.get_spent_stars_for_day()
        week_spent = await database.get_spent_stars_for_week()
        month_spent = await database.get_spent_stars_for_month()
        total_withdrawn_val = await database.get_total_withdrawn()

        total_tasks_val = await database.get_total_tasks()
        total_promocodes_val = await database.get_total_promocodes()
        total_channels_val = await database.get_total_channels()

        boosters_count = await database.get_unique_users_count()

        stats_message = (
            f"📊 <b>Админ-панель</b>\n\n"
            f"<b>🏦 Балансы</b>\n"
            f"  ⭐️ Звезд (Pyrogram): <code>{pyrogram_balance_str}</code>\n"
            f"  💶 Баланс SubGram: <code>{subgram_balance_str}</code>\n\n"
            f"💸 <b>Всего выплачено:</b> <code>{total_withdrawn_val:.2f}⭐️</code>\n\n"
            f"📉 <b>Потрачено звезд (выплаты):</b>\n"
            f"  🔹 За сегодня: <code>{day_spent:.2f}⭐️</code>\n"
            f"  🔹 За неделю: <code>{week_spent:.2f}⭐️</code>\n"
            f"  🔹 За месяц: <code>{month_spent:.2f}⭐️</code>\n\n"
            f"👥 <b>Пользователей:</b>\n"
            f"  ▫️ Всего: <code>{total_users}</code>\n"
            f"  ▫️ Новых за день: <code>{daily_users}</code>\n"
            f"  ▫️ Новых за месяц: <code>{monthly_users}</code>\n\n"
            f"🚀 <b>Количество бустеров:</b> <code>{boosters_count}</code>\n\n"
            f"⚙️ <b>Объекты в базе:</b>\n"
            f"  📋 Задания: <code>{total_tasks_val}</code>\n"
            f"  📚 Промокоды: <code>{total_promocodes_val}</code>\n"
            f"  📡 ОП Каналы: <code>{total_channels_val}</code>"
        )
        markup = await create_admin_panel_markup(user_id)

        if not send_new and target_message:
            try:
                await target_message.edit_text(stats_message, reply_markup=markup, parse_mode="HTML")
            except MessageNotModified:
                log.debug("Admin panel content not modified.")
            except Exception as e_edit:
                log.warning(f"Failed to edit admin panel message for user {user_id}: {e_edit}. Sending new.")
                send_new = True

        if send_new:
            await bot.send_message(target_chat_id, stats_message, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        log.exception(f"Error displaying admin panel for user {user_id}: {e}")
        error_text = "Произошла ошибка при загрузке админ-панели."
        try:
            await bot.send_message(target_chat_id, error_text, reply_markup=await create_admin_panel_markup(user_id))
        except Exception as e_err_send:
            log.error(f"Failed to send error message for admin panel to {target_chat_id}: {e_err_send}")


def register_admin_panel_handlers(dp: Dispatcher, bot: Bot, app):
    dp.register_message_handler(lambda msg: show_admin_panel(msg, bot, app), commands=['adminpanel'], state="*")
    dp.register_callback_query_handler(lambda call: show_admin_panel(call, bot, app), lambda c: c.data == "adminpanel",
                                       state="*")
    log.info("Admin panel handlers registered.")
