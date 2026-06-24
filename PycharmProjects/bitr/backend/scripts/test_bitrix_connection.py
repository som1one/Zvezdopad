#!/usr/bin/env python3
"""
Скрипт для тестирования подключения к Bitrix24 API
"""

import requests
import json
import sys

BITRIX_WEBHOOK_URL = "https://karkas.bitrix24.ru/rest/153/6uraxwf9k813lbcm"

def get_all_uf_fields():
    """Получает все пользовательские поля с их значениями из реальной сделки"""
    url = f"{BITRIX_WEBHOOK_URL}/crm.deal.get"
    payload = {"id": "217"}
    r = requests.post(url, json=payload, timeout=10)
    deal = r.json().get("result", {})
    
    # Получаем описание полей
    url_fields = f"{BITRIX_WEBHOOK_URL}/crm.deal.fields"
    r_fields = requests.get(url_fields, timeout=10)
    fields_info = r_fields.json().get("result", {})
    
    print("\nПользовательские поля в сделке #217:")
    print("-" * 60)
    for key in sorted(deal.keys()):
        if key.startswith("UF_"):
            field_info = fields_info.get(key, {})
            title = field_info.get("title", key)
            field_type = field_info.get("type", "unknown")
            value = deal[key]
            print(f"{key}:")
            print(f"  Название: {title}")
            print(f"  Тип: {field_type}")
            print(f"  Значение: {value}")
            print()

def test_connection():
    """Тестирует подключение к Bitrix24"""
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ПОДКЛЮЧЕНИЯ К BITRIX24")
    print("=" * 60)
    print(f"Webhook URL: {BITRIX_WEBHOOK_URL}\n")
    
    # Тест 1: Получить список сделок с типом оплаты "Рассрочка"
    print("1. Поиск сделок с типом оплаты 'Рассрочка':")
    print("-" * 60)
    url = f"{BITRIX_WEBHOOK_URL}/crm.deal.list"
    payload = {
        "filter": {
            "TYPE_PAYMENT": "Рассрочка"
        },
        "select": [
            "ID",
            "TITLE",
            "OPPORTUNITY",
            "TYPE_PAYMENT",
            "EMAIL",
            "UF_TERM_MONTHS",
            "UF_PAID_AMOUNT"
        ],
        "start": 0,
        "limit": 10
    }
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        deals = data.get("result", [])
        
        print(f"✅ Найдено сделок: {len(deals)}")
        
        if deals:
            print("\nПервые 3 сделки:")
            for i, deal in enumerate(deals[:3], 1):
                print(f"\n  Сделка {i}:")
                print(f"    ID: {deal.get('ID')}")
                print(f"    Название: {deal.get('TITLE')}")
                print(f"    Сумма: {deal.get('OPPORTUNITY')}")
                print(f"    Тип оплаты: {deal.get('TYPE_PAYMENT')}")
                print(f"    Email: {deal.get('EMAIL')}")
                print(f"    Срок (мес): {deal.get('UF_TERM_MONTHS')}")
                print(f"    Оплачено: {deal.get('UF_PAID_AMOUNT')}")
                print(f"    Все поля: {list(deal.keys())}")
        else:
            print("⚠️  Сделки с типом оплаты 'Рассрочка' не найдены")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    
    # Тест 2: Получить детали одной сделки
    if deals:
        print("\n" + "=" * 60)
        print("2. Детали первой сделки:")
        print("-" * 60)
        deal_id = deals[0].get("ID")
        url = f"{BITRIX_WEBHOOK_URL}/crm.deal.get"
        payload = {"id": deal_id}
        
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
            data = r.json()
            deal = data.get("result", {})
            
            print(f"✅ Сделка ID: {deal_id}")
            print("\nВсе доступные поля:")
            for key in sorted(deal.keys()):
                value = deal[key]
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)[:100]
                print(f"  {key}: {value}")
                
        except Exception as e:
            print(f"❌ Ошибка: {e}")
    
    # Тест 3: Проверить доступные пользовательские поля
    print("\n" + "=" * 60)
    print("3. Поиск пользовательских полей (UF_*):")
    print("-" * 60)
    url = f"{BITRIX_WEBHOOK_URL}/crm.deal.fields"
    
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        fields = data.get("result", {})
        
        uf_fields = {k: v for k, v in fields.items() if k.startswith("UF_")}
        print(f"✅ Найдено пользовательских полей: {len(uf_fields)}")
        
        print("\nПоля, связанные с рассрочкой:")
        for key, field in uf_fields.items():
            title = field.get("title", "")
            if any(word in title.lower() for word in ["рассроч", "срок", "оплат", "месяц", "term", "paid"]):
                print(f"  {key}: {title} (тип: {field.get('type')})")
                
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    
    # Тест 4: Получить все пользовательские поля с их значениями
    get_all_uf_fields()
    
    print("\n" + "=" * 60)
    print("РЕЗЮМЕ:")
    print("=" * 60)
    print("✅ API Bitrix24 работает")
    print(f"✅ Найдено сделок с фильтром 'Рассрочка': {len(deals)}")
    print("⚠️  Поля TYPE_PAYMENT, UF_TERM_MONTHS, UF_PAID_AMOUNT не найдены")
    print("💡 Нужно:")
    print("   1. Создать эти поля в Bitrix24 или")
    print("   2. Использовать существующие пользовательские поля")
    print("   3. Обновить фильтр для поиска сделок с рассрочкой")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    test_connection()

