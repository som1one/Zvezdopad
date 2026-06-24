"""
Скрипт для вывода всех рассрочек в консоль.
Запускается через docker-compose exec backend python -c "exec(open('scripts/debug_deals_data.py').read())"
Но лучше добавить это в эндпоинт API
"""

import sys
import os
import json

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models.payment_log import SessionLocal
from models.deal import Deal
from bitrix.client import get_all_installment_deals
from installments.service import normalize_deal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_all_deals():
    """Выводит информацию о всех рассрочках"""
    
    db = SessionLocal()
    try:
        print("\n" + "="*80)
        print("ДИАГНОСТИКА ВСЕХ РАССРОЧЕК")
        print("="*80 + "\n")
        
        # Получаем все сделки из Bitrix24
        print("1. Получаем сделки из Bitrix24...")
        bitrix_deals = get_all_installment_deals()
        print(f"   ✓ Найдено {len(bitrix_deals)} сделок\n")
        
        # Получаем все сделки из локальной БД
        print("2. Получаем сделки из локальной БД...")
        db_deals = db.query(Deal).all()
        db_deals_dict = {deal.deal_id: deal for deal in db_deals}
        print(f"   ✓ Найдено {len(db_deals)} сделок\n")
        
        # Обрабатываем каждую сделку
        print("3. Обработка данных каждой сделки:\n")
        
        for bitrix_deal in bitrix_deals:
            deal_id = bitrix_deal.get("ID")
            db_deal = db_deals_dict.get(deal_id)
            
            # Формируем данные для normalize_deal
            deal_data = bitrix_deal.copy()
            if db_deal:
                deal_data["UF_PAID_AMOUNT"] = str(db_deal.paid_amount)
                deal_data["UF_TERM_MONTHS"] = str(db_deal.term_months)
                deal_data["EMAIL"] = db_deal.email
                deal_data["TITLE"] = db_deal.title
            
            # Нормализуем данные
            try:
                normalized = normalize_deal(deal_data)
                deal_info = normalized["deal"]
                payments = normalized["payments"]
                
                print(f"Сделка ID: {deal_id}")
                print(f"  Название: {deal_info.get('title', '—')}")
                print(f"  Email: {deal_info.get('email', '—')}")
                print(f"  Общая сумма: {deal_info['total_amount']:,} ₽")
                print(f"  Оплачено: {deal_info['paid_amount']:,} ₽")
                print(f"  Срок: {deal_info['term_months']} мес.")
                print(f"  Оплачено месяцев: {deal_info.get('paid_months', 0)}")
                print(f"  Количество платежей в графике: {len(payments)}")
                
                if payments:
                    paid_count = sum(1 for p in payments if p.get("status") == "paid")
                    print(f"  Оплачено платежей: {paid_count} из {len(payments)}")
                    print(f"  Первый платеж: {payments[0]['month']} - {payments[0]['amount']:,} ₽ ({payments[0]['status']})")
                    if len(payments) > 1:
                        print(f"  Последний платеж: {payments[-1]['month']} - {payments[-1]['amount']:,} ₽ ({payments[-1]['status']})")
                
                print()
                
            except Exception as e:
                print(f"  ✗ Ошибка при обработке сделки {deal_id}: {e}\n")
                continue
        
        print("="*80)
        print("ДИАГНОСТИКА ЗАВЕРШЕНА")
        print("="*80 + "\n")
        
    except Exception as e:
        logger.error(f"Ошибка при диагностике: {e}", exc_info=True)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    debug_all_deals()

