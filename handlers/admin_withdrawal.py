import logging
import asyncpg
import asyncio
from datetime import datetime, timezone

from aiogram import types, Bot, Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.exceptions import TelegramAPIError, InvalidQueryID, MessageNotModified

import database
from settings import ADMIN_IDS, CHANEL_ID, SUP_LOGIN, LOG_VIVOD_CHANEL
from utils import send_gift_with_retry, format_datetime
from keyboards import create_admin_withdrawal_markup, create_admin_panel_markup

log = logging.getLogger('handlers.admin_withdrawal')


async def handle_paid_status(call: CallbackQuery, bot: Bot, app):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        try:
            await call.answer("⛔ У вас нет прав!", show_alert=True)
        except InvalidQueryID:
            pass
        except Exception as e:
            log.error(f"Error answering cb (no rights) handle_paid_status: {e}")
        return

    try:
        parts = call.data.split(":")
        if len(parts) < 5: raise ValueError("Incorrect parts count")
        target_user_id = int(parts[1]);
        amount = int(parts[2]);
        emoji = parts[3];
        request_id = int(parts[4])
    except (ValueError, IndexError) as e:
        log.error(f"Error parsing 'paid' callback data '{call.data}': {e}")
        try:
            await call.answer("Ошибка данных колбэка.", show_alert=True)
        except InvalidQueryID:
            pass
        except Exception as ans_e:
            log.error(f"Error answering cb (parse error) handle_paid_status: {ans_e}")
        return

    try:
        await call.answer()
    except InvalidQueryID:
        log.warning(f"IQID fail on initial answer in handle_paid_status for request {request_id}")
    except Exception as e:
        log.error(f"Error on initial answer cb handle_paid_status req {request_id}: {e}")
        return

    log.info(f"Admin {admin_id} approves withdrawal request {request_id} for user {target_user_id}, amount {amount}")

    pool = database.db_pool
    if not pool:
        log.error("DB pool not initialized!")
        try:
            await call.answer("Ошибка БД.", show_alert=True)
        except:
            pass
        return

    gift_id = None
    request_status = 'pending'
    conn = None
    update_message_after_db = True

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():

                req_data = await conn.fetchrow(
                    "SELECT gift_id, status, user_id, amount FROM withdraw_requests WHERE id = $1 FOR UPDATE",
                    request_id)
                if not req_data:
                    update_message_after_db = False
                    await call.answer(f"Заявка №{request_id} не найдена.", show_alert=True)
                    return

                gift_id = req_data['gift_id']
                request_status = req_data['status']
                db_user_id = req_data['user_id']
                db_amount = req_data['amount']

                if db_user_id != target_user_id or db_amount != amount:
                    log.error(
                        f"Mismatch data req {request_id}. CB: user={target_user_id}, amt={amount}. DB: user={db_user_id}, amt={db_amount}")
                    update_message_after_db = False
                    await call.answer("Несоответствие данных!", show_alert=True)
                    return

                if request_status != 'pending':
                    update_message_after_db = False
                    await call.answer(f"Заявка №{request_id} уже обработана ({request_status}).", show_alert=True)
                    return

                if amount == 1700 and gift_id is None:
                    log.warning(f"Withdrawal request {request_id} is Premium. Requires manual processing.")
                    await conn.execute(
                        "UPDATE withdraw_requests SET status = 'paid', processed_time = CURRENT_TIMESTAMP WHERE id = $1",
                        request_id)
                    update_message_after_db = True
                    await call.answer("Статус Premium изменен на 'paid'. Выдайте вручную.", show_alert=True)

                    try:
                        await call.message.edit_text(
                            call.message.html_text.replace("Ожидает обработки ⚙️", f"<b>Выдан Premium (вручную) ✅</b>"),
                            parse_mode="HTML", reply_markup=None)
                    except Exception as edit_err:
                        log.warning(f"Failed update premium request message {request_id}: {edit_err}")
                    try:
                        await bot.send_message(target_user_id, f"✅ Заявка №{request_id} на Premium одобрена! Ожидайте.")
                    except Exception as notify_err:
                        log.warning(f"Failed send premium approved notification {target_user_id}: {notify_err}")
                    return

                if not gift_id:
                    log.error(f"Missing gift_id req {request_id}, amount {amount}")
                    await conn.execute(
                        "UPDATE withdraw_requests SET status = 'failed', processed_time = CURRENT_TIMESTAMP WHERE id = $1",
                        request_id)
                    update_message_after_db = True
                    await call.answer(f"Ошибка: Нет Gift ID для заявки №{request_id}.", show_alert=True)

                    try:
                        await call.message.edit_text(
                            call.message.html_text.replace("Ожидает обработки ⚙️", f"<b>Ошибка: нет Gift ID ❌</b>"),
                            parse_mode="HTML",
                            reply_markup=create_admin_withdrawal_markup(target_user_id, amount, emoji, request_id))
                    except Exception as edit_err:
                        log.warning(f"Failed update missing gift_id request msg {request_id}: {edit_err}")
                    return

        gift_sent_successfully = False
        if request_status == 'pending' and gift_id:
            try:
                await send_gift_with_retry(app, target_user_id, gift_id, bot_instance=bot)
                log.info(f"Gift {gift_id} sent successfully req {request_id} user {target_user_id}.")
                gift_sent_successfully = True
            except Exception as e_gift:
                log.exception(f"Failed send gift req {request_id} user {target_user_id}: {e_gift}")
                error_text = f"Ошибка Stars: {str(e_gift)[:100]}"
                async with pool.acquire() as conn_fail:
                    await conn_fail.execute(
                        "UPDATE withdraw_requests SET status = 'failed', processed_time = CURRENT_TIMESTAMP WHERE id = $1 AND status = 'pending'",
                        request_id)
                await call.answer(f"Ошибка отправки Stars: {e_gift}", show_alert=True)
                update_message_after_db = True
                try:
                    current_markup = create_admin_withdrawal_markup(target_user_id, amount, emoji, request_id)
                    await call.message.edit_text(
                        call.message.html_text.replace("Ожидает обработки ⚙️", f"<b>{error_text} ❌</b>"),
                        parse_mode="HTML", reply_markup=current_markup)
                except Exception as edit_err:
                    log.warning(f"Failed update failed request msg {request_id}: {edit_err}")
                return

        if gift_sent_successfully:
            async with pool.acquire() as conn_paid:
                await conn_paid.execute(
                    "UPDATE withdraw_requests SET status = 'paid', processed_time = CURRENT_TIMESTAMP WHERE id = $1 AND status = 'pending'",
                    request_id)
            update_message_after_db = True
            try:
                await call.message.edit_text(
                    call.message.html_text.replace("Ожидает обработки ⚙️", f"<b>Подарок отправлен 🎁</b>"),
                    parse_mode="HTML", reply_markup=None)
            except Exception as edit_err:
                log.warning(f"Failed update paid request msg {request_id}: {edit_err}")
            try:
                await call.answer("✅ Подарок отправлен!", show_alert=False)
            except InvalidQueryID:
                pass
            except Exception as ans_e:
                log.error(f"Error answering cb (gift sent) handle_paid_status: {ans_e}")

            try:
                user_notify_text = (
                    f"🎉 <b>Заявка №{request_id}</b> ({amount}⭐️) выполнена!\n🎁 Отправлено от <a href='https://t.me/{SUP_LOGIN}'>администрации</a>.\n\n🙏 Будем благодарны за отзыв!")
                markup_notify = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🌟 Оставить отзыв", url="https://t.me/ZvezdoPadTGChat/19752"))
                await bot.send_message(target_user_id, user_notify_text, parse_mode="HTML",
                                       disable_web_page_preview=True, reply_markup=markup_notify)
            except Exception as e_notify:
                log.warning(f"Failed send 'paid' notification user {target_user_id}: {e_notify}")

    except asyncpg.PostgresError as db_err:
        log.exception(f"Database error processing 'paid' callback req {request_id}: {db_err}")
        try:
            await call.answer("Ошибка базы данных.", show_alert=True)
        except:
            pass
    except Exception as e:
        log.exception(f"Unexpected error processing 'paid' callback req {request_id}: {e}")
        try:
            await call.answer("Непредвиденная ошибка.", show_alert=True)
        except:
            pass


async def handle_denied_status(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        try:
            await call.answer("⛔ У вас нет прав!", show_alert=True)
        except InvalidQueryID:
            pass
        except Exception as e:
            log.error(f"Error answering cb (no rights) handle_denied_status: {e}")
        return

    try:
        parts = call.data.split(":");
        request_id = int(parts[1])
    except (ValueError, IndexError):
        log.error(f"Error parsing 'denied' callback data '{call.data}'")
        try:
            await call.answer("Ошибка данных.", show_alert=True)
        except InvalidQueryID:
            pass
        except Exception as ans_e:
            log.error(f"Error answering cb (parse error) handle_denied_status: {ans_e}")
        return

    target_user_id = None;
    amount = None;
    request_status = 'pending'
    pool = database.db_pool
    if not pool:
        log.error("DB pool not initialized!")
        try:
            await call.answer("Ошибка БД.", show_alert=True)
        except:
            pass
        return

    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                req_data = await conn.fetchrow(
                    "SELECT user_id, amount, status FROM withdraw_requests WHERE id = $1 FOR UPDATE", request_id)
                if not req_data:
                    await call.answer(f"Заявка №{request_id} не найдена.", show_alert=True);
                    return

                request_status = req_data['status']
                target_user_id = req_data['user_id']
                amount = req_data['amount']

                if request_status != 'pending':
                    await call.answer(f"Заявка №{request_id} уже обработана ({request_status}).", show_alert=True)
                    return

                log.info(
                    f"Admin {admin_id} denies withdrawal request {request_id} for user {target_user_id}, amount {amount}")
                await conn.execute(
                    "UPDATE withdraw_requests SET status = 'denied', processed_time = CURRENT_TIMESTAMP WHERE id = $1",
                    request_id)

                if target_user_id and amount is not None and amount > 0:
                    await database.add_stars(target_user_id, amount)
                    log.info(f"Returned {amount} stars to user {target_user_id} denial req {request_id}.")
                else:
                    log.error(
                        f"Cannot return stars denied req {request_id}: missing user_id or invalid amount ({amount}).")

            if target_user_id and amount is not None and amount > 0:
                try:
                    await bot.send_message(target_user_id,
                                           f"🚫 Заявка №{request_id} ({amount}⭐️) отклонена.\nЗвезды возвращены.\n\nПоддержка: @{SUP_LOGIN}",
                                           parse_mode="HTML")
                except Exception as e:
                    log.warning(f"Failed send 'denied' notification user {target_user_id}: {e}")

            try:
                await call.message.edit_text(
                    call.message.html_text.replace("Ожидает обработки ⚙️", f"<b>Отказано 🚫</b>"), parse_mode="HTML",
                    reply_markup=None)
                await call.answer("🚫 Заявка отклонена, звезды возвращены.", show_alert=False)
            except Exception as e:
                log.warning(f"Failed edit message withdrawal channel denied req {request_id}: {e}")
                await call.answer("Статус в БД обновлен, сообщение не изменено.", show_alert=True)

        except asyncpg.PostgresError as db_err:
            log.exception(f"Database error processing 'denied' callback req {request_id}: {db_err}")
            await call.answer("Ошибка базы данных.", show_alert=True)
        except Exception as e:
            log.exception(f"Unexpected error processing 'denied' callback req {request_id}: {e}")
            await call.answer("Непредвиденная ошибка.", show_alert=True)


async def handle_paid_all(call: CallbackQuery, bot: Bot, app):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        try:
            await call.answer("⛔ Нет прав!", show_alert=True)
        except:
            pass
        return
    log.info(f"Admin {admin_id} initiated 'paid_all' action.")
    try:
        await call.answer("Начинаю обработку...")
    except:
        pass

    processed_count, failed_count, skipped_premium, skipped_other = 0, 0, 0, 0
    pending_requests = []
    pool = database.db_pool
    if not pool:
        log.error("DB pool not initialized!")
        await call.message.answer("Ошибка БД.")
        return

    try:
        async with pool.acquire() as conn_fetch:
            pending_requests = await conn_fetch.fetch(
                "SELECT id, user_id, amount, gift_id FROM withdraw_requests WHERE status = 'pending'")
        if not pending_requests:
            await call.answer("Нет ожидающих заявок.", show_alert=True);
            return

        progress_msg = await call.message.answer(f"Найдено {len(pending_requests)} заявок. Отправка Stars...")
        processed_total = 0

        for req in pending_requests:
            processed_total += 1
            req_id, user_id, amount, gift_id = req['id'], req['user_id'], req['amount'], req['gift_id']

            if not gift_id:
                if amount == 1700:
                    skipped_premium += 1; log.warning(f"Skipping premium req {req_id} user {user_id} (paid_all).")
                else:
                    skipped_other += 1; log.warning(f"Skipping req {req_id} user {user_id} missing gift_id (paid_all).")
                continue

            gift_sent_successfully = False
            try:
                await send_gift_with_retry(app, user_id, gift_id, bot_instance=bot)
                gift_sent_successfully = True
            except Exception as e:
                log.error(f"Failed process req {req_id} user {user_id} during 'paid_all': {e}")
                failed_count += 1
                async with pool.acquire() as conn_fail:
                    await conn_fail.execute(
                        "UPDATE withdraw_requests SET status = 'failed', processed_time = CURRENT_TIMESTAMP WHERE id = $1 AND status = 'pending'",
                        req_id)
                await asyncio.sleep(0.1)
                continue

            if gift_sent_successfully:
                async with pool.acquire() as conn_paid:
                    await conn_paid.execute(
                        "UPDATE withdraw_requests SET status = 'paid', processed_time = CURRENT_TIMESTAMP WHERE id = $1 AND status = 'pending'",
                        req_id)
                processed_count += 1
                log.info(f"Successfully processed req {req_id} user {user_id} (paid_all).")
                try:
                    await bot.send_message(user_id, f"✅ Заявка №{req_id} ({amount}⭐️) одобрена (массовая).")
                except Exception as notify_err:
                    log.warning(f"Failed send paid_all notification user {user_id}: {notify_err}")
                await asyncio.sleep(0.2)

            if processed_total % 10 == 0 or processed_total == len(pending_requests):
                try:
                    await progress_msg.edit_text(
                        f"Обработано: {processed_total}/{len(pending_requests)}\n✅ Успешно: {processed_count}\n❌ Ошибок: {failed_count}\n⏭ Пропущено(Prem): {skipped_premium}\n⏭ Пропущено(др): {skipped_other}")
                except Exception as edit_progress_err:
                    log.warning(f"Failed update paid_all progress msg: {edit_progress_err}")

        result_message = (
            f"✅ Массовое подтверждение завершено!\n\nВсего: {len(pending_requests)}\nУспешно: {processed_count}\nОшибок: {failed_count}\nПропущено(Prem): {skipped_premium}\nПропущено(др): {skipped_other}")
        await progress_msg.edit_text(result_message)
        log.info(
            f"Admin {admin_id} 'paid_all' finished. Total: {len(pending_requests)}, Success: {processed_count}, Failed: {failed_count}, Skipped P: {skipped_premium}, Skipped O: {skipped_other}")

    except asyncpg.PostgresError as db_err:
        log.exception(f"Database error during 'paid_all': {db_err}")
        await call.message.answer("Ошибка базы данных при 'paid_all'.")
    except Exception as e:
        log.exception(f"Unexpected error during 'paid_all': {e}")
        await call.message.answer("Непредвиденная ошибка при 'paid_all'.")


async def handle_denied_all(call: CallbackQuery, bot: Bot):
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        try:
            await call.answer("⛔ Нет прав!", show_alert=True)
        except:
            pass
        return
    log.info(f"Admin {admin_id} initiated 'denied_all' action.")
    try:
        await call.answer("Начинаю обработку...")
    except:
        pass

    denied_count = 0;
    returned_stars_total = 0.0;
    pending_requests = []
    pool = database.db_pool
    if not pool:
        log.error("DB pool not initialized!")
        await call.message.answer("Ошибка БД.")
        return

    try:
        async with pool.acquire() as conn:
            pending_requests = await conn.fetch(
                "SELECT id, user_id, amount FROM withdraw_requests WHERE status = 'pending' FOR UPDATE")
            if not pending_requests:
                await call.answer("Нет ожидающих заявок.", show_alert=True);
                return

            progress_msg = await call.message.answer(f"Найдено {len(pending_requests)} заявок. Отклонение и возврат...")
            processed_total = 0

            async with conn.transaction():
                result_update = await conn.execute(
                    "UPDATE withdraw_requests SET status = 'denied', processed_time = CURRENT_TIMESTAMP WHERE status = 'pending'")
                denied_count = int(result_update.split()[-1]) if result_update else 0
                log.info(f"Denied {denied_count} pending requests in DB.")

                for req in pending_requests:
                    processed_total += 1
                    req_id, user_id, amount = req['id'], req['user_id'], req['amount']
                    try:
                        if amount is not None and amount > 0:
                            await database.add_stars(user_id, amount)
                            returned_stars_total += amount
                            log.debug(f"Returned {amount} stars user {user_id} denied req {req_id} (denied_all)")
                        else:
                            log.warning(
                                f"Skipping star return denied req {req_id} user {user_id}: invalid amount {amount}")

                        asyncio.create_task(bot.send_message(user_id,
                                                             f"🚫 Заявка №{req_id} ({amount}⭐️) отклонена (массовая).\nЗвезды возвращены.\n\nПоддержка: @{SUP_LOGIN}",
                                                             parse_mode="HTML"))

                    except Exception as e:
                        log.error(f"Failed return stars or notify user {user_id} denied req {req_id} (denied_all): {e}")

                    if processed_total % 10 == 0 or processed_total == len(pending_requests):
                        try:
                            await progress_msg.edit_text(
                                f"Обработано: {processed_total}/{len(pending_requests)}\n🚫 Отклонено: {denied_count}\n💰 Возвращено: {returned_stars_total:.2f}⭐️")
                        except Exception as edit_progress_err:
                            log.warning(f"Failed update denied_all progress msg: {edit_progress_err}")

        result_message = (
            f"🚫 Массовый отказ завершен!\n\nВсего: {len(pending_requests)}\nОтклонено: {denied_count}\nВозвращено: {returned_stars_total:.2f}⭐️")
        await progress_msg.edit_text(result_message)
        log.info(
            f"Admin {admin_id} 'denied_all' finished. Denied: {denied_count}, Returned: {returned_stars_total:.2f} stars.")

    except asyncpg.PostgresError as db_err:
        log.exception(f"Database error during 'denied_all': {db_err}")
        await call.message.answer("Ошибка базы данных при 'denied_all'.")
    except Exception as e:
        log.exception(f"Unexpected error during 'denied_all': {e}")
        await call.message.answer("Непредвиденная ошибка при 'denied_all'.")


def register_admin_withdrawal_handlers(dp: Dispatcher, bot: Bot, app):
    dp.register_callback_query_handler(lambda call: handle_paid_status(call, bot, app),
                                       lambda c: c.data.startswith("paid:"), state="*")
    dp.register_callback_query_handler(lambda call: handle_denied_status(call, bot),
                                       lambda c: c.data.startswith("denied_req:"), state="*")
    dp.register_callback_query_handler(lambda call: handle_denied_status(call, bot),
                                       lambda c: c.data.startswith("denied:"), state="*")
    dp.register_callback_query_handler(lambda call: handle_paid_all(call, bot, app), lambda c: c.data == "paid_all",
                                       state="*")
    dp.register_callback_query_handler(lambda call: handle_denied_all(call, bot), lambda c: c.data == "denied_all",
                                       state="*")
    log.info("Admin withdrawal handlers registered.")
