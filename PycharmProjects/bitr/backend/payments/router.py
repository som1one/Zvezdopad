from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from payments.yookassa import create_payment, process_webhook
from payments.logger import get_payment_logs
from core.config import settings
from core.security import get_current_user, require_admin
from bitrix.client import get_installment_deal
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

class PaymentRequest(BaseModel):
    amount: int

class PaymentLogResponse(BaseModel):
    id: int
    deal_id: str
    payment_id: str
    amount: int
    status: str
    source: str
    comment: Optional[str] = None
    created_at: str

@router.post("/create")
def create_payment_endpoint(
    body: PaymentRequest,
    user = Depends(get_current_user)
):
    """
    Создание платежа через YooKassa.
    
    Валидация:
    - Сумма должна быть больше 0
    - Сумма не должна превышать остаток по рассрочке
    """
    user_identifier = user.email or user.phone or user.identifier
    logger.info(f"Запрос на создание платежа от пользователя {user_identifier}, сумма: {body.amount} ₽")
    
    # Валидация суммы на бэке
    if body.amount <= 0:
        logger.warning(f"Попытка создать платеж с некорректной суммой: {body.amount}")
        raise HTTPException(status_code=400, detail="Сумма должна быть больше 0")
    
    # Получаем данные о рассрочке
    user_identifier = user.email or user.phone or user.identifier
    logger.info(f"Получение данных рассрочки для пользователя {user_identifier}")
    
    from bitrix.client import get_installment_deal_by_phone
    if user.identifier_type == "phone":
        deal = get_installment_deal_by_phone(user.identifier)
    else:
        deal = get_installment_deal(user.identifier)
    
    if not deal:
        logger.warning(f"Рассрочка не найдена для пользователя {user_identifier}")
        raise HTTPException(
            status_code=404, 
            detail=f"Рассрочка не найдена для пользователя {user_identifier}"
        )
    
    logger.info(f"Рассрочка найдена: deal_id={deal.get('ID')}")
    
    # Получаем текущую оплаченную сумму из БД для проверки остатка
    # ВАЖНО: Используем SELECT FOR UPDATE для блокировки строки и предотвращения race condition
    # Это гарантирует, что два одновременных платежа не смогут превысить остаток
    from models.deal import Deal
    from models.payment_log import SessionLocal
    db = SessionLocal()
    try:
        # Блокируем строку для чтения/обновления до конца транзакции
        # Это предотвращает одновременные платежи, которые могут превысить остаток
        db_deal = db.query(Deal).filter(Deal.deal_id == deal["ID"]).with_for_update().first()
        
        if not db_deal:
            # Если сделки нет в БД, создаем её
            logger.info(f"Сделка {deal['ID']} не найдена в локальной БД, создаем запись")
            
            # Получаем email из контакта Bitrix24, если пользователь вошел по телефону
            user_email = user.email
            if not user_email and user.identifier_type == "phone":
                try:
                    contact_id = deal.get("CONTACT_ID")
                    if contact_id:
                        import requests
                        contact_res = requests.get(
                            f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.get",
                            params={"ID": contact_id},
                            timeout=10
                        )
                        if contact_res.status_code == 200:
                            contact = contact_res.json().get('result', {})
                            contact_email = contact.get('EMAIL')
                            if contact_email:
                                if isinstance(contact_email, list) and len(contact_email) > 0:
                                    if isinstance(contact_email[0], dict):
                                        user_email = contact_email[0].get('VALUE', '')
                                    else:
                                        user_email = str(contact_email[0])
                                elif isinstance(contact_email, str):
                                    user_email = contact_email
                except Exception as e:
                    logger.warning(f"Не удалось получить email из контакта: {e}")
            
            # Получаем сумму из Bitrix24 (НЕ подставляем дефолт)
            opportunity = deal.get("OPPORTUNITY", "0")
            if isinstance(opportunity, str):
                opportunity = opportunity.replace(" ", "").replace(",", "")
            total_amount = int(float(opportunity)) if opportunity and float(opportunity) > 0 else 0
            
            # Получаем срок из Bitrix24 (если есть; иначе 0)
            term_val = deal.get("UF_TERM_MONTHS")
            try:
                term_months = int(term_val) if term_val else 0
            except (ValueError, TypeError):
                term_months = 0
            
            db_deal = Deal(
                deal_id=deal["ID"],
                title=deal.get("TITLE", ""),
                email=user_email or user.identifier,
                total_amount=total_amount,
                paid_amount=0,
                term_months=term_months
            )
            db.add(db_deal)
            db.commit()
            db.refresh(db_deal)
            logger.info(f"Создана запись в БД для сделки {deal['ID']}: total_amount={total_amount}, term_months={term_months}")
        
        logger.info(f"Данные из БД: total_amount={db_deal.total_amount}, paid_amount={db_deal.paid_amount}")

        # Если сумма рассрочки неизвестна — не можем корректно валидировать остаток
        if db_deal.total_amount <= 0:
            logger.warning(f"Cannot create payment: total_amount is not set for deal {deal['ID']} (OPPORTUNITY=0)")
            raise HTTPException(
                status_code=400,
                detail="Сумма рассрочки не задана в Bitrix24 (OPPORTUNITY=0). Заполните сумму сделки, чтобы принимать платежи."
            )

        remaining = db_deal.total_amount - db_deal.paid_amount
        
        if body.amount > remaining:
            logger.warning(
                f"Попытка оплаты суммы {body.amount} ₽ превышает остаток {remaining} ₽ "
                f"для сделки {deal['ID']}"
            )
            raise HTTPException(
                status_code=400, 
                detail=f"Сумма платежа ({body.amount} ₽) превышает остаток по рассрочке ({remaining} ₽)"
            )
        
        if remaining <= 0:
            logger.warning(f"Попытка оплаты полностью оплаченной рассрочки {deal['ID']}")
            raise HTTPException(
                status_code=400, 
                detail="Рассрочка уже полностью оплачена"
            )
        
        logger.info(
            f"Валидация пройдена. Создание платежа на сумму {body.amount} ₽ для сделки {deal['ID']}. "
            f"Остаток: {remaining} ₽"
        )
    finally:
        db.close()
    
    try:
        url = create_payment(
            amount=body.amount,
            deal_id=deal["ID"],
            return_url=settings.FRONTEND_URL,
            identifier=user.identifier,
            identifier_type=user.identifier_type,
            email=user.email
        )
        logger.info(f"Платеж успешно создан, URL: {url}")
        return {"url": url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при создании платежа в YooKassa: {e}", exc_info=True)
        msg = str(e)
        # Ошибки внешнего провайдера отдаём как 502 (чтобы не маскировать как «ошибка сервера»)
        if "ЮKassa:" in msg or "yookassa" in msg.lower() or "api.yookassa.ru" in msg:
            raise HTTPException(status_code=502, detail=f"Ошибка при создании платежа: {msg}")
        raise HTTPException(status_code=500, detail=f"Ошибка при создании платежа: {msg}")

@router.post("/webhook")
async def yookassa_webhook(request: Request):
    """
    Webhook endpoint для получения уведомлений от YooKassa.
    
    ВАЖНО: В продакшене нужно добавить проверку подписи webhook!
    YooKassa отправляет заголовок X-YooMoney-Signature для проверки.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Логируем входящий запрос
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Webhook endpoint called from IP: {client_ip}, headers: {dict(request.headers)}")
    
    try:
        # Получаем тело запроса как строку для проверки подписи
        body_bytes = await request.body()
        body_str = body_bytes.decode('utf-8')
        
        # Парсим JSON
        import json
        payload = json.loads(body_str)
        
        # Валидация базовой структуры payload
        from payments.webhook_security import verify_webhook_payload
        if not verify_webhook_payload(payload):
            raise HTTPException(status_code=400, detail="Invalid webhook payload structure")
        
        # Проверка подписи (в продакшене обязательно)
        if settings.VERIFY_WEBHOOK_SIGNATURE or settings.ENVIRONMENT == "production":
            from payments.webhook_security import verify_webhook_signature
            signature = request.headers.get("X-YooMoney-Signature")
            if not signature:
                logger.warning("Webhook signature header missing")
                if settings.ENVIRONMENT == "production":
                    raise HTTPException(status_code=401, detail="Webhook signature required")
            elif not verify_webhook_signature(body_str, signature):
                logger.error(f"Invalid webhook signature for payment {payload.get('object', {}).get('id')}")
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
            else:
                logger.debug("Webhook signature verified successfully")
        else:
            logger.info("Webhook signature verification skipped (development mode)")
        
        payment_id = payload.get('object', {}).get('id')
        logger.info(f"Received webhook: event={payload.get('event')}, payment_id={payment_id}")
        
        process_webhook(payload)
        
        logger.info(f"Webhook processed successfully for payment {payment_id}")
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON in webhook payload")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@router.post("/webhook/test")
async def test_webhook_endpoint(user = Depends(require_admin)):
    """
    Тестовый endpoint для проверки работы webhook endpoint.
    Проверяет доступность endpoint'а без реальной обработки платежа.
    """
    logger.info("Test webhook endpoint called by admin")
    
    return {
        "status": "ok",
        "message": "Webhook endpoint доступен. URL: https://pay.mari-karkas.ru/api/payments/webhook",
        "note": "Проверьте, что этот URL указан в настройках YooKassa (Настройки → HTTP уведомления)"
    }

@router.get("/logs", response_model=List[PaymentLogResponse])
def get_payment_logs_endpoint(
    deal_id: Optional[str] = None
    , user = Depends(require_admin)
):
    """
    Получить логи платежей (для админа)
    """
    logs = get_payment_logs(deal_id=deal_id)
    return [
        PaymentLogResponse(
            id=log.id,
            deal_id=log.deal_id,
            payment_id=log.payment_id,
            amount=log.amount,
            status=log.status,
            source=log.source,
            comment=getattr(log, "comment", None),
            created_at=log.created_at.isoformat()
        )
        for log in logs
    ]
