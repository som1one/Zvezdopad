"""
Скрипт для получения всех рассрочек и их информации.
Можно запустить через docker-compose exec backend python -c "exec(open('scripts/get_all_deals_info.py').read())"
"""

import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models.payment_log import SessionLocal
from models.deal import Deal
from bitrix.client import get_all_installment_deals
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_all_deals_info():
    """Получает все рассрочки с полной информацией"""
    
    db = SessionLocal()
    try:
        print("="*80)
        print("ПОЛУЧЕНИЕ ВСЕХ РАССРОЧЕК")
        print("="*80)
        
        # Получаем все сделки из Bitrix24
        print("\n1. Получаем сделки из Bitrix24...")
        bitrix_deals = get_all_installment_deals()
        print(f"   Найдено: {len(bitrix_deals)} сделок")
        
        # Получаем все сделки из локальной БД
        print("\n2. Получаем сделки из локальной БД...")
        db_deals = db.query(Deal).all()
        db_deals_dict = {deal.deal_id: deal for deal in db_deals}
        print(f"   Найдено: {len(db_deals)} сделок")
        
        # Объединяем данные
        print("\n3. Объединяем данные...")
        result = []
        
        for bitrix_deal in bitrix_deals:
            deal_id = bitrix_deal.get("ID")
            db_deal = db_deals_dict.get(deal_id)
            
            # Получаем сумму из Bitrix24
            opportunity = bitrix_deal.get("OPPORTUNITY", "0")
            try:
                if isinstance(opportunity, str):
                    opportunity = opportunity.replace(" ", "").replace(",", "")
                total_amount = int(float(opportunity)) if opportunity else 0
            except (ValueError, TypeError):
                total_amount = 0
            
            # Используем данные из БД как источник истины
            paid_amount = db_deal.paid_amount if db_deal else 0
            term_months = db_deal.term_months if db_deal else int(bitrix_deal.get("UF_TERM_MONTHS", "6"))
            
            # Рассчитываем ежемесячный платеж
            monthly = total_amount // term_months if term_months > 0 else 0
            remainder = total_amount % term_months if term_months > 0 else 0
            
            result.append({
                "deal_id": deal_id,
                "title": bitrix_deal.get("TITLE", ""),
                "email": db_deal.email if db_deal else None,
                "total_amount": total_amount,
                "paid_amount": paid_amount,
                "remaining_amount": max(0, total_amount - paid_amount),
                "term_months": term_months,
                "monthly_payment": monthly,
                "remainder": remainder,
                "in_db": db_deal is not None,
                "bitrix_data": {
                    "OPPORTUNITY": bitrix_deal.get("OPPORTUNITY"),
                    "UF_TERM_MONTHS": bitrix_deal.get("UF_TERM_MONTHS"),
                    "UF_PAID_AMOUNT": bitrix_deal.get("UF_PAID_AMOUNT"),
                    "CONTACT_ID": bitrix_deal.get("CONTACT_ID"),
                    "STAGE_ID": bitrix_deal.get("STAGE_ID"),
                }
            })
        
        # Сортируем по deal_id
        result.sort(key=lambda x: int(x["deal_id"]) if x["deal_id"].isdigit() else 0, reverse=True)
        
        # Выводим результаты
        print("\n" + "="*80)
        print("РЕЗУЛЬТАТЫ")
        print("="*80)
        
        for i, deal in enumerate(result, 1):
            print(f"\n{i}. ID: {deal['deal_id']}")
            print(f"   Название: {deal['title']}")
            print(f"   Email: {deal['email'] or '—'}")
            print(f"   Общая сумма: {deal['total_amount']:,} ₽")
            print(f"   Оплачено: {deal['paid_amount']:,} ₽")
            print(f"   Остаток: {deal['remaining_amount']:,} ₽")
            print(f"   Срок: {deal['term_months']} мес.")
            print(f"   Ежемесячный платеж: {deal['monthly_payment']:,} ₽")
            if deal['remainder'] > 0:
                print(f"   Остаток на последний платеж: {deal['remainder']:,} ₽")
            print(f"   В БД: {'Да' if deal['in_db'] else 'Нет'}")
            print(f"   Bitrix OPPORTUNITY: {deal['bitrix_data']['OPPORTUNITY']}")
            print(f"   Bitrix UF_TERM_MONTHS: {deal['bitrix_data']['UF_TERM_MONTHS']}")
            print(f"   Bitrix UF_PAID_AMOUNT: {deal['bitrix_data']['UF_PAID_AMOUNT']}")
        
        # Статистика
        print("\n" + "="*80)
        print("СТАТИСТИКА")
        print("="*80)
        print(f"Всего сделок: {len(result)}")
        print(f"В локальной БД: {sum(1 for d in result if d['in_db'])}")
        
        total_sum = sum(d['total_amount'] for d in result)
        paid_sum = sum(d['paid_amount'] for d in result)
        print(f"\nОбщая сумма всех рассрочек: {total_sum:,} ₽")
        print(f"Оплачено всего: {paid_sum:,} ₽")
        print(f"Остаток к оплате: {total_sum - paid_sum:,} ₽")
        print(f"Процент оплаты: {round((paid_sum / total_sum * 100) if total_sum > 0 else 0, 2)}%")
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    get_all_deals_info()

