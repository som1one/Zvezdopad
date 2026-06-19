import logging
import asyncpg
import asyncio
import time
from html import escape

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import MessageCantBeDeleted, MessageToDeleteNotFound, InvalidQueryID

import database
from settings import (
    CHANEL_ID, LOG_VIVOD_CHANEL, SUP_LOGIN
)
from utils import t, format_datetime, send_gift_with_retry, sanitize_username, mask_username, mask_id
from keyboards import create_back_button, create_withdrawal_buttons, create_admin_withdrawal_markup
from handlers.common import check_subscription
from handlers.user_menu import show_main_menu
from datetime import datetime, timezone

log = logging.getLogger('handlers.user_withdrawal')


async def show_withdraw_menu(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    log.info(f"User {user_id}: Showing withdrawal menu.")

    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"User {user_id}: InvalidQueryID caught for {call.data} (show_withdraw_menu).");
        return
    except Exception as e:
        log.error(f"User {user_id}: Error answering callback for {call.data} (show_withdraw_menu): {e}");
        return

    if not await database.are_withdrawals_enabled():
        log.warning(f"User {user_id}: Tried to access withdrawals while disabled.")
        disabled_message_text = t(user_id, 'withdrawals_disabled_message')
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        await bot.send_message(user_id, disabled_message_text)
        return

    log.debug(f"User {user_id}: Checking subscription before showing withdraw menu...")
    start_sub_check = time.monotonic()
    is_subscribed = await check_subscription(bot, user_id, chat_id)
    duration_sub_check = time.monotonic() - start_sub_check
    log.info(f"User {user_id}: Subscription check result: {is_subscribed}. Duration: {duration_sub_check:.3f}s")

    if not is_subscribed:
        try:
            await call.message.delete()
        except (MessageCantBeDeleted, MessageToDeleteNotFound):
            pass
        await bot.send_message(user_id, t(user_id, "not_subscribed"))
        return

    if await database.is_user_blocked(user_id):
        log.warning(f"User {user_id}: Blocked user tried to access withdraw menu.")
        await bot.send_message(user_id, "❌ Вы заблокированы!")
        return

    user_data = await database.get_user(user_id)
    if not user_data:
        log.warning(f"User {user_id}: Not found in DB when accessing withdraw menu.")
        await bot.send_message(user_id, t(user_id, 'no_registration'))
        return

    stars = user_data['stars']
    refs_weekly = await database.get_referrals_count_week(user_id)
    exchange_req = await database.get_exchange_referral_req()
    log.debug(f"User {user_id}: Balance={stars:.2f}, WeeklyRefs={refs_weekly}, Req={exchange_req}")

    caption = (
        f"🔸 <b>У тебя на счету:</b> <code>{stars:.2f}</code>⭐️\n\n"
        f"‼️ <b>Для обмена звёзд требуется {exchange_req} рефералов за текущую неделю.</b>\n"
        f"   └ У тебя сейчас: <code>{refs_weekly}</code>\n\n"
        f"<b>Выбери подарок для обмена звёзд из доступных вариантов ниже:</b>"
    )
    markup = create_withdrawal_buttons(user_id, stars)
    image_path = "images/obmen.jpg"

    try:
        await call.message.delete()
    except (MessageCantBeDeleted, MessageToDeleteNotFound):
        pass

    try:
        with open(image_path, "rb") as photo:
            await call.message.answer_photo(photo=photo, caption=caption, reply_markup=markup, parse_mode="HTML")
    except FileNotFoundError:
        log.error(f"Withdrawal image not found: {image_path}")
        await call.message.answer(caption, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        log.exception(f"User {user_id}: Error displaying withdrawal menu: {e}")
        await call.message.answer(caption, reply_markup=markup, parse_mode="HTML")

    log.info(f"User {user_id}: Successfully shown withdrawal menu.")


async def handle_withdraw_request(call: CallbackQuery, bot: Bot, app):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    start_time = time.monotonic()
    log.info(f"User {user_id}: Starting handle_withdraw_request. Callback data: {call.data}")

    amt = 0
    star_gift_id = None
    emoji = "❓"
    is_premium_request = False

    try:
        parts = call.data.split(":")
        action = parts[0]
        amount_str = parts[1]
        type_or_gift_id = parts[2] if len(parts) > 2 else None
        if not amount_str.isdigit(): raise ValueError("Amount not digit")
        amt = int(amount_str)

        if amt == 1700 and type_or_gift_id == 'premium':
            is_premium_request = True;
            emoji = "📱";
            star_gift_id = None
        elif amt > 0:
            is_premium_request = False
            amounts_map = {15: [("🧸", 5170233102089322756), ("💝", 5170145012310081615)],
                           25: [("🌹", 5168103777563050263), ("🎁", 5170250947678437525)],
                           50: [("🍾", 6028601630662853006), ("🚀", 5170564780938756245), ("💐", 5170314324215857265),
                                ("🎂", 5170144170496491616)],
                           100: [("🏆", 5168043875654172773), ("💍", 5170690322832818290), ("💎", 5170521118301225164)], }
            emoji = "❓";
            star_gift_id = None
            if amt in amounts_map:
                possible_gifts = amounts_map[amt]
                if type_or_gift_id and type_or_gift_id.isdigit():
                    gift_id_from_callback = int(type_or_gift_id)
                    for em, gid in possible_gifts:
                        if gid == gift_id_from_callback: emoji = em; star_gift_id = gid; break
                if star_gift_id is None and possible_gifts: emoji, star_gift_id = possible_gifts[0]
            if star_gift_id is None and not is_premium_request: raise ValueError(
                f"Could not determine gift ID for amount {amt}")
        else:
            raise ValueError("Amount must be positive")
        log.info(
            f"User {user_id}: Parsed withdrawal request: amount={amt}, emoji='{emoji}', gift_id={star_gift_id}, premium={is_premium_request}")
    except (ValueError, IndexError) as e:
        log.error(f"User {user_id}: Error parsing withdraw callback data '{call.data}': {e}")
        try:
            await call.answer("Ошибка обработки запроса.", show_alert=True)
        except InvalidQueryID:
            log.warning(f"User {user_id}: IQID fail answering parse error")
        except Exception as err:
            log.error(f"User {user_id}: Error answering cb parse error: {err}")
        return

    log.debug(f"User {user_id}: Starting pre-checks for withdrawal...")
    start_prechecks = time.monotonic()

    if not await database.are_withdrawals_enabled():
        log.warning(f"User {user_id}: Withdrawals disabled during request confirmation (amount {amt}).")
        try:
            await call.answer(t(user_id, 'withdrawals_disabled_message'), show_alert=True)
        except InvalidQueryID:
            log.warning(f"User {user_id}: IQID fail answering withdrawals disabled")
        except Exception as err:
            log.error(f"User {user_id}: Error answering cb withdrawals disabled: {err}")
        return

    log.debug(f"User {user_id}: Checking subscription...")
    is_subscribed = await check_subscription(bot, user_id, chat_id)
    log.debug(f"User {user_id}: Subscription check result: {is_subscribed}")
    if not is_subscribed:
        try:
            await call.answer(t(user_id, "not_subscribed"), show_alert=True)
        except InvalidQueryID:
            log.warning(f"User {user_id}: IQID fail answering not subscribed")
        except Exception as err:
            log.error(f"User {user_id}: Error answering cb not subscribed: {err}")
        return

    if await database.is_user_blocked(user_id):
        log.warning(f"User {user_id}: Blocked user tried to confirm withdrawal.")
        try:
            await call.answer("Вы заблокированы.", show_alert=True)
        except InvalidQueryID:
            log.warning(f"User {user_id}: IQID fail answering blocked")
        except Exception as err:
            log.error(f"User {user_id}: Error answering cb blocked: {err}")
        return

    refs_weekly = await database.get_referrals_count_week(user_id)
    exchange_req = await database.get_exchange_referral_req()
    log.debug(f"User {user_id}: Weekly refs={refs_weekly}, Req={exchange_req}")
    if refs_weekly < exchange_req:
        error_msg = t(user_id, 'withdrawal_referral_req_not_met').format(required=exchange_req, action_type="обмена",
                                                                         current=refs_weekly)
        log.warning(f"User {user_id}: Referral requirement not met ({refs_weekly}/{exchange_req}).")
        try:
            await call.answer(error_msg, show_alert=True)
        except InvalidQueryID:
            log.warning(f"User {user_id}: IQID fail answering ref req not met")
        except Exception as err:
            log.error(f"User {user_id}: Error answering cb ref req not met: {err}")
        return

    duration_prechecks = time.monotonic() - start_prechecks
    log.info(f"User {user_id}: Pre-checks passed. Duration: {duration_prechecks:.3f}s")

    pool = database.db_pool
    if not pool:
        log.error("DB pool not initialized!")
        await bot.send_message(user_id, "Ошибка БД.")
        return

    conn = None
    request_id = None
    start_db_tx = time.monotonic()
    log.info(f"User {user_id}: Starting database transaction for withdrawal...")

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                log.debug(f"User {user_id}: DB Transaction acquired.")

                user_data_db = await conn.fetchrow("SELECT stars, username FROM users WHERE id = $1 FOR UPDATE",
                                                   user_id)
                if not user_data_db:
                    log.error(f"User {user_id}: Not found in DB during withdrawal confirmation (inside TX).")
                    await call.answer("Ошибка: Пользователь не найден.", show_alert=True)
                    return

                current_stars = user_data_db['stars']
                log.debug(f"User {user_id}: Balance inside TX: {current_stars:.2f}")

                if amt > current_stars:
                    log.warning(f"User {user_id}: Insufficient balance inside TX ({current_stars:.2f} < {amt}).")
                    await call.answer(t(user_id, 'not_enough_stars'), show_alert=True)
                    return

                exchange_limit = await database.get_exchange_daily_limit()
                exchange_count_today = await database.get_daily_withdrawal_count(user_id, 'exchange')
                log.debug(f"User {user_id}: Daily exchange count={exchange_count_today}, Limit={exchange_limit}")
                if exchange_count_today >= exchange_limit:
                    limit_msg = t(user_id, 'withdrawal_limit_reached').format(limit_type="обычных обменов",
                                                                              count=exchange_count_today,
                                                                              limit=exchange_limit)
                    log.warning(
                        f"User {user_id}: Daily exchange limit reached ({exchange_count_today}/{exchange_limit}).")
                    await call.answer(limit_msg, show_alert=True)
                    return

                log.debug(f"User {user_id}: Attempting to withdraw stars...")
                success_withdraw = await database.withdraw_stars(conn, user_id, amt)
                if not success_withdraw:
                    current_stars_check = await conn.fetchval("SELECT stars FROM users WHERE id = $1", user_id)
                    log.warning(
                        f"User {user_id}: Withdraw failed INSIDE TRANSACTION for amount {amt}. Balance: {current_stars_check}")
                    await bot.send_message(user_id, t(user_id, 'not_enough_stars'))
                    return
                log.info(f"User {user_id}: Stars withdrawn successfully ({amt}).")

                user_full_name = escape(call.from_user.full_name or user_data_db['username'] or f'ID: {user_id}')
                admin_description = f"{emoji} {user_full_name}"
                if is_premium_request:
                    admin_description = f"📱 Premium request by {user_full_name}"

                log.debug(f"User {user_id}: Inserting withdrawal request...")
                request_id = await conn.fetchval('''
                    INSERT INTO withdraw_requests (user_id, amount, status, gift_id, emoji, request_time)
                    VALUES ($1, $2, 'pending', $3, $4, CURRENT_TIMESTAMP)
                    RETURNING id
                ''', user_id, amt, star_gift_id, admin_description)

                if not request_id:
                    raise Exception("Failed to insert withdrawal request and get ID.")
                log.info(
                    f"User {user_id}: Withdrawal request {request_id} recorded: amount={amt}, gift_id={star_gift_id}.")

                log.debug(f"User {user_id}: Incrementing daily withdrawal count...")
                # ----- ИСПРАВЛЕНИЕ -----
                # Передаем объект conn первым аргументом
                if not await database.increment_daily_withdrawal_count(conn, user_id, 'exchange'):
                    # ----------------------
                    log.error(f"User {user_id}: Failed to increment daily withdrawal count. Rolling back.")
                    raise Exception("Counter increment failed")
                log.info(f"User {user_id}: Daily withdrawal count incremented.")

            log.info(f"User {user_id}: DB Transaction committed successfully for request {request_id}.")
        duration_db_tx = time.monotonic() - start_db_tx
        log.info(f"User {user_id}: DB Transaction duration: {duration_db_tx:.3f}s")

        start_notifications = time.monotonic()
        if request_id:
            admin_markup = create_admin_withdrawal_markup(user_id, amt, emoji, request_id)
            user_display_name = escape(call.from_user.username or f"id_{user_id}")
            withdrawal_channel_message = (
                f"<b>✅ Запрос на обмен №{request_id}</b>\n\n"
                f"👤 Пользователь: @{user_display_name} | ID: <code>{user_id}</code>\n"
                f"💫 Количество: <code>{amt}</code>⭐️ [{emoji}]\n\n"
                f"🔄 Статус: <b>Ожидает обработки ⚙️</b>"
            )
            try:
                log.debug(f"User {user_id}, Req {request_id}: Sending message to main channel {CHANEL_ID}...")
                await bot.send_message(CHANEL_ID, withdrawal_channel_message, reply_markup=admin_markup,
                                       parse_mode="HTML")
                log.info(
                    f"User {user_id}: Sent withdrawal request {request_id} message to main channel {CHANEL_ID}.")
            except Exception as e:
                log.error(f"User {user_id}, Req {request_id}: Failed send main chan {CHANEL_ID}: {e}")

            try:
                user_data_log = await database.get_user(user_id)
                withdrawn_total = (user_data_log['withdrawn'] if user_data_log else 0)
                click_count = user_data_log['click_count'] if user_data_log else 0
                gift_count = user_data_log['gift_count'] if user_data_log else 0
                registration_time_formatted = format_datetime(
                    user_data_log['registration_time']) if user_data_log else 'N/A'
                refs_data = await database.get_referrals(user_id)
                last_refs_text = "\n".join(
                    f"• @{escape(sanitize_username(mask_username(ref['username'])))}<code>({mask_id(ref['id'])})</code>: {ref['stars']:.1f}⭐️"
                    for ref in refs_data[:5]
                ) or "Нет"
                log_details_message = (
                    f"<b>ℹ️ Детали запроса №{request_id}</b>\n\n"
                    f"👤 Пользователь: @{user_display_name} | ID: <code>{user_id}</code>\n"
                    f"💫 Сумма: <code>{amt}</code>⭐️ {emoji} (GiftID: {star_gift_id or 'N/A'})\n\n"
                    f"📊 Статистика:\n"
                    f"  👥 Рефы (неделя): <b>{refs_weekly}</b>\n"
                    f"  💰 Всего выведено: <b>{withdrawn_total:.2f}⭐️</b>\n"
                    f"  🖱 Клики: <b>{click_count}</b> | 🎁 Подарки: <b>{gift_count}</b>\n"
                    f"  📅 Регистрация: <code>{registration_time_formatted}</code>\n\n"
                    f"👥 Последние 5 рефералов:\n{last_refs_text}\n"
                )
                await asyncio.sleep(0.1)
                log.debug(
                    f"User {user_id}, Req {request_id}: Sending details to log channel {LOG_VIVOD_CHANEL}...")
                await bot.send_message(LOG_VIVOD_CHANEL, log_details_message, parse_mode="HTML",
                                       disable_web_page_preview=True)
                log.info(
                    f"User {user_id}: Sent withdrawal request {request_id} details to log channel {LOG_VIVOD_CHANEL}.")
            except Exception as e:
                log.error(f"User {user_id}, Req {request_id}: Failed send log chan {LOG_VIVOD_CHANEL}: {e}")

            try:
                user_notification_text = (
                    f"✅ <b>Твой запрос на вывод №{request_id}</b> ({amt}⭐️) успешно создан.\n"
                    f"🔍 Ожидай обработки и следи за статусом в канале выплат.\n\n"
                    f"<blockquote>‼️ Чтобы выплата прошла быстрее, напиши любое сообщение поддержке: @{SUP_LOGIN}</blockquote>"
                )
                await asyncio.sleep(0.1)
                log.debug(f"User {user_id}, Req {request_id}: Sending confirmation message to user...")
                await bot.send_message(user_id, user_notification_text, parse_mode="HTML",
                                       disable_web_page_preview=True)
                log.info(f"User {user_id}: Sent withdrawal confirmation for request {request_id}.")
            except Exception as e:
                log.error(f"User {user_id}, Req {request_id}: Failed send confirm to user: {e}")

            try:
                await call.message.delete()
            except Exception as e:
                log.warning(
                    f"User {user_id}: Could not delete withdrawal menu message {call.message.message_id}: {e}")

            duration_notifications = time.monotonic() - start_notifications
            log.info(f"User {user_id}, Req {request_id}: Notifications duration: {duration_notifications:.3f}s")

            await show_main_menu(call.message, user_id, bot, edit=False)
        else:
            log.error(
                f"User {user_id}: Transaction committed but request_id is missing for amount {amt}. Balance likely deducted.")
            await bot.send_message(user_id, "Произошла ошибка при создании заявки (нет ID). Баланс мог измениться.")

    except Exception as e:
        log.exception(f"User {user_id}: Error processing withdrawal request (amount {amt}): {e}")
        await bot.send_message(user_id, "Произошла ошибка при создании заявки на вывод.")
        try:
            if call.message:
                await show_main_menu(call.message, user_id, bot, edit=False)
        except Exception as menu_err:
            log.error(f"User {user_id}: Failed to show main menu after withdrawal error: {menu_err}")

    finally:
        duration_total = time.monotonic() - start_time
        log.info(f"User {user_id}: Finished handle_withdraw_request. Total duration: {duration_total:.3f}s")


async def handle_insufficient_funds(call: CallbackQuery):
    user_id = call.from_user.id
    log.warning(f"User {user_id}: Clicked insufficient funds button. Callback: {call.data}")
    try:
        await call.answer(t(user_id, 'not_enough_stars'), show_alert=True)
    except InvalidQueryID:
        log.warning(f"User {user_id}: InvalidQueryID caught for {call.data} (insufficient_funds).")
    except Exception as e:
        log.error(f"User {user_id}: Error answering callback for {call.data} (insufficient_funds): {e}")


def register_user_withdrawal_handlers(dp: Dispatcher, bot: Bot, app):
    dp.register_callback_query_handler(lambda call: show_withdraw_menu(call, bot),
                                       lambda c: c.data == "withdraw_stars_menu", state="*")
    dp.register_callback_query_handler(lambda call: handle_withdraw_request(call, bot, app),
                                       lambda c: c.data.startswith("withdraw:"), state="*")
    dp.register_callback_query_handler(handle_insufficient_funds, lambda c: c.data == "insufficient_funds", state="*")
    log.info("User withdrawal handlers registered.")
