#!/usr/bin/env python3
"""
Скрипт для синхронизации данных из Bitrix24 в локальную БД.

Использование:
    python sync_bitrix_to_db.py
    или
    python -m scripts.sync_bitrix_to_db
"""

import sys
import os
import logging
from datetime import datetime
from typing import Tuple

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.payment_log import init_db, get_db
from models.deal import Deal
from bitrix.client import get_all_installment_deals
from bitrix.client import _get_full_deal
from bitrix.parsing import parse_money_to_int, parse_int
from core.config import settings
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_contact_email(contact_id: str) -> str:
    """Получает email контакта из Bitrix24"""
    try:
        url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.get"
        params = {"ID": contact_id}
        
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        contact = res.json().get("result", {})
        
        # Email может быть списком словарей или строкой
        email_val = contact.get("EMAIL")
        if isinstance(email_val, list) and email_val:
            first = email_val[0]
            if isinstance(first, dict):
                return first.get("VALUE") or ""
            return str(first)
        elif isinstance(email_val, str):
            return email_val
        
        return ""
    except Exception as e:
        logger.warning(f"Не удалось получить email для контакта {contact_id}: {e}")
        return ""


def sync_deal_to_db(db, bitrix_deal: dict) -> Tuple[bool, str]:
    """
    Синхронизирует одну сделку из Bitrix24 в БД.
    Возвращает (успех, сообщение)
    """
    deal_id = bitrix_deal.get("ID")
    if not deal_id:
        return False, "Нет ID сделки"
    
    try:
        # Получаем полные данные сделки (включая UF_* поля)
        full_deal = _get_full_deal(deal_id)
        if not full_deal:
            return False, f"Не удалось получить полные данные для сделки {deal_id}"
        
        # Получаем email контакта
        contact_id = bitrix_deal.get("CONTACT_ID") or full_deal.get("CONTACT_ID")
        email = ""
        if contact_id:
            email = get_contact_email(contact_id)
        
        # Парсим данные
        title = full_deal.get("TITLE") or bitrix_deal.get("TITLE") or ""
        total_amount = parse_money_to_int(full_deal.get("OPPORTUNITY"))
        paid_amount = parse_money_to_int(full_deal.get("UF_PAID_AMOUNT"))
        term_months = parse_int(full_deal.get("UF_TERM_MONTHS"))
        initial_payment = parse_money_to_int(full_deal.get("UF_INITIAL_PAYMENT")) or 0
        
        # Проверяем, существует ли запись в БД
        db_deal = db.query(Deal).filter(Deal.deal_id == str(deal_id)).first()
        
        if db_deal:
            # Обновляем существующую запись
            # НЕ перезаписываем paid_amount, если он уже больше (защита от потери данных)
            if paid_amount > 0 and db_deal.paid_amount > paid_amount:
                logger.info(
                    f"Сделка {deal_id}: локальная оплата ({db_deal.paid_amount}) больше Bitrix ({paid_amount}), "
                    f"оставляем локальную"
                )
                paid_amount = db_deal.paid_amount
            
            db_deal.title = title
            db_deal.email = email or db_deal.email  # Обновляем email, если он есть в Bitrix
            db_deal.total_amount = total_amount
            db_deal.paid_amount = paid_amount
            db_deal.initial_payment = initial_payment
            db_deal.term_months = term_months
            db_deal.updated_at = datetime.utcnow()
            
            action = "обновлена"
        else:
            # Создаем новую запись
            db_deal = Deal(
                deal_id=str(deal_id),
                title=title,
                email=email,
                total_amount=total_amount,
                paid_amount=paid_amount,
                initial_payment=initial_payment,
                term_months=term_months,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(db_deal)
            action = "создана"
        
        db.commit()
        db.refresh(db_deal)
        
        return True, f"Сделка {deal_id} ({title[:30]}...) {action}"
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при синхронизации сделки {deal_id}: {e}", exc_info=True)
        return False, f"Ошибка: {str(e)}"


def main():
    """Основная функция синхронизации"""
    logger.info("Начало синхронизации данных из Bitrix24 в БД")
    
    # Инициализируем БД
    init_db()
    
    # Получаем сессию БД
    db = next(get_db())
    
    try:
        # Получаем все сделки с рассрочкой из Bitrix24
        logger.info("Получение списка сделок из Bitrix24...")
        bitrix_deals = get_all_installment_deals()
        logger.info(f"Найдено {len(bitrix_deals)} сделок с рассрочкой в Bitrix24")
        
        if not bitrix_deals:
            logger.warning("Не найдено ни одной сделки с рассрочкой в Bitrix24")
            return
        
        # Синхронизируем каждую сделку
        success_count = 0
        error_count = 0
        
        for i, bitrix_deal in enumerate(bitrix_deals, 1):
            deal_id = bitrix_deal.get("ID", "unknown")
            logger.info(f"[{i}/{len(bitrix_deals)}] Обработка сделки {deal_id}...")
            
            success, message = sync_deal_to_db(db, bitrix_deal)
            
            if success:
                success_count += 1
                logger.info(f"✓ {message}")
            else:
                error_count += 1
                logger.error(f"✗ {message}")
        
        logger.info("=" * 60)
        logger.info(f"Синхронизация завершена:")
        logger.info(f"  Успешно: {success_count}")
        logger.info(f"  Ошибок: {error_count}")
        logger.info(f"  Всего: {len(bitrix_deals)}")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при синхронизации: {e}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
