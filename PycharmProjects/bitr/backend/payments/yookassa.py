import uuid
import logging
from yookassa import Payment, Configuration
import requests
from core.config import settings
from bitrix.client import update_paid_amount, _get_full_deal
from payments.logger import log_payment, update_payment_status, get_payment_logs

logger = logging.getLogger(__name__)

Configuration.account_id = settings.YOOKASSA_SHOP_ID
Configuration.secret_key = settings.YOOKASSA_SECRET

def create_payment(amount, deal_id, return_url, identifier=None, identifier_type=None, email=None):
    """
    Создание платежа в ЮKassa и логирование
    
    Args:
        amount: Сумма платежа
        deal_id: ID сделки
        return_url: URL для возврата после оплаты
        email: Email пользователя (для сохранения в metadata)
    """
    # email в metadata — опционально (у пользователей с входом по телефону его может не быть)
    email_to_save = email if email else None
    
    idempotence_key = str(uuid.uuid4())
    
    try:
        payment = Payment.create({
            "amount": {
                "value": f"{amount}.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url
            },
            "capture": True,
            "description": "Платеж по рассрочке",
            "metadata": {
                # ВАЖНО: в БД deal_id хранится строкой; в metadata держим строку,
                # иначе на Postgres сравнение VARCHAR = INTEGER может ломать webhook-обработку.
                "deal_id": str(deal_id),
                "email": email_to_save,
                "identifier": identifier,
                "identifier_type": identifier_type
            }
        }, idempotence_key)
    except requests.exceptions.HTTPError as e:
        status_code = getattr(getattr(e, "response", None), "status_code", None)
        if status_code == 401:
            # Самая частая причина: неверные ключи магазина (shop_id/secret)
            raise Exception(
                "ЮKassa: 401 Unauthorized. Проверьте YOOKASSA_SHOP_ID и YOOKASSA_SECRET "
                "(должны соответствовать вашему магазину; тестовые ключи работают только в тестовом режиме)."
            )
        raise

    payment_id = payment.id
    
    # Логируем создание платежа
    try:
        log_payment(
            deal_id=str(deal_id),
            payment_id=payment_id,
            amount=amount,
            status="pending",
            source="yookassa"
        )
    except Exception as e:
        logger.error(f"Error logging payment creation: {e}")
        # Не падаем, если логирование не работает
    
    return payment.confirmation.confirmation_url

def process_webhook(payload: dict):
    """Обработка webhook от ЮKassa с логированием"""
    logger.info(f"=== WEBHOOK RECEIVED === Payload keys: {list(payload.keys())}")
    
    event = payload.get("event")
    obj = payload.get("object")

    if event != "payment.succeeded":
        logger.info(f"Webhook event '{event}' ignored (only processing 'payment.succeeded')")
        return

    payment_id = obj.get("id")
    if not payment_id:
        logger.error("payment_id not found in webhook payload")
        raise Exception("payment_id not found in webhook payload")
    
    logger.info(f"=== Processing webhook for payment {payment_id}, event: {event} ===")
    
    # Валидация данных из webhook
    if "amount" not in obj or "value" not in obj["amount"]:
        raise Exception("Invalid webhook payload: amount.value not found")
    
    try:
        amount = int(float(obj["amount"]["value"]))
        if amount <= 0:
            raise Exception(f"Invalid payment amount: {amount}")
    except (ValueError, TypeError) as e:
        raise Exception(f"Invalid amount format in webhook: {e}")
    
    metadata = obj.get("metadata", {})
    deal_id_raw = metadata.get("deal_id")
    if deal_id_raw in (None, "", False):
        raise Exception("deal_id not found in metadata")
    deal_id = str(deal_id_raw).strip()
    if not deal_id:
        raise Exception("deal_id not found in metadata")
    identifier = metadata.get("identifier")
    identifier_type = metadata.get("identifier_type")
    
    logger.info(f"Webhook payment {payment_id}: deal_id={deal_id}, amount={amount}")

    # ВАЖНО: Используем ОДНУ сессию БД для всех операций
    # Это предотвращает утечку соединений и проблемы с транзакциями
    logger.info(f"Creating DB session for payment {payment_id}, deal_id={deal_id}")
    from models.deal import Deal
    from models.payment_log import PaymentLog, SessionLocal
    from models.cash_allocation import CashAllocation
    db = SessionLocal()
    try:
        # Быстрая проверка на уже обработанный платеж (до блокировки, для оптимизации)
        # Но затем перепроверим в транзакции с блокировкой
        quick_check_log = db.query(PaymentLog).filter(
            PaymentLog.payment_id == payment_id
        ).first()
        
        quick_check_alloc = db.query(CashAllocation).filter(
            CashAllocation.payment_id == payment_id
        ).first() is not None
        
        if quick_check_log and quick_check_log.status == "paid" and quick_check_alloc:
            logger.info(f"Payment {payment_id} already processed (paid + allocations exist), skipping")
            db.close()
            return
        
        # Блокируем строку сделки, чтобы избежать гонок при параллельных вебхуках/платежах
        db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).with_for_update().first()
        logger.info(f"Deal {deal_id} lookup result: {'found' if db_deal else 'NOT FOUND'}")
        
        if db_deal:
            # ВАЖНО: Перепроверяем log_entry и allocations в той же транзакции после блокировки сделки
            # Это предотвращает race condition между проверкой и обновлением
            log_entry = db.query(PaymentLog).filter(PaymentLog.payment_id == payment_id).with_for_update().first()
            alloc_already_exists = db.query(CashAllocation).filter(
                CashAllocation.payment_id == payment_id
            ).first() is not None
            
            # Финальная проверка: если уже ПОЛНОСТЬЮ обработан (статус paid И аллокации созданы), выходим
            if log_entry and log_entry.status == "paid" and alloc_already_exists:
                logger.info(f"Payment {payment_id} already fully processed (paid + allocations exist), skipping")
                db.commit()  # Commit чтобы освободить блокировку
                db.close()
                return
            
            # Определяем, нужно ли добавлять сумму к paid_amount
            # Если лог уже "paid", то сумму повторно НЕ прибавляем (но аллокации можем создать, если их нет)
            should_add_to_paid_amount = not (log_entry and log_entry.status == "paid")
            logger.info(
                f"Payment {payment_id} processing: log_entry exists={log_entry is not None}, "
                f"log_status={log_entry.status if log_entry else 'N/A'}, "
                f"alloc_exists={alloc_already_exists}, "
                f"should_add_to_paid={should_add_to_paid_amount}, deal_id={deal_id}"
            )
            current_paid = db_deal.paid_amount or 0
            new_paid_amount = current_paid + amount if should_add_to_paid_amount else current_paid

            # Если total_amount задан — ограничиваем переплату
            if db_deal.total_amount and db_deal.total_amount > 0:
                if new_paid_amount > db_deal.total_amount:
                    logger.warning(
                        f"Payment amount {amount} would exceed total amount. "
                        f"Current: {current_paid}, Total: {db_deal.total_amount}. "
                        f"Setting to total amount."
                    )
                    new_paid_amount = db_deal.total_amount

            db_deal.paid_amount = new_paid_amount
            logger.info(
                f"Updated paid_amount in DB: {current_paid} {'+' + str(amount) if should_add_to_paid_amount else '(already paid)'} = {new_paid_amount} "
                f"for deal {deal_id} (total={db_deal.total_amount})"
            )
            
            # Обновляем или создаем лог платежа
            if log_entry:
                if log_entry.status != "paid":
                    log_entry.status = "paid"
                    # Обновляем сумму из webhook (авторитетный источник)
                    if log_entry.amount != amount:
                        logger.info(f"Updating payment log amount from {log_entry.amount} to {amount} (webhook is authoritative)")
                        log_entry.amount = amount
                    logger.info(f"Updated payment log status to 'paid' for {payment_id}")
                else:
                    logger.warning(f"Payment {payment_id} log already has status 'paid'")
            else:
                # Создаем новый лог если не было
                new_log = PaymentLog(
                    deal_id=str(deal_id),
                    payment_id=payment_id,
                    amount=amount,
                    status="paid",
                    source="yookassa"
                )
                db.add(new_log)
                log_entry = new_log
                logger.info(f"Created payment log for {payment_id}")

            # Месячный зачёт (учёт в БД): распределяем сумму платежа по месяцам графика
            # Пишем в cash_allocations (используется для paid/partial статусов в графике).
            if not alloc_already_exists:
                try:
                    term = int(db_deal.term_months or 0)
                    total_sum = int(db_deal.total_amount or 0)
                    initial_payment = int(db_deal.initial_payment or 0)
                    installment_amount = max(0, total_sum - initial_payment)  # Сумма рассрочки (без первоначального взноса)
                    logger.info(
                        f"Allocating payment {payment_id} for deal {deal_id}: "
                        f"term={term}, total={total_sum}, initial={initial_payment}, "
                        f"installment_amount={installment_amount}, payment_amount={amount}"
                    )
                    if term > 0 and installment_amount > 0:
                        monthly = installment_amount // term
                        remainder = installment_amount % term
                        logger.info(f"Monthly payment: {monthly}, remainder: {remainder}")

                        # Сколько уже зачтено по месяцам (включая наличные и прошлые ЮKassa)
                        sums = {}
                        rows = db.query(CashAllocation).filter(CashAllocation.deal_id == str(deal_id)).all()
                        for r in rows:
                            try:
                                idx = int(r.month_index)
                                amt = int(r.amount or 0)
                                if idx >= 0 and amt > 0:
                                    sums[idx] = sums.get(idx, 0) + amt
                            except Exception:
                                continue
                        
                        logger.info(f"Existing allocations per month: {sums}")

                        left = int(amount)
                        allocations_created = 0
                        for i in range(term):
                            due = monthly + (remainder if i == term - 1 else 0)
                            already = sums.get(i, 0)
                            remaining = max(0, due - already)
                            if remaining <= 0:
                                logger.debug(f"Month {i} already fully paid (due={due}, already={already}), skipping")
                                continue
                            part = min(remaining, left)
                            if part <= 0:
                                break
                            db.add(CashAllocation(
                                deal_id=str(deal_id),
                                payment_id=payment_id,
                                month_index=i,
                                amount=part
                            ))
                            allocations_created += 1
                            sums[i] = already + part
                            left -= part
                            logger.info(f"Allocated {part} to month {i} (due={due}, already={already}, remaining={remaining})")
                            if left <= 0:
                                break

                        # Если переплата — добавляем в последний месяц, чтобы сумма сохранилась в учёте
                        if left > 0 and term > 0:
                            db.add(CashAllocation(
                                deal_id=str(deal_id),
                                payment_id=payment_id,
                                month_index=term - 1,
                                amount=left
                            ))
                            allocations_created += 1
                            logger.info(f"Allocated remaining {left} to last month {term - 1} (overpayment)")
                        
                        logger.info(f"Created {allocations_created} allocations for payment {payment_id}")
                    else:
                        logger.warning(
                            f"Skip month allocation for payment {payment_id}: "
                            f"term_months={db_deal.term_months}, installment_amount={installment_amount} "
                            f"(total={total_sum}, initial={initial_payment})"
                        )
                except Exception as e:
                    logger.error(f"Failed to allocate yookassa payment by months for {payment_id}: {e}", exc_info=True)
            
            try:
                db.commit()
                # Проверяем, что данные действительно сохранились
                db.refresh(db_deal)
                logger.info(
                    f"Successfully committed payment {payment_id} processing for deal {deal_id}. "
                    f"Final paid_amount in DB: {db_deal.paid_amount}"
                )
            except Exception as commit_error:
                logger.error(f"Failed to commit payment {payment_id} processing: {commit_error}", exc_info=True)
                db.rollback()
                raise
        else:
            logger.warning(f"Deal {deal_id} not found in local DB, creating new record")
            # Создаем запись в БД если её нет
            try:
                # Идентификатор пользователя (email/phone) — сохраняем как строку в Deal.email (исторически поле так называется)
                email = metadata.get("email") or identifier or "unknown"
                
                # Получаем данные из Bitrix24
                # ВАЖНО: Используем get_installment_deal для поиска, но затем получаем полные данные
                # через _get_full_deal, чтобы получить пользовательские поля (UF_TERM_MONTHS, UF_PAID_AMOUNT)
                # Здесь достаточно получить по ID
                bitrix_deal = _get_full_deal(deal_id) or {}
                
                # Создаем запись Deal с валидацией данных
                try:
                    # Получаем OPPORTUNITY (может быть строкой "0.00" или числом)
                    opportunity = bitrix_deal.get("OPPORTUNITY", "0")
                    if isinstance(opportunity, str):
                        opportunity = opportunity.replace(" ", "").replace(",", "")
                    total_amount = int(float(opportunity)) if opportunity and float(opportunity) > 0 else 0
                    
                    # Срок (если есть), иначе 0
                    term_months_str = bitrix_deal.get("UF_TERM_MONTHS")
                    try:
                        term_months = int(term_months_str) if term_months_str else 0
                    except (ValueError, TypeError):
                        term_months = 0
                    
                    title = bitrix_deal.get("TITLE", f"Deal {deal_id}")
                    
                    if total_amount <= 0:
                        logger.warning(
                            f"Deal {deal_id} has no total_amount in Bitrix24 (OPPORTUNITY=0). "
                            f"Saving as unknown total (0)."
                        )
                    
                    new_deal = Deal(
                        deal_id=deal_id,
                        title=title,
                        email=email,
                        total_amount=total_amount,
                        paid_amount=amount,
                        term_months=term_months
                    )
                    db.add(new_deal)
                    
                    # Создаем лог платежа
                    new_log = PaymentLog(
                        deal_id=str(deal_id),
                        payment_id=payment_id,
                        amount=amount,
                        status="paid",
                        source="yookassa"
                    )
                    db.add(new_log)

                    # Месячный зачёт для нового deal (если есть срок/сумма)
                    try:
                        term = int(term_months or 0)
                        total_sum = int(total_amount or 0)
                        initial_payment = 0  # Для нового deal initial_payment ещё не установлен, будет 0
                        installment_amount = max(0, total_sum - initial_payment)  # Сумма рассрочки
                        if term > 0 and installment_amount > 0:
                            monthly = installment_amount // term
                            remainder = installment_amount % term
                            left = int(amount)
                            for i in range(term):
                                due = monthly + (remainder if i == term - 1 else 0)
                                part = min(due, left)
                                if part <= 0:
                                    break
                                db.add(CashAllocation(
                                    deal_id=str(deal_id),
                                    payment_id=payment_id,
                                    month_index=i,
                                    amount=part
                                ))
                                left -= part
                                if left <= 0:
                                    break
                            if left > 0 and term > 0:
                                db.add(CashAllocation(
                                    deal_id=str(deal_id),
                                    payment_id=payment_id,
                                    month_index=term - 1,
                                    amount=left
                                ))
                    except Exception as e:
                        logger.warning(f"Failed to allocate yookassa payment by months for new deal {deal_id}: {e}")
                    
                    try:
                        db.commit()
                        logger.info(
                            f"Successfully created new deal record and payment log for {deal_id} "
                            f"(email: {email}, paid_amount: {amount}, total: {total_amount})"
                        )
                    except Exception as commit_error:
                        logger.error(f"Failed to commit new deal creation for {deal_id}: {commit_error}", exc_info=True)
                        db.rollback()
                        raise
                except (ValueError, TypeError) as validation_error:
                    logger.error(
                        f"Data validation error when creating deal {deal_id}: {validation_error}. "
                        f"Payment {payment_id} processed but deal not saved.",
                        exc_info=True
                    )
                    # Создаем хотя бы лог платежа
                    try:
                        new_log = PaymentLog(
                            deal_id=str(deal_id),
                            payment_id=payment_id,
                            amount=amount,
                            status="paid",
                            source="yookassa"
                        )
                        db.add(new_log)
                        db.commit()
                        logger.warning(
                            f"Created payment log only (no deal record) for payment {payment_id}, "
                            f"deal {deal_id} - validation error"
                        )
                    except Exception as log_error:
                        logger.error(f"Failed to create payment log: {log_error}", exc_info=True)
                        db.rollback()
            except Exception as create_error:
                logger.error(
                    f"Unexpected error creating deal record for {deal_id}, payment {payment_id}: {create_error}",
                    exc_info=True
                )
                # Пытаемся сохранить хотя бы лог платежа
                try:
                    db.rollback()  # Откатываем неудачную транзакцию
                    new_log = PaymentLog(
                        deal_id=str(deal_id),
                        payment_id=payment_id,
                        amount=amount,
                        status="paid",
                        source="yookassa"
                    )
                    db.add(new_log)
                    db.commit()
                    logger.warning(
                        f"Created payment log only (no deal record) for payment {payment_id}, "
                        f"deal {deal_id} - unexpected error during deal creation"
                    )
                except Exception as log_error:
                    logger.error(
                        f"Failed to create payment log after deal creation error: {log_error}",
                        exc_info=True
                    )
                    db.rollback()
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating paid_amount in DB: {e}", exc_info=True)
        # Проверяем, не был ли платеж уже обработан (используем ту же сессию)
        try:
            check_log = db.query(PaymentLog).filter(
                PaymentLog.payment_id == payment_id,
                PaymentLog.status == "paid"
            ).first()
            if check_log:
                logger.warning(f"Payment {payment_id} already processed, but error occurred. Skipping.")
                # Сессия закроется в finally
                return  # Платеж уже обработан, не поднимаем исключение
        except Exception as check_error:
            logger.warning(f"Error checking payment status: {check_error}")
        # Если платеж не был обработан, поднимаем исключение (сессия закроется в finally)
        raise
    finally:
        # Получаем финальную оплаченную сумму ДО закрытия сессии для обновления Bitrix24
        final_paid_amount = None
        try:
            final_deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
            if final_deal:
                final_paid_amount = final_deal.paid_amount
                logger.info(f"Final paid_amount from DB: {final_paid_amount} for deal {deal_id}")
        except Exception as e:
            logger.warning(f"Error getting final paid_amount: {e}")
        db.close()
        logger.info(f"DB session closed for payment {payment_id}")

    # Обновляем сделку в Bitrix (обновляем полную сумму из БД)
    # Выполняем после закрытия основной транзакции, чтобы не блокировать БД
    deal_title = None
    deal_email = None
    
    # Получаем информацию о сделке для уведомления ДО обновления Bitrix
    try:
        from models.deal import Deal
        from models.payment_log import SessionLocal
        db_notif = SessionLocal()
        try:
            deal_info = db_notif.query(Deal).filter(Deal.deal_id == deal_id).first()
            if deal_info:
                deal_title = deal_info.title
                deal_email = deal_info.email
        finally:
            db_notif.close()
    except Exception as e:
        logger.debug(f"Could not get deal info for notification: {e}")
    
    if final_paid_amount is not None:
        try:
            update_paid_amount(deal_id, final_paid_amount)  # Обновляем полную сумму
            logger.info(f"Updated Bitrix24 paid_amount: {final_paid_amount} for deal {deal_id}")
        except Exception as e:
            logger.warning(f"Error updating Bitrix24: {e}")
            # Продолжаем обработку даже если Bitrix недоступен
    else:
        # Если не удалось получить из БД, обновляем на сумму платежа (может быть неточно)
        logger.warning(f"Deal {deal_id} not in DB, updating Bitrix24 with payment amount only")
        try:
            update_paid_amount(deal_id, amount)
        except Exception as e:
            logger.warning(f"Error updating Bitrix24 with payment amount: {e}")
    
    # Отправляем уведомление в Telegram (не критично, если не получится)
    try:
        from notifications.telegram import send_telegram_notification, format_payment_notification
        try:
            # Безопасное получение email
            notification_email = None
            if deal_email:
                notification_email = deal_email
            elif metadata:
                notification_email = metadata.get("email") or metadata.get("identifier")
            if not notification_email:
                notification_email = identifier
            
            # Формируем и отправляем уведомление
            notification_message = format_payment_notification(
                deal_id=str(deal_id) if deal_id else "неизвестно",
                amount=int(amount) if amount else 0,
                payment_id=str(payment_id) if payment_id else "неизвестно",
                source="yookassa",
                title=str(deal_title) if deal_title else None,
                email=str(notification_email) if notification_email else None
            )
            send_telegram_notification(notification_message)
        except Exception as format_error:
            logger.warning(f"Failed to format Telegram notification: {format_error}", exc_info=True)
    except ImportError as import_error:
        logger.debug(f"Telegram notifications module not available: {import_error}")
    except Exception as e:
        logger.warning(f"Failed to send Telegram notification: {e}", exc_info=True)
        # Не прерываем обработку платежа из-за ошибки уведомления
    
    logger.info(f"Payment {payment_id} processed successfully for deal {deal_id}, amount: {amount}")
