#!/usr/bin/env python3
"""
Проверка ключей YooKassa.

Использование:
    python -m scripts.check_yookassa_keys
"""

import sys
import os
import requests

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings

def check_keys():
    """Проверяет ключи YooKassa"""
    shop_id = settings.YOOKASSA_SHOP_ID
    secret = settings.YOOKASSA_SECRET
    
    print("=" * 60)
    print("ПРОВЕРКА КЛЮЧЕЙ YOOKASSA")
    print("=" * 60)
    print()
    
    # Проверяем формат ключей
    print("📋 Информация о ключах:")
    print(f"  Shop ID: {shop_id[:10]}..." if shop_id and len(shop_id) > 10 else f"  Shop ID: {shop_id}")
    
    if secret:
        if secret.startswith("test_"):
            print(f"  ⚠️  Секретный ключ: test_... (ТЕСТОВЫЙ МАГАЗИН)")
            print("  ⚠️  ВНИМАНИЕ: Используется тестовый магазин!")
        elif secret.startswith("live_"):
            print(f"  ✅ Секретный ключ: live_... (РАБОЧИЙ МАГАЗИН)")
        else:
            print(f"  ⚠️  Секретный ключ: {secret[:10]}... (неизвестный формат)")
    else:
        print("  ❌ Секретный ключ не установлен")
    
    print()
    
    # Проверяем подключение к API
    print("🔗 Проверка подключения к API YooKassa...")
    try:
        sess = requests.Session()
        sess.auth = (shop_id, secret)
        resp = sess.get("https://api.yookassa.ru/v3/me", timeout=20)
        
        if resp.status_code == 200:
            print("  ✅ Подключение успешно!")
            data = resp.json()
            print(f"  Название магазина: {data.get('account', {}).get('fiscal_inn', 'N/A')}")
            print(f"  Статус: {data.get('account', {}).get('status', 'N/A')}")
        elif resp.status_code == 401:
            print("  ❌ Ошибка авторизации (401)")
            print("  Возможные причины:")
            print("    - Неверный Shop ID")
            print("    - Неверный секретный ключ")
            print("    - Тестовые ключи используются в рабочем режиме (или наоборот)")
        else:
            print(f"  ⚠️  Неожиданный статус: {resp.status_code}")
            print(f"  Ответ: {resp.text[:200]}")
    except Exception as e:
        print(f"  ❌ Ошибка подключения: {e}")
    
    print()
    print("=" * 60)
    
    # Рекомендации
    if secret and secret.startswith("test_"):
        print()
        print("⚠️  РЕКОМЕНДАЦИИ:")
        print("  1. Замените тестовые ключи на рабочие в файле .env")
        print("  2. Рабочие ключи начинаются с 'live_'")
        print("  3. Получите ключи в личном кабинете YooKassa")
        print("  4. Перезапустите backend после изменения")
        print()

if __name__ == "__main__":
    check_keys()
