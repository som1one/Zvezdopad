"""
Скрипт для экспорта всех рассрочек с информацией о сроках и оплаченных суммах.
Выводит данные в JSON и CSV форматах.
"""

import sys
import os
import json
import csv
from datetime import datetime

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.orm import Session
from models.payment_log import SessionLocal
from models.deal import Deal
from bitrix.client import get_all_installment_deals
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def export_all_deals():
    """Экспортирует все рассрочки с данными из Bitrix24 и локальной БД"""
    
    db = SessionLocal()
    try:
        # Получаем все сделки из Bitrix24
        logger.info("Получаем все сделки из Bitrix24...")
        bitrix_deals = get_all_installment_deals()
        logger.info(f"Найдено {len(bitrix_deals)} сделок в Bitrix24")
        
        # Получаем все сделки из локальной БД
        logger.info("Получаем все сделки из локальной БД...")
        db_deals = db.query(Deal).all()
        db_deals_dict = {deal.deal_id: deal for deal in db_deals}
        logger.info(f"Найдено {len(db_deals)} сделок в локальной БД")
        
        # Объединяем данные
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
            
            # Получаем email
            email = db_deal.email if db_deal else None
            
            # Определяем статус
            if total_amount > 0 and paid_amount >= total_amount:
                status = "paid"
            elif paid_amount > 0:
                status = "active"
            elif total_amount > 0:
                status = "pending"
            else:
                status = "active"
            
            result.append({
                "deal_id": deal_id,
                "title": bitrix_deal.get("TITLE", ""),
                "email": email,
                "total_amount": total_amount,
                "paid_amount": paid_amount,
                "remaining_amount": max(0, total_amount - paid_amount),
                "term_months": term_months,
                "status": status,
                "date_create": bitrix_deal.get("DATE_CREATE"),
                "stage_id": bitrix_deal.get("STAGE_ID"),
                "contact_id": bitrix_deal.get("CONTACT_ID"),
                "in_db": db_deal is not None
            })
        
        # Сортируем по deal_id
        result.sort(key=lambda x: int(x["deal_id"]) if x["deal_id"].isdigit() else 0, reverse=True)
        
        # Сохраняем в JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_filename = f"deals_export_{timestamp}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"Данные сохранены в {json_filename}")
        
        # Сохраняем в CSV
        csv_filename = f"deals_export_{timestamp}.csv"
        if result:
            with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=result[0].keys())
                writer.writeheader()
                writer.writerows(result)
            logger.info(f"Данные сохранены в {csv_filename}")
        
        # Выводим статистику
        print("\n" + "="*80)
        print("СТАТИСТИКА ПО РАССРОЧКАМ")
        print("="*80)
        print(f"Всего сделок: {len(result)}")
        print(f"В локальной БД: {sum(1 for d in result if d['in_db'])}")
        print(f"Полностью оплачено: {sum(1 for d in result if d['status'] == 'paid')}")
        print(f"В процессе: {sum(1 for d in result if d['status'] == 'active')}")
        print(f"Не оплачено: {sum(1 for d in result if d['status'] == 'pending')}")
        
        total_sum = sum(d['total_amount'] for d in result)
        paid_sum = sum(d['paid_amount'] for d in result)
        print(f"\nОбщая сумма всех рассрочек: {total_sum:,} ₽")
        print(f"Оплачено всего: {paid_sum:,} ₽")
        print(f"Остаток к оплате: {total_sum - paid_sum:,} ₽")
        print(f"Процент оплаты: {round((paid_sum / total_sum * 100) if total_sum > 0 else 0, 2)}%")
        
        # Выводим первые 10 сделок
        print("\n" + "="*80)
        print("ПРИМЕРЫ СДЕЛОК (первые 10):")
        print("="*80)
        for i, deal in enumerate(result[:10], 1):
            print(f"\n{i}. ID: {deal['deal_id']}")
            print(f"   Название: {deal['title']}")
            print(f"   Email: {deal['email'] or '—'}")
            print(f"   Общая сумма: {deal['total_amount']:,} ₽")
            print(f"   Оплачено: {deal['paid_amount']:,} ₽")
            print(f"   Остаток: {deal['remaining_amount']:,} ₽")
            print(f"   Срок: {deal['term_months']} мес.")
            print(f"   Статус: {deal['status']}")
            print(f"   В БД: {'Да' if deal['in_db'] else 'Нет'}")
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при экспорте данных: {e}", exc_info=True)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    export_all_deals()

