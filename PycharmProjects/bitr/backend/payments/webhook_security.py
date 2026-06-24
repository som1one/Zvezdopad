"""
Модуль для проверки безопасности webhook от YooKassa.

ВАЖНО: В продакшене обязательно использовать проверку подписи!
"""

import hmac
import hashlib
import logging
from core.config import settings

logger = logging.getLogger(__name__)

def verify_webhook_signature(payload: str, signature: str) -> bool:
    """
    Проверяет подпись webhook от YooKassa.
    
    Args:
        payload: Тело запроса (JSON строка)
        signature: Подпись из заголовка X-YooMoney-Signature
    
    Returns:
        True если подпись валидна, False иначе
    """
    if not signature:
        logger.warning("Webhook signature missing")
        return False
    
    try:
        # YooKassa использует HMAC-SHA256
        # Секретный ключ берется из настроек
        secret = settings.YOOKASSA_SECRET.encode('utf-8')
        expected_signature = hmac.new(
            secret,
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Сравниваем подписи безопасным способом
        return hmac.compare_digest(expected_signature, signature)
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False

def verify_webhook_payload(payload: dict) -> bool:
    """
    Базовая валидация структуры webhook payload.
    
    Args:
        payload: Словарь с данными webhook
    
    Returns:
        True если структура валидна
    """
    required_fields = ["event", "object"]
    
    for field in required_fields:
        if field not in payload:
            logger.error(f"Missing required field in webhook: {field}")
            return False
    
    if payload.get("event") != "payment.succeeded":
        logger.info(f"Webhook event is not 'payment.succeeded': {payload.get('event')}")
        return False
    
    obj = payload.get("object", {})
    required_obj_fields = ["id", "amount", "status"]
    
    for field in required_obj_fields:
        if field not in obj:
            logger.error(f"Missing required field in webhook object: {field}")
            return False
    
    # Проверяем статус платежа
    if obj.get("status") != "succeeded":
        logger.warning(f"Payment status is not 'succeeded': {obj.get('status')}")
        return False
    
    return True

