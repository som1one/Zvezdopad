# Содержимое файла: handlers/admin_promocodes.py (Адаптировано для asyncpg)
import logging
import asyncpg  # <-- Добавлено
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified

import database  # Наш async database
from settings import ADMIN_IDS
from utils import t
from keyboards import create_admin_cancel_markup
from states import AdminAddPromoCodeState, AdminDeletePromoCodeState

log = logging.getLogger('handlers.admin_promocodes')


async def add_promocode_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = create_admin_cancel_markup()
    prompt = (
        "Введите данные промокода в формате:\n"
        "<code>ПРОМОКОД:СУММА:ЛИМИТ:РЕФЕРАЛЫ</code>\n\n"
        "• <b>ПРОМОКОД:</b> Сам код (без пробелов)\n"
        "• <b>СУММА:</b> Награда в звездах (число)\n"
        "• <b>ЛИМИТ:</b> Макс. число активаций (целое > 0)\n"
        "• <b>РЕФЕРАЛЫ:</b> Мин. число рефералов (целое >= 0)\n\n"
        "<i>Пример:</i> <code>SUPERGIFT:5:100:10</code>"
    )
    await call.message.edit_text(prompt, reply_markup=markup, parse_mode="HTML")
    await AdminAddPromoCodeState.waiting_for_data.set()


async def add_promocode_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    markup = create_admin_cancel_markup()
    parts = message.text.strip().split(':')

    try:
        if len(parts) != 4: raise ValueError("Incorrect number of parts")
        promocode = parts[0]
        if not promocode or ' ' in promocode: raise ValueError("Invalid promocode format")
        reward = float(parts[1]);
        max_uses = int(parts[2]);
        min_referrals = int(parts[3])
        if reward <= 0 or max_uses <= 0 or min_referrals < 0: raise ValueError("Values invalid")

        await database.add_promocode(promocode, reward, max_uses, min_referrals)  # await
        log.info(f"Admin {admin_id} added promocode: '{promocode}', {reward}, {max_uses}, {min_referrals}")
        await message.answer(f"✅ Промокод <code>{escape(promocode)}</code> добавлен!", reply_markup=markup,
                             parse_mode="HTML")
        await state.finish()

    except (ValueError, IndexError) as e:
        log.warning(f"Invalid promocode input admin {admin_id}: '{message.text}'. Err: {e}")
        await message.reply("❌ Ошибка формата. <code>КОД:СУММА:ЛИМИТ:РЕФЫ</code>", reply_markup=markup,
                            parse_mode="HTML")
    except Exception as e:
        log.exception(f"Error adding promocode admin {admin_id}: {e}")
        await message.answer("❌ Ошибка добавления.", reply_markup=markup);
        await state.finish()


async def delete_promocode_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()
    markup = create_admin_cancel_markup()
    await show_promocodes_list(call, state, for_deletion=True)  # await


async def delete_promocode_input(message: types.Message, state: FSMContext):
    admin_id = message.from_user.id
    if admin_id not in ADMIN_IDS: await state.finish(); return
    promocode_to_delete = message.text.strip()
    markup = create_admin_cancel_markup()

    try:
        deleted = await database.delete_promo(promocode_to_delete)  # await
        log.info(f"Admin {admin_id} attempted delete promocode: '{promocode_to_delete}'")
        if deleted:
            await message.answer(f"✅ <code>{escape(promocode_to_delete)}</code> удален.", reply_markup=markup,
                                 parse_mode="HTML")
        else:
            await message.answer(f"ℹ️ <code>{escape(promocode_to_delete)}</code> не найден.", reply_markup=markup,
                                 parse_mode="HTML")
    except Exception as e:
        log.exception(f"Error deleting promocode admin {admin_id}: {e}")
        await message.answer("❌ Ошибка удаления.", reply_markup=markup)
    await state.finish()


async def delete_promocode_from_list(call: CallbackQuery, state: FSMContext):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS: await call.answer("Нет доступа!", show_alert=True); return
    try:
        promocode_to_delete = call.data[len("delete_promo_"):]
    except IndexError:
        await call.answer("Ошибка данных.", show_alert=True); return

    try:
        await database.delete_promo(promocode_to_delete)  # await
        log.info(f"Admin {admin_id} deleted promocode '{promocode_to_delete}' from list.")
        await call.answer(f"Промокод '{escape(promocode_to_delete)}' удален.", show_alert=False)
        await show_promocodes_list(call, state, for_deletion=True)  # await
    except Exception as e:
        log.exception(f"Error deleting promocode '{promocode_to_delete}' from list: {e}")
        await call.answer("Ошибка удаления.", show_alert=True)


async def show_promocodes_list(call: CallbackQuery, state: FSMContext, for_deletion=False):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer()

    promocodes_details = await database.get_all_promocodes()  # await
    markup = InlineKeyboardMarkup(row_width=1)
    action_text = "(Нажмите для удаления)" if for_deletion else ""
    message_text = f"<b>📜 Список промокодов {action_text}:</b>\n\n"
    cancel_markup = create_admin_cancel_markup()

    if not promocodes_details:
        message_text += "<i>Нет активных промокодов.</i>"
    else:
        for data in promocodes_details:
            code, reward, uses, refs = data['promocode'], data['reward'], data['max_uses'], data['min_referrals']
            line_text = f"<code>{escape(code)}</code> | {reward}⭐️ | Акт: {uses} | Реф: {refs}"
            if for_deletion:
                button_text = f"{line_text} | ❌"
                markup.add(InlineKeyboardButton(button_text, callback_data=f"delete_promo_{code}"))
            else:
                message_text += f"• {line_text}\n"

    if cancel_markup.inline_keyboard:
        for row in cancel_markup.inline_keyboard: markup.row(*row)

    try:
        disable_preview = not for_deletion
        await call.message.edit_text(message_text, reply_markup=markup, parse_mode="HTML",
                                     disable_web_page_preview=disable_preview)
    except MessageNotModified:
        pass
    except Exception as e:
        log.error(f"Error editing message for promocode list: {e}")


def register_admin_promocode_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(add_promocode_start, lambda c: c.data == "admin_promocode_added", state="*")
    dp.register_message_handler(add_promocode_input, state=AdminAddPromoCodeState.waiting_for_data)
    dp.register_callback_query_handler(lambda call, state: show_promocodes_list(call, state, for_deletion=True),
                                       lambda c: c.data == "admin_promocode_delete", state="*")
    dp.register_callback_query_handler(delete_promocode_from_list, lambda c: c.data.startswith("delete_promo_"),
                                       state="*")
    # dp.register_message_handler(delete_promocode_input, state=AdminDeletePromoCodeState.waiting_for_promocode) # Удаление вводом пока убрано, т.к. есть список
    dp.register_callback_query_handler(lambda call, state: show_promocodes_list(call, state, for_deletion=False),
                                       lambda c: c.data == "show_promocodes", state="*")
    log.info("Admin promocode management handlers registered.")
