"""
Тестовый скрипт для вывода всех данных, которые получаются из Bitrix24.
Показывает полную структуру данных каждой сделки.
"""

import sys
import os
import json
from datetime import datetime
from pprint import pprint

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models.payment_log import SessionLocal
from models.deal import Deal
from bitrix.client import get_all_installment_deals, _get_full_deal, get_installment_deal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_bitrix_data():
    """Тестирует получение данных из Bitrix24 и выводит все поля"""
    
    print("\n" + "="*100)
    print("ТЕСТ ПОЛУЧЕНИЯ ДАННЫХ ИЗ BITRIX24")
    print("="*100 + "\n")
    
    # 1. Получаем все рассрочки через список
    print("1. Получение списка всех рассрочек (get_all_installment_deals)...")
    print("-"*100)
    try:
        all_deals = get_all_installment_deals()
        print(f"✓ Получено сделок: {len(all_deals)}")
        
        if all_deals:
            print(f"\nПоля в первой сделке из списка:")
            first_deal = all_deals[0]
            print(f"  Ключи: {list(first_deal.keys())}")
            print(f"\n  Детали первой сделки:")
            for key, value in sorted(first_deal.items()):
                print(f"    {key}: {value} (тип: {type(value).__name__})")
        else:
            print("⚠ Нет сделок в списке")
    except Exception as e:
        print(f"✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    # 2. Для каждой сделки получаем полные данные
    print("\n\n2. Получение полных данных каждой сделки (_get_full_deal)...")
    print("-"*100)
    
    db = SessionLocal()
    try:
        for i, deal_summary in enumerate(all_deals[:5], 1):  # Ограничиваем первыми 5 для удобства
            deal_id = deal_summary.get("ID")
            if not deal_id:
                continue
                
            print(f"\n{i}. Сделка ID: {deal_id}")
            print(f"   Краткие данные из списка:")
            print(f"     TITLE: {deal_summary.get('TITLE', '—')}")
            print(f"     OPPORTUNITY: {deal_summary.get('OPPORTUNITY', '—')}")
            print(f"     UF_TERM_MONTHS: {deal_summary.get('UF_TERM_MONTHS', '—')}")
            print(f"     UF_PAID_AMOUNT: {deal_summary.get('UF_PAID_AMOUNT', '—')}")
            print(f"     CONTACT_ID: {deal_summary.get('CONTACT_ID', '—')}")
            print(f"     STAGE_ID: {deal_summary.get('STAGE_ID', '—')}")
            
            try:
                full_deal = _get_full_deal(deal_id)
                if full_deal:
                    print(f"\n   ✓ Полные данные получены")
                    print(f"   Ключи в полных данных: {list(full_deal.keys())}")
                    print(f"\n   Все поля полных данных:")
                    for key, value in sorted(full_deal.items()):
                        value_str = str(value)[:100] if value else "None"
                        if len(str(value)) > 100:
                            value_str += "..."
                        print(f"     {key:30} = {value_str} (тип: {type(value).__name__})")
                else:
                    print(f"   ✗ Не удалось получить полные данные")
            except Exception as e:
                print(f"   ✗ Ошибка при получении полных данных: {e}")
            
            # Проверяем данные в локальной БД
            db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
            if db_deal:
                print(f"\n   Данные в локальной БД:")
                print(f"     deal_id: {db_deal.deal_id}")
                print(f"     title: {db_deal.title}")
                print(f"     email: {db_deal.email}")
                print(f"     total_amount: {db_deal.total_amount}")
                print(f"     paid_amount: {db_deal.paid_amount}")
                print(f"     term_months: {db_deal.term_months}")
            else:
                print(f"\n   ⚠ Нет данных в локальной БД")
                
    finally:
        db.close()
    
    # 3. Тест получения сделки по email
    print("\n\n3. Тест получения сделки по email (get_installment_deal)...")
    print("-"*100)
    
    # Получаем email из БД
    db = SessionLocal()
    try:
        db_deal = db.query(Deal).first()
        if db_deal and db_deal.email:
            test_email = db_deal.email
            print(f"Используем email: {test_email}")
            
            try:
                deal_by_email = get_installment_deal(test_email)
                if deal_by_email:
                    print(f"\n✓ Сделка найдена по email")
                    print(f"  ID: {deal_by_email.get('ID')}")
                    print(f"  TITLE: {deal_by_email.get('TITLE', '—')}")
                    print(f"  OPPORTUNITY: {deal_by_email.get('OPPORTUNITY', '—')}")
                    print(f"  UF_TERM_MONTHS: {deal_by_email.get('UF_TERM_MONTHS', '—')}")
                    print(f"  UF_PAID_AMOUNT: {deal_by_email.get('UF_PAID_AMOUNT', '—')}")
                    print(f"\n  Все поля:")
                    for key, value in sorted(deal_by_email.items()):
                        value_str = str(value)[:80] if value else "None"
                        if len(str(value)) > 80:
                            value_str += "..."
                        print(f"    {key:30} = {value_str}")
                else:
                    print(f"✗ Сделка не найдена по email {test_email}")
            except Exception as e:
                print(f"✗ Ошибка при получении сделки по email: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("⚠ Нет сделок в БД с email для теста")
    finally:
        db.close()
    
    # 4. Сохраняем данные в JSON файл
    print("\n\n4. Сохранение данных в JSON файл...")
    print("-"*100)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f"bitrix_data_test_{timestamp}.json"
    
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_deals_in_list": len(all_deals),
            "deals": []
        }
    }
    
    for deal_summary in all_deals:
        deal_id = deal_summary.get("ID")
        deal_data = {
            "id": deal_id,
            "summary_data": deal_summary.copy()
        }
        
        # Получаем полные данные
        try:
            full_deal = _get_full_deal(deal_id)
            if full_deal:
                deal_data["full_data"] = full_deal.copy()
        except Exception as e:
            deal_data["full_data_error"] = str(e)
        
        # Данные из БД
        db = SessionLocal()
        try:
            db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
            if db_deal:
                deal_data["local_db_data"] = {
                    "deal_id": db_deal.deal_id,
                    "title": db_deal.title,
                    "email": db_deal.email,
                    "total_amount": db_deal.total_amount,
                    "paid_amount": db_deal.paid_amount,
                    "term_months": db_deal.term_months
                }
        finally:
            db.close()
        
        output_data["summary"]["deals"].append(deal_data)
    
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"✓ Данные сохранены в {json_filename}")
    
    print("\n" + "="*100)
    print("ТЕСТ ЗАВЕРШЕН")
    print("="*100 + "\n")

if __name__ == "__main__":
    test_bitrix_data()

