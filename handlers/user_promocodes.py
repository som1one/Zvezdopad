# Содержимое файла: handlers/user_promocodes.py (Исправлена ошибка TypeError)
import logging
import asyncpg
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound

import database
from settings import LINK_1, LINK_2
from utils import t
from keyboards import create_back_button
from states import PromoCodeState
from handlers.user_menu import show_main_menu

log = logging.getLogger('handlers.user_promocodes')  # Имя логгера оставляем как есть


async def prompt_for_promocode(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    await call.answer()

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass

    image_path = "images/promo.jpg"
    caption = (
        f"✨ Введи промокод для получения бонуса:\n\n"
        f"<i>*Найти промокоды можно в <a href='{LINK_1}'>канале</a> и <a href='{LINK_2}'>чате</a>.</i>"
    )

    try:
        with open(image_path, "rb") as photo:
            # --- ИСПРАВЛЕНИЕ: Убран disable_web_page_preview ---
            await call.message.answer_photo(photo=photo, caption=caption, parse_mode="HTML")
            # --------------------------------------------------
    except FileNotFoundError:
        log.error(f"Promo image not found: {image_path}")
        await call.message.answer(caption, parse_mode="HTML", disable_web_page_preview=True)  # Для answer() оставляем
    except Exception as e:
        # Логируем как ERROR, т.к. это проблема отправки
        log.error(f"Error sending promo prompt to user {user_id}: {e}")
        # Убираем traceback из лога ошибки, т.к. он был в запросе пользователя
        # log.exception(f"Error sending promo prompt to user {user_id}: {e}")
        await call.message.answer(caption, parse_mode="HTML", disable_web_page_preview=True)  # Для answer() оставляем

    await PromoCodeState.waiting_for_promocode.set()
    # Уровень INFO будет скрыт базовой настройкой ERROR в main.py
    # log.info(f"User {user_id} entered promocode input state.")


async def process_promocode_entry(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    promocode = message.text.strip()
    await state.finish()
    # log.info(f"User {user_id} submitted promocode: '{promocode}'") # INFO будет скрыт

    success, result_message = await database.use_promocode(user_id, promocode)

    if success:
        # log.info(f"Promocode '{promocode}' activation result for user {user_id}: Success - {result_message}") # INFO будет скрыт
        await message.answer(result_message, parse_mode="HTML")
    else:
        # Логируем как WARNING, если не удалось активировать
        log.warning(f"Promocode '{promocode}' activation result for user {user_id}: Failed - {result_message}")
        await message.answer(result_message, parse_mode="HTML")

    await show_main_menu(message, user_id, bot, edit=False)


def register_user_promocode_handlers(dp: Dispatcher, bot: Bot):
    dp.register_callback_query_handler(lambda call: prompt_for_promocode(call, bot),
                                       lambda c: c.data == "enter_promocode", state="*")
    dp.register_message_handler(lambda msg, state: process_promocode_entry(msg, state, bot),
                                state=PromoCodeState.waiting_for_promocode)

