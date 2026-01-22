#!/usr/bin/env python3
"""
Проверка конкретных сделок по ID.

Использование:
    python -m scripts.check_specific_deals 469 879 731
"""

import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.payment_log import init_db, get_db
from models.deal import Deal
from bitrix.client import _get_full_deal
from bitrix.parsing import parse_money_to_int, parse_int
from core.config import settings
import requests

def check_deal_in_db(deal_id: str, db):
    """Проверка сделки в БД"""
    deal = db.query(Deal).filter(Deal.deal_id == str(deal_id)).first()
    if deal:
        print(f"  ✓ Найдена в БД:")
        print(f"    - ID: {deal.deal_id}")
        print(f"    - Название: {deal.title}")
        print(f"    - Email: {deal.email or 'не указан'}")
        print(f"    - Общая сумма: {deal.total_amount}")
        print(f"    - Оплачено: {deal.paid_amount}")
        print(f"    - Первоначальный взнос: {deal.initial_payment}")
        print(f"    - Срок (месяцев): {deal.term_months}")
        print(f"    - Сумма рассрочки: {max(0, deal.total_amount - deal.initial_payment)}")
        return True
    else:
        print(f"  ✗ НЕ найдена в БД")
        return False

def check_deal_in_bitrix(deal_id: str):
    """Проверка сделки в Bitrix24"""
    try:
        full_deal = _get_full_deal(deal_id)
        if full_deal:
            print(f"  ✓ Найдена в Bitrix24:")
            print(f"    - ID: {full_deal.get('ID')}")
            print(f"    - Название: {full_deal.get('TITLE', 'N/A')}")
            print(f"    - Тип оплаты: {full_deal.get('TYPE_PAYMENT', 'N/A')}")
            print(f"    - Общая сумма: {full_deal.get('OPPORTUNITY', 'N/A')}")
            print(f"    - UF_PAID_AMOUNT: {full_deal.get('UF_PAID_AMOUNT', 'N/A')}")
            print(f"    - UF_TERM_MONTHS: {full_deal.get('UF_TERM_MONTHS', 'N/A')}")
            print(f"    - UF_INITIAL_PAYMENT: {full_deal.get('UF_INITIAL_PAYMENT', 'N/A')}")
            
            # Проверяем, есть ли контакт
            contact_id = full_deal.get('CONTACT_ID')
            if contact_id:
                try:
                    url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.get"
                    params = {"ID": contact_id}
                    res = requests.get(url, params=params, timeout=10)
                    if res.status_code == 200:
                        contact = res.json().get("result", {})
                        email_val = contact.get("EMAIL")
                        email = ""
                        if isinstance(email_val, list) and email_val:
                            first = email_val[0]
                            email = first.get("VALUE", "") if isinstance(first, dict) else str(first)
                        elif isinstance(email_val, str):
                            email = email_val
                        print(f"    - Email контакта: {email or 'не указан'}")
                except Exception as e:
                    print(f"    - Email контакта: ошибка получения ({e})")
            
            return True
        else:
            print(f"  ✗ НЕ найдена в Bitrix24")
            return False
    except Exception as e:
        print(f"  ✗ Ошибка при запросе к Bitrix24: {e}")
        return False

def main():
    """Основная функция"""
    # Получаем ID из аргументов командной строки
    if len(sys.argv) < 2:
        print("Использование: python -m scripts.check_specific_deals <deal_id1> <deal_id2> ...")
        print("Пример: python -m scripts.check_specific_deals 469 879 731")
        sys.exit(1)
    
    deal_ids = sys.argv[1:]
    
    print("=" * 60)
    print(f"ПРОВЕРКА СДЕЛОК: {', '.join(deal_ids)}")
    print("=" * 60 + "\n")
    
    # Инициализируем БД
    init_db()
    db = next(get_db())
    
    try:
        for deal_id in deal_ids:
            print(f"\n{'=' * 60}")
            print(f"СДЕЛКА {deal_id}")
            print("=" * 60)
            
            # Проверка в БД
            print("\n📊 В локальной БД:")
            in_db = check_deal_in_db(deal_id, db)
            
            # Проверка в Bitrix24
            print("\n🔗 В Bitrix24:")
            in_bitrix = check_deal_in_bitrix(deal_id)
            
            # Анализ
            print("\n📋 Анализ:")
            if in_db and in_bitrix:
                print("  ✓ Сделка есть и в БД, и в Bitrix24")
                deal = db.query(Deal).filter(Deal.deal_id == str(deal_id)).first()
                if deal:
                    total = deal.total_amount or 0
                    initial = deal.initial_payment or 0
                    installment = max(0, total - initial)
                    print(f"  - Сумма рассрочки: {installment}")
                    if installment <= 0:
                        print("  ⚠️ ВНИМАНИЕ: Сумма рассрочки = 0, поэтому сделка могла быть отфильтрована")
                    if deal.term_months == 0:
                        print("  ⚠️ ВНИМАНИЕ: Срок рассрочки = 0 (не настроен)")
            elif in_db and not in_bitrix:
                print("  ⚠️ Сделка есть в БД, но НЕТ в Bitrix24")
            elif not in_db and in_bitrix:
                print("  ⚠️ Сделка есть в Bitrix24, но НЕТ в БД")
                print("  💡 Решение: запустите синхронизацию")
                print("     python -m scripts.sync_bitrix_to_db")
            else:
                print("  ❌ Сделка не найдена ни в БД, ни в Bitrix24")
        
        print("\n" + "=" * 60)
        print("ПРОВЕРКА ЗАВЕРШЕНА")
        print("=" * 60)
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
