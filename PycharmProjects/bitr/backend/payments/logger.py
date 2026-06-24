from models.payment_log import PaymentLog, SessionLocal
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def log_payment(deal_id: str, payment_id: str, amount: int, status: str, source: str = "yookassa"):
    """
    Логирование платежа в БД
    
    Args:
        deal_id: ID сделки из Bitrix
        payment_id: ID платежа из ЮKassa
        amount: Сумма платежа в копейках
        status: Статус ("pending", "paid", "failed")
        source: Источник ("yookassa", "admin")
    """
    db = SessionLocal()
    try:
        # Проверяем, не существует ли уже такой платеж
        existing = db.query(PaymentLog).filter(PaymentLog.payment_id == payment_id).first()
        if existing:
            return existing
        
        log_entry = PaymentLog(
            deal_id=deal_id,
            payment_id=payment_id,
            amount=amount,
            status=status,
            source=source,
            created_at=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as e:
        db.rollback()
        logger.error(f"Error logging payment: {e}", exc_info=True)
        raise
    finally:
        db.close()

def get_payment_logs(deal_id: str = None):
    """
    Получить логи платежей
    
    Args:
        deal_id: Опционально - фильтр по ID сделки
    
    Returns:
        List[PaymentLog]
    """
    db = SessionLocal()
    try:
        query = db.query(PaymentLog)
        if deal_id:
            query = query.filter(PaymentLog.deal_id == str(deal_id))
        return query.order_by(PaymentLog.created_at.desc()).all()
    except Exception as e:
        logger.error(f"Error getting payment logs: {e}", exc_info=True)
        return []
    finally:
        db.close()

def update_payment_status(payment_id: str, status: str):
    """
    Обновить статус платежа
    
    Args:
        payment_id: ID платежа
        status: Новый статус
    """
    db = SessionLocal()
    try:
        log_entry = db.query(PaymentLog).filter(PaymentLog.payment_id == payment_id).first()
        if log_entry:
            log_entry.status = status
            db.commit()
            return log_entry
        return None
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating payment status: {e}", exc_info=True)
        raise
    finally:
        db.close()

