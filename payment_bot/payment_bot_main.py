import asyncio
import logging
import os
import uuid

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    SuccessfulPayment,
    CallbackQuery,
)
from aiogram.utils.markdown import hbold

import payment_bot_settings as p_settings
from payment_bot_keyboards import (
    get_main_payment_keyboard,
    get_boost_selection_keyboard,
    get_topup_amount_keyboard,
    get_back_to_main_payment_menu_keyboard
)
from payment_bot_states import PaymentStates

import database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s (%(filename)s).%(funcName)s(%(lineno)d)"
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=p_settings.PAYMENT_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()
payment_router = Router(name="payment_router")


async def notify_admins(text: str):
    for admin_id in p_settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"Failed to send notification to admin {admin_id}: {e}")


async def send_stars_invoice(chat_id: int, user_id: int, amount_stars: int, title: str, description: str,
                             payload_prefix: str, photo_url: str | None = None):
    # Генерируем уникальный payload для каждой транзакции
    payload_uuid = f"{payload_prefix}_{user_id}_{uuid.uuid4().hex}"
    prices = [LabeledPrice(label=f"{title} ({amount_stars} ⭐)", amount=amount_stars)]
    invoice_params = {
        "chat_id": chat_id, "title": title, "description": description,
        "payload": payload_uuid, "currency": "XTR", "prices": prices, "is_flexible": False
    }
    if photo_url:
        invoice_params["photo_url"] = photo_url
        invoice_params["photo_width"] = 512
        invoice_params["photo_height"] = 512
    try:
        await bot.send_invoice(**invoice_params)
        logger.info(f"Invoice for {amount_stars} XTR (Payload: {payload_uuid}) sent to user {user_id} for '{title}'.")
        return True
    except Exception as e:
        logger.error(f"Error sending invoice to user {user_id} for '{title}': {e}", exc_info=True)
        await bot.send_message(chat_id,
                               "Не удалось создать счет на оплату. Пожалуйста, попробуйте позже или свяжитесь с поддержкой.")
        return False


@payment_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or f"id_{user_id}"
    args = message.text.split(maxsplit=1)
    payload_arg = args[1] if len(args) > 1 else None
    logger.info(f"User {user_id} (@{username}) started payment bot. Payload arg: '{payload_arg}'")
    try:
        if not await database.user_exists(user_id):
            lang_code = message.from_user.language_code if message.from_user.language_code in ['ru', 'en',
                                                                                               'uk'] else 'ru'
            await database.add_user(user_id, username, lang=lang_code)
            logger.info(f"New user {user_id} (@{username}) registered in DB via payment bot.")
        else:
            # Опционально: Обновляем username, если он изменился
            stored_username = await database.get_user_username(user_id)
            if stored_username != username: await database.update_user_username(user_id, username)
    except Exception as e:
        logger.error(f"Error checking/adding user {user_id} to DB: {e}")
        await message.answer("Произошла ошибка при инициализации. Попробуйте /start еще раз.")
        return
    # Обработка deep link аргументов
    if payload_arg:
        if payload_arg == "topup":
            await route_to_top_up(message, state);
            return
        elif payload_arg == "boost":
            await route_to_buy_boost_menu(message, state);
            return
        # Можно добавить обработку других аргументов
    # Стандартное приветствие
    await message.answer(
        f"Привет, {hbold(message.from_user.full_name)}!\n\n"
        "Здесь ты можешь пополнить свой баланс или приобрести бусты для основного бота, используя Telegram Stars ✨.",
        reply_markup=get_main_payment_keyboard()
    )


async def route_to_top_up(message_or_callback: Message | CallbackQuery, state: FSMContext):
    msg_target = message_or_callback if isinstance(message_or_callback, Message) else message_or_callback.message
    text = ("✨ Пополняем баланс Telegram Stars! ✨\n\n"
            "Выберите готовую сумму или введите свою, нажав на соответствующую кнопку.")
    reply_markup = get_topup_amount_keyboard()
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer()
        try:
            # Попытка отредактировать сообщение
            await msg_target.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            # Если не получилось отредактировать (например, сообщение старое), отправляем новое
            logger.warning(f"Could not edit msg for topup amount prompt (user: {msg_target.chat.id}): {e}")
            await msg_target.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        # Если это было сообщение /start topup, просто отвечаем
        await msg_target.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def route_to_buy_boost_menu(message_or_callback: Message | CallbackQuery, state: FSMContext):
    msg_target = message_or_callback if isinstance(message_or_callback, Message) else message_or_callback.message
    if isinstance(message_or_callback, CallbackQuery): await message_or_callback.answer()  # Отвечаем на callback
    boost_options = p_settings.BOOST_OPTIONS
    if not boost_options:
        text_reply = "😔 К сожалению, доступных бустов сейчас нет. Загляните позже!"
        # Если это callback, показываем клавиатуру главного меню
        rm = get_main_payment_keyboard() if isinstance(message_or_callback, CallbackQuery) else None
        if isinstance(message_or_callback, CallbackQuery):
            await msg_target.edit_text(text_reply, reply_markup=rm, parse_mode=ParseMode.HTML)
        else:
            await msg_target.answer(text_reply, reply_markup=rm, parse_mode=ParseMode.HTML)
        return
    text = "🚀 <b>Выберите буст для покупки:</b>\n\n"
    for boost_id_key, boost_info in boost_options.items():
        text += f"<b>{boost_info['name']}</b> ({boost_info['price_stars']} ⭐)\n{boost_info['description']}\n\n"
    rm = get_boost_selection_keyboard()  # Клавиатура выбора буста
    if isinstance(message_or_callback, CallbackQuery):
        await msg_target.edit_text(text, reply_markup=rm, parse_mode=ParseMode.HTML)
    else:
        await msg_target.answer(text, reply_markup=rm, parse_mode=ParseMode.HTML)
    await state.set_state(PaymentStates.choosing_boost)  # Устанавливаем состояние ожидания выбора буста


@payment_router.callback_query(F.data == "top_up_balance")
async def cb_top_up_balance(callback: CallbackQuery, state: FSMContext):
    await route_to_top_up(callback, state)


@payment_router.callback_query(F.data == "buy_boost_menu")
async def cb_buy_boost_menu(callback: CallbackQuery, state: FSMContext):
    await route_to_buy_boost_menu(callback, state)


@payment_router.callback_query(F.data == "back_to_payment_main")
async def cb_back_to_payment_main(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    current_state = await state.get_state()
    if current_state is not None:
        logger.info(f"User {callback.from_user.id} clearing state {current_state} and returning to main payment menu.")
        await state.clear()
    try:
        await callback.message.edit_text("Вы вернулись в главное меню платежей.",
                                         reply_markup=get_main_payment_keyboard())
    except Exception as e:
        # Если редактирование не удалось, отправляем новое сообщение
        logger.warning(f"Could not edit message on back_to_payment_main for user {callback.from_user.id}: {e}")
        await callback.message.answer("Вы вернулись в главное меню платежей.", reply_markup=get_main_payment_keyboard())


@payment_router.callback_query(F.data == "topup_manual_amount")
async def cb_topup_manual_amount(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "✍️ Введите желаемую сумму пополнения в Telegram Stars (например, 150):",
        reply_markup=get_back_to_main_payment_menu_keyboard()  # Кнопка "Назад в меню"
    )
    await state.set_state(PaymentStates.waiting_for_topup_amount)


@payment_router.callback_query(F.data.startswith("topup_preset:"))
async def cb_topup_preset(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        amount_stars = int(callback.data.split(":", 1)[1])
        logger.info(f"User {callback.from_user.id} selected preset top-up of {amount_stars} Stars.")
        await callback.message.delete()  # Удаляем сообщение с кнопками выбора суммы
        await send_stars_invoice(
            chat_id=callback.message.chat.id, user_id=callback.from_user.id, amount_stars=amount_stars,
            title="Пополнение баланса", description=f"Пополнение вашего баланса на {amount_stars} Telegram Stars.",
            payload_prefix="topup",  # Используем префикс 'topup'
            photo_url=p_settings.INVOICE_PHOTO_URL_TOPUP
        )
    except (ValueError, IndexError) as e:
        logger.error(f"Error processing preset topup callback '{callback.data}': {e}")
        await callback.message.answer("Произошла ошибка. Попробуйте снова.", reply_markup=get_topup_amount_keyboard())
    await state.clear()  # Очищаем состояние


@payment_router.message(PaymentStates.waiting_for_topup_amount, F.text)
async def process_manual_top_up_amount(message: Message, state: FSMContext):
    try:
        amount_stars = int(message.text.strip())
        # Проверка на минимальную/максимальную сумму, если нужно
        if amount_stars <= 0: await message.reply("Сумма должна быть больше нуля.",
                                                  reply_markup=get_topup_amount_keyboard()); return
        if amount_stars < 1: await message.reply("Минимальная сумма пополнения - 1 ⭐.",
                                                 reply_markup=get_topup_amount_keyboard()); return
        # if amount_stars > MAX_SUM: ...
    except ValueError:
        await message.reply("Пожалуйста, введите число (например, 100).", reply_markup=get_topup_amount_keyboard());
        return
    logger.info(f"User {message.from_user.id} manually entered top-up of {amount_stars} Stars.")
    await send_stars_invoice(
        chat_id=message.chat.id, user_id=message.from_user.id, amount_stars=amount_stars,
        title="Пополнение баланса", description=f"Пополнение вашего баланса на {amount_stars} Telegram Stars.",
        payload_prefix="topup",  # Используем префикс 'topup'
        photo_url=p_settings.INVOICE_PHOTO_URL_TOPUP
    )
    await state.clear()  # Очищаем состояние


@payment_router.callback_query(PaymentStates.choosing_boost, F.data.startswith("confirm_boost_purchase:"))
async def cb_confirm_boost_purchase(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    boost_id_key = callback.data.split(":", 1)[1]
    selected_boost = p_settings.BOOST_OPTIONS.get(boost_id_key)
    if not selected_boost:
        await callback.message.edit_text("Ошибка: Буст не найден.", reply_markup=get_main_payment_keyboard())
        await state.clear();
        return
    # Получаем данные буста
    price_stars = selected_boost['price_stars'];
    boost_name = selected_boost['name'];
    boost_description = selected_boost['description']
    logger.info(f"User {callback.from_user.id} confirms purchase of boost '{boost_name}' for {price_stars} Stars.")
    try:
        await callback.message.delete()  # Удаляем сообщение выбора буста
    except Exception as e:
        logger.warning(f"Could not delete boost selection message for user {callback.from_user.id}: {e}")
    # Отправляем инвойс на покупку буста
    await send_stars_invoice(
        chat_id=callback.message.chat.id, user_id=callback.from_user.id, amount_stars=price_stars,
        title=f"Покупка: {boost_name}", description=f"{boost_description}\nСтоимость: {price_stars} Telegram Stars.",
        payload_prefix=f"buyboost_{boost_id_key}",  # Формируем payload с ключом буста
        photo_url=p_settings.INVOICE_PHOTO_URL_BOOST
    )
    await state.clear()  # Очищаем состояние


@payment_router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    # Здесь можно добавить проверки перед подтверждением платежа (например, наличие буста, не истек ли он)
    # Для простоты пока просто подтверждаем
    await pre_checkout_query.answer(ok=True)
    logger.info(
        f"PreCheckoutQuery {pre_checkout_query.id} for user {pre_checkout_query.from_user.id} (payload: {pre_checkout_query.invoice_payload}) answered OK.")


@payment_router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    user_id = message.from_user.id;
    username = message.from_user.username or f"id_{user_id}"
    payment_info = message.successful_payment;
    currency = payment_info.currency
    total_amount_stars = payment_info.total_amount;  # Это сумма в минимальных единицах валюты (для XTR 1 star = 1 unit)
    invoice_payload = payment_info.invoice_payload  # Payload, который мы передавали
    logger.info(
        f"Successful payment from user {user_id} (@{username}): {total_amount_stars} {currency}. Payload: {invoice_payload}")
    # Проверяем валюту
    if currency != "XTR":
        logger.error(f"Received successful payment for non-XTR currency: {currency} from user {user_id}.")
        await message.answer("Произошла ошибка с валютой платежа. Пожалуйста, обратитесь в поддержку.");
        await notify_admins(f"⚠️ Ошибка валюты! User: {user_id}, Payload: {invoice_payload}, Curr: {currency}");
        return
    # Обработка в зависимости от payload
    if invoice_payload.startswith("topup_"):
        try:
            # Добавляем звезды пользователю в основной БД
            await database.add_stars(user_id, float(total_amount_stars))  # Добавляем сумму напрямую
            success_msg = (f"✅ Баланс успешно пополнен на {hbold(total_amount_stars)} Stars!\n\n"
                           f"Ваши звёзды доступны в <a href=\"https://t.me/{p_settings.MAIN_BOT_USERNAME}\">основном боте</a>.")
            await message.answer(success_msg, reply_markup=get_main_payment_keyboard())
            logger.info(f"Topped up {total_amount_stars} stars for user {user_id}.")
            await notify_admins(f"💳 @{username} ({user_id}) пополнил баланс на {total_amount_stars} Stars.")
        except Exception as e:
            logger.exception(f"Error processing successful top-up for user {user_id}: {e}")
            await message.answer("Произошла ошибка при зачислении звёзд. Пожалуйста, свяжитесь с поддержкой.");
            await notify_admins(f"🆘 Ошибка зачисления звёзд! User: {user_id}, Payload: {invoice_payload}, Error: {e}")
    elif invoice_payload.startswith("buyboost_"):
        try:
            # --- ИСПРАВЛЕННЫЙ БЛОК ИЗВЛЕЧЕНИЯ boost_id_key ---
            boost_id_key = None
            for key in p_settings.BOOST_OPTIONS.keys():
                prefix_to_check = f"buyboost_{key}_"
                if invoice_payload.startswith(prefix_to_check):
                    boost_id_key = key
                    break
            # --- КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ---

            # Проверяем, нашли ли мы ключ и есть ли он в настройках
            if not boost_id_key or boost_id_key not in p_settings.BOOST_OPTIONS:
                log.error(
                    f"Unknown boost_id derived from payload '{invoice_payload}' for user {user_id}. Derived key: '{boost_id_key}'")
                await message.answer("Ошибка: неизвестный буст. Свяжитесь с поддержкой.");
                await notify_admins(
                    f"⚠️ Ошибка покупки буста! User: {user_id}, Payload: {invoice_payload}, Неизвестный ключ: {boost_id_key}");
                return

            selected_boost = p_settings.BOOST_OPTIONS[boost_id_key];
            boost_name = selected_boost['name'];
            boost_price = selected_boost['price_stars']
            # Проверка соответствия суммы (на всякий случай)
            if total_amount_stars != boost_price:
                logger.error(
                    f"Price mismatch for boost '{boost_name}'. Expected {boost_price}, paid {total_amount_stars}. User: {user_id}")
                await message.answer(
                    f"Произошла ошибка с суммой оплаты буста «{boost_name}». Пожалуйста, свяжитесь с поддержкой.");
                await notify_admins(
                    f"🆘 Ошибка суммы буста! User: {user_id}, Boost: {boost_name}, Expected: {boost_price}, Paid: {total_amount_stars}");
                return

            # Активируем буст в БД
            boost_details_for_db = {
                "price_stars": boost_price,
                "purchased_at": message.date.isoformat(),  # Время покупки
                # Берем остальные параметры из настроек
                "duration_hours": selected_boost.get("duration_hours"),
                "type": selected_boost.get("type"),
                "effect_value": selected_boost.get("effect_value")
            }
            activation_success = await database.activate_boost_in_db(user_id, boost_id_key, boost_details_for_db)

            if activation_success:
                success_msg = (
                    f"🚀 Буст «{hbold(boost_name)}» успешно приобретен за {hbold(total_amount_stars)} Stars!\n\n"
                    f"Он будет автоматически активирован в <a href=\"https://t.me/{p_settings.MAIN_BOT_USERNAME}\">основном боте</a>.")
                await message.answer(success_msg, reply_markup=get_main_payment_keyboard())
                logger.info(f"Processed boost '{boost_name}' purchase for user {user_id}.")
                await notify_admins(
                    f"🚀 @{username} ({user_id}) купил буст «{boost_name}» за {total_amount_stars} Stars.")
            else:
                # Если активация в БД не удалась
                logger.error(f"Failed to activate boost '{boost_name}' in DB for user {user_id}.")
                await message.answer(
                    "Буст был оплачен, но произошла ошибка при его активации. Пожалуйста, свяжитесь с поддержкой.");
                await notify_admins(f"🆘 Ошибка активации буста в БД! User: {user_id}, Boost: {boost_name}")
        except Exception as e:
            logger.exception(f"Error processing successful boost purchase for user {user_id}: {e}")
            await message.answer("Произошла ошибка при активации буста. Пожалуйста, свяжитесь с поддержкой.");
            await notify_admins(
                f"🆘 Ошибка обработки покупки буста! User: {user_id}, Payload: {invoice_payload}, Error: {e}")
    else:
        # Если payload не распознан
        logger.warning(f"Unknown successful payment payload: {invoice_payload} from user {user_id}")
        await message.answer(
            "Платёж получен, но его назначение не удалось определить. Пожалуйста, свяжитесь с поддержкой.");
        await notify_admins(f"⚠️ Неизвестный payload платежа! User: {user_id}, Payload: {invoice_payload}")


async def on_payment_bot_startup(dispatcher: Dispatcher):
    logger.info("Payment bot starting up...")
    try:
        # Используем стандартную init_db_pool, если кастомная не нужна/не найдена
        await database.init_db_pool()
        logger.info("DB pool initialized for payment bot.")
    except AttributeError:
        logger.warning("init_db_pool_custom not found, trying init_db_pool.")
        try:
            await database.init_db_pool()
        except Exception as e_std:
            logger.critical(f"Standard DB pool init failed: {e_std}", exc_info=True);
            raise
    except Exception as e:
        logger.critical(f"Custom DB pool init failed: {e}", exc_info=True);
        raise
    # Можно добавить уведомление админам о запуске платежного бота
    # await notify_admins("Платежный бот запущен.")


async def on_payment_bot_shutdown(dispatcher: Dispatcher):
    logger.info("Payment bot shutting down...")
    # Можно добавить уведомление админам об остановке
    # await notify_admins("Платежный бот останавливается.")
    await database.close_db_pool();
    logger.info("DB pool closed for payment bot.")


async def main_polling():
    dp.include_router(payment_router)
    dp.startup.register(on_payment_bot_startup)
    dp.shutdown.register(on_payment_bot_shutdown)
    logger.info("Starting payment bot polling...")
    try:
        # Удаляем необработанные обновления при старте
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"Payment bot polling crashed: {e}", exc_info=True)
    finally:
        await bot.session.close()  # Закрываем сессию бота
        logger.info("Payment bot polling stopped and session closed.")


if __name__ == "__main__":
    try:
        asyncio.run(main_polling())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Payment Bot stopped by user.")
    except Exception as e:
        logger.critical(f"Payment Bot main_polling function crashed: {e}", exc_info=True)
