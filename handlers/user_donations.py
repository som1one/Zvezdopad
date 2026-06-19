# Содержимое файла: handlers/user_donations.py (С доп. логами в обработчиках платежей)
import logging
import os
import time  # <-- ДОБАВЛЕНО для измерения времени

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, LabeledPrice, PreCheckoutQuery, \
    SuccessfulPayment, InputFile
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID, TelegramAPIError

# Импорты из проекта
from database import set_custom_reward_in_db, set_ref_reward  # Убедитесь, что они async!
from settings import DONATE_PAY, DONATE_TIME, ADMIN_IDS, TOKEN  # Убедитесь, что TOKEN импортируется
from keyboards import create_back_button

# --- НАСТРОЙКА ЛОГГИРОВАНИЯ ---
log = logging.getLogger('handlers.user_donations')


# Уровень INFO будет установлен в main.py

# --- Обработчики донатов ---

async def show_donate_options(call: CallbackQuery, bot: Bot):
    """Показывает опции доната."""
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"IQID fail show_donate_options user {user_id}");
        return
    except Exception as e:
        log.error(f"Error answering cb show_donate_options user {user_id}: {e}");
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(text="🌟 Оплатить Telegram Stars", callback_data="donate_stars"))
    keyboard.add(create_back_button(user_id))

    # Текст для начального сообщения
    caption = f"""
💛 <b>Выберите способ поддержки:</b>

Поддержи проект через Telegram Stars и получи бонусы!

✨ <b>Награды за поддержку ({DONATE_PAY} ⭐):</b>
      • Множитель <b>x2.5</b> к кликам на {DONATE_TIME} дней.
      • Множитель <b>x2</b> за рефералов на {DONATE_TIME} дней.

Выберите способ оплаты ниже.
"""
    image_path = "images/donate.jpg"

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass  # Логирование не нужно

    try:
        photo_input = InputFile(image_path)
        await bot.send_photo(
            chat_id=user_id,
            photo=photo_input,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except FileNotFoundError:
        log.error(f"Donate image not found: {image_path}")
        await bot.send_message(user_id, caption, reply_markup=keyboard, parse_mode="HTML")
    except TelegramAPIError as e:
        log.error(f"Telegram API error sending donate options photo user {user_id}: {e}")
        await bot.send_message(user_id, caption, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        log.exception(f"Unexpected error sending donate options user {user_id}: {e}")
        await bot.send_message(user_id, caption, reply_markup=keyboard, parse_mode="HTML")


async def handle_donate_stars(call: CallbackQuery, bot: Bot):
    """Инициирует процесс оплаты через Telegram Stars (с оформлением из референса)."""
    user_id = call.from_user.id
    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"IQID fail handle_donate_stars user {user_id}");
        return
    except Exception as e:
        log.error(f"Error answering cb handle_donate_stars user {user_id}: {e}");
        return

    price_amount = DONATE_PAY
    if not isinstance(price_amount, int) or price_amount <= 0:
        log.error(f"Invalid DONATE_PAY value: {price_amount}.")
        await bot.send_message(user_id, "Ошибка конфигурации суммы доната.")
        return

    # ОФОРМЛЕНИЕ ИЗ РЕФЕРЕНСА ДЛЯ ИНВОЙСА
    invoice_description = (
        f"✨ Поддержи проект и получи бонусы!\n\n"
        f"🌟 Множитель x2.5 к кликам на {DONATE_TIME} дней.\n"
        f"🤝 Множитель x2 за рефералов на {DONATE_TIME} дней.\n\n"
        f"❓ Для возврата в меню пропиши /start."
    )
    photo_url_for_invoice = "https://promo-storage.biz/prodvinemoscow/1/1611564384WhatsApp_Image_2021_01_25_at_11_46_00.jpeg"
    photo_width = 500
    photo_height = 300

    labeled_price = types.LabeledPrice(label='Поддержка проекта 💛', amount=price_amount)
    payload = f"donate_boost_{user_id}"
    provider_token = ""

    try:
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass

        await bot.send_invoice(
            chat_id=user_id,
            title="💛 Поддержка проекта",
            description=invoice_description,
            provider_token=provider_token,
            currency="XTR",
            prices=[labeled_price],
            start_parameter="donate-boost",
            payload=payload,
            photo_url=photo_url_for_invoice,
            photo_width=photo_width,
            photo_height=photo_height,
            is_flexible=False
        )
        log.info(f"XTR Invoice sent user {user_id} for {price_amount} XTR (reference UI).")
    except TelegramAPIError as e:
        log.exception(f"Failed to send XTR invoice user {user_id} (API Error): {e}")
        await bot.send_message(user_id, "Не удалось создать счет для оплаты Stars. Пожалуйста, попробуйте позже.")
    except Exception as e:
        log.exception(f"Unexpected error sending XTR invoice user {user_id}: {e}")
        await bot.send_message(user_id, "Произошла ошибка при создании счета Stars.")


async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    """Обрабатывает предварительный запрос перед списанием Stars."""
    start_time = time.monotonic()  # Засекаем время начала
    user_id = pre_checkout_query.from_user.id
    query_id = pre_checkout_query.id

    # --- ЛОГ: Начало обработки ---
    log.info(f"START handle_pre_checkout query {query_id} user {user_id}")

    log.info(
        f"Received pre-checkout query {query_id} from user {user_id}, "
        f"amount {pre_checkout_query.total_amount} {pre_checkout_query.currency}, "
        f"payload: {pre_checkout_query.invoice_payload}"
    )

    expected_payload_prefix = f"donate_boost_{user_id}"
    if pre_checkout_query.invoice_payload != expected_payload_prefix:
        log.warning(
            f"PreCheckoutQuery {query_id} payload mismatch user {user_id}. Expected '{expected_payload_prefix}', got '{pre_checkout_query.invoice_payload}'")
        await bot.answer_pre_checkout_query(query_id, ok=False, error_message="Ошибка проверки платежа.")
        processing_time = time.monotonic() - start_time
        # --- ЛОГ: Конец обработки (ошибка payload) ---
        log.info(
            f"END handle_pre_checkout query {query_id} user {user_id} (Payload mismatch). Time: {processing_time:.3f}s")
        return

    if pre_checkout_query.currency != "XTR":
        log.warning(
            f"PreCheckoutQuery {query_id} currency mismatch user {user_id}. Expected 'XTR', got '{pre_checkout_query.currency}'")
        await bot.answer_pre_checkout_query(query_id, ok=False, error_message="Неверная валюта.")
        processing_time = time.monotonic() - start_time
        # --- ЛОГ: Конец обработки (ошибка валюты) ---
        log.info(
            f"END handle_pre_checkout query {query_id} user {user_id} (Currency mismatch). Time: {processing_time:.3f}s")
        return

    answer_ok = False
    try:
        await bot.answer_pre_checkout_query(query_id, ok=True)
        answer_ok = True
        log.info(f"Answered pre-checkout query {query_id} successfully (ok=True) for user {user_id}.")
    except InvalidQueryID:
        log.warning(f"Failed answer pre-checkout query {query_id}: InvalidQueryID")
        # Выходим, т.к. отвечать поздно
    except TelegramAPIError as e:
        log.error(f"Failed answer pre-checkout query {query_id} user {user_id} (API Error): {e}")
        # Пытаемся ответить False
        try:
            await bot.answer_pre_checkout_query(query_id, ok=False, error_message="Внутренняя ошибка.")
        except Exception:
            pass
    except Exception as e:
        log.exception(f"Unexpected error answering pre-checkout query {query_id} user {user_id}: {e}")
        # Пытаемся ответить False
        try:
            await bot.answer_pre_checkout_query(query_id, ok=False, error_message="Непредвиденная ошибка.")
        except Exception:
            pass

    processing_time = time.monotonic() - start_time
    # --- ЛОГ: Конец обработки (основной) ---
    log.info(
        f"END handle_pre_checkout query {query_id} user {user_id} (Answer ok: {answer_ok}). Time: {processing_time:.3f}s")


async def handle_successful_payment(message: types.Message, bot: Bot):
    """Обрабатывает сообщение об успешном платеже Stars."""
    start_time = time.monotonic()  # Засекаем время
    user_id = message.from_user.id
    username = message.from_user.username or f"id{user_id}"
    payment_info = message.successful_payment
    amount = payment_info.total_amount
    currency = payment_info.currency
    charge_id = payment_info.telegram_payment_charge_id
    payload = payment_info.invoice_payload

    # --- ЛОГ: Начало обработки ---
    log.info(f"START handle_successful_payment user {user_id}, charge {charge_id}, amount {amount} {currency}")

    log.info(
        f"Successful XTR payment received from user {user_id} (@{username}): "
        f"Amount={amount} {currency}, ChargeID={charge_id}, Payload={payload}"
    )

    expected_payload = f"donate_boost_{user_id}"
    if payload != expected_payload or currency != "XTR":
        log.error(
            f"Payload/Currency mismatch in successful_payment! User {user_id}, Expected '{expected_payload}'/XTR, got '{payload}'/{currency}'. Ignoring.")
        await message.answer("Обнаружено несоответствие данных платежа. Бонусы не начислены.")
        processing_time = time.monotonic() - start_time
        # --- ЛОГ: Конец обработки (ошибка payload/currency) ---
        log.info(
            f"END handle_successful_payment user {user_id}, charge {charge_id} (Payload/Currency mismatch). Time: {processing_time:.3f}s")
        return

    # --- Применяем бусты (ИСПОЛЬЗУЕМ AWAIT) ---
    boosted_min_click = 0.25
    boosted_max_click = 0.25
    boosted_min_ref = 2.0
    boosted_max_ref = 2.0

    boosts_applied = False
    try:
        await set_custom_reward_in_db(user_id, boosted_min_click, boosted_max_click, DONATE_TIME)
        await set_ref_reward(user_id, boosted_min_ref, boosted_max_ref, DONATE_TIME)
        boosts_applied = True
        log.info(f"Boosts applied for user {user_id} after successful donation for {DONATE_TIME} days.")

        await message.answer(
            f"<b>Спасибо за поддержку проекта 💛</b>\n\n"
            f"✨ Твои бусты успешно активированы на {DONATE_TIME} дней:\n"
            f"🌟 <b>Клики:</b> x2.5 ({boosted_min_click:.2f} ⭐/клик).\n"
            f"🤝 <b>Рефералы:</b> x2 ({boosted_min_ref:.1f} ⭐/реферал).\n\n"
            f"Продолжай наслаждаться игрой! 🥳",
            parse_mode="HTML"
        )

        admin_notification = (
            f"💛 <b>Получен донат Stars!</b>\n\n"
            f"👤 Отправитель: @{username} | ID: <code>{user_id}</code>\n"
            f"💰 Сумма: <code>{amount} {currency}</code>\n"
            f"🧾 Payload: <code>{payload}</code>\n"
            f"💳 TG Charge ID: <code>{charge_id}</code>\n\n"
            f"✅ Бусты (x2.5 клик, x2 реф) на {DONATE_TIME} дней применены."
        )
        if ADMIN_IDS:
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_notification, parse_mode="HTML")
                except Exception as e:
                    log.error(f"Failed to send donation notification to admin {admin_id}: {e}")
        else:
            log.warning("ADMIN_IDS list is empty. No admin notification sent.")

    except Exception as e:
        log.exception(
            f"Error applying boosts or sending notifications user {user_id} after payment (Payload: {payload}): {e}")
        await message.answer(
            "Спасибо за платеж! Однако произошла ошибка при активации ваших бонусов 😥. Пожалуйста, свяжитесь с поддержкой.")
        # Уведомляем админов об ошибке
        admin_error_notification = (
            f"🆘 <b>Ошибка начисления бонусов после доната Stars!</b>\n\n"
            f"👤 Пользователь: @{username} | ID: <code>{user_id}</code>\n"
            f"💰 Сумма: <code>{amount} {currency}</code>\n"
            f"🧾 Payload: <code>{payload}</code>\n"
            f"💳 TG Charge ID: <code>{charge_id}</code>\n\n"
            f"❗️ Произошла ошибка при вызове функций БД или отправке уведомлений. Проверьте логи."
        )
        if ADMIN_IDS:
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, admin_error_notification, parse_mode="HTML")
                except Exception as admin_e:
                    log.error(f"Failed to send boost error notification to admin {admin_id}: {admin_e}")

    processing_time = time.monotonic() - start_time
    # --- ЛОГ: Конец обработки (основной) ---
    log.info(
        f"END handle_successful_payment user {user_id}, charge {charge_id} (Boosts applied: {boosts_applied}). Time: {processing_time:.3f}s")


# --- Регистрация обработчиков ---

def register_user_donation_handlers(dp: Dispatcher, bot: Bot):
    """Регистрирует обработчики для донатов."""
    dp.register_callback_query_handler(lambda call: show_donate_options(call, bot), lambda c: c.data == "donate",
                                       state="*")
    dp.register_callback_query_handler(lambda call: handle_donate_stars(call, bot), lambda c: c.data == "donate_stars",
                                       state="*")
    dp.register_pre_checkout_query_handler(lambda query: handle_pre_checkout(query, bot), state="*")
    dp.register_message_handler(lambda msg: handle_successful_payment(msg, bot),
                                content_types=types.ContentType.SUCCESSFUL_PAYMENT, state="*")

    # --- ЛОГИРОВАНИЕ ОСТАЕТСЯ INFO ---
    log.info("User donation handlers registered.")
