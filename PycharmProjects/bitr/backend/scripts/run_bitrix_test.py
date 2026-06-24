#!/usr/bin/env python3
"""Простой скрипт для вывода данных из Bitrix24 в текстовом формате"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bitrix.client import get_all_installment_deals, _get_full_deal
from models.payment_log import SessionLocal
from models.deal import Deal

def main():
    print("="*80)
    print("BITRIX24 ДАННЫЕ - ТЕСТ")
    print("="*80)
    print()
    
    # Получаем список всех рассрочек
    print("1. Получение списка всех рассрочек...")
    all_deals = get_all_installment_deals()
    print(f"   Всего сделок: {len(all_deals)}")
    
    if all_deals:
        print(f"\n   Поля в списке: {', '.join(list(all_deals[0].keys()))}")
    print()
    
    # Обрабатываем каждую сделку
    db = SessionLocal()
    try:
        for i, deal_summary in enumerate(all_deals[:10], 1):  # Ограничиваем 10 для читаемости
            deal_id = deal_summary.get("ID")
            print("="*80)
            print(f"СДЕЛКА #{i} - ID: {deal_id}")
            print("="*80)
            
            print("\nSUMMARY DATA (из списка):")
            print("-"*80)
            for key, value in sorted(deal_summary.items()):
                value_str = str(value)[:100] if value else "None"
                if len(str(value)) > 100:
                    value_str += "..."
                print(f"  {key:30} = {value_str}")
            
            print("\nFULL DATA (полные данные):")
            print("-"*80)
            try:
                full_deal = _get_full_deal(deal_id)
                if full_deal:
                    print(f"  Всего полей: {len(full_deal.keys())}")
                    print(f"  Поля: {', '.join(sorted(full_deal.keys()))}")
                    print("\n  Значения (первые 30 полей):")
                    for key, value in sorted(list(full_deal.items()))[:30]:
                        value_str = str(value)[:80] if value else "None"
                        if len(str(value)) > 80:
                            value_str += "..."
                        print(f"    {key:30} = {value_str}")
                else:
                    print("  ✗ Не удалось получить полные данные")
            except Exception as e:
                print(f"  ✗ Ошибка: {e}")
            
            print("\nLOCAL DB (локальная база данных):")
            print("-"*80)
            db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
            if db_deal:
                print(f"  title:        {db_deal.title}")
                print(f"  email:        {db_deal.email}")
                print(f"  total_amount: {db_deal.total_amount}")
                print(f"  paid_amount:  {db_deal.paid_amount}")
                print(f"  term_months:  {db_deal.term_months}")
            else:
                print("  ✗ Нет данных в локальной БД")
            
            print()
    
    finally:
        db.close()
    
    print("="*80)
    print("ТЕСТ ЗАВЕРШЕН")
    print("="*80)

if __name__ == "__main__":
    main()

