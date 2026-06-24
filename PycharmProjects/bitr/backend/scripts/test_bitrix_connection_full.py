"""
Полный тест подключения к Bitrix24 с новым вебхуком.
Проверяет все необходимые права доступа.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_bitrix_connection():
    """Тестирует подключение к Bitrix24 и проверяет права"""
    
    print("="*80)
    print("ТЕСТ ПОДКЛЮЧЕНИЯ К BITRIX24")
    print("="*80)
    print(f"\nWebhook URL: {settings.BITRIX_WEBHOOK_URL}\n")
    
    tests = [
        {
            "name": "1. Проверка подключения (profile)",
            "method": "profile",
            "params": {}
        },
        {
            "name": "2. Получение списка контактов",
            "method": "crm.contact.list",
            "params": {
                "select": ["ID", "NAME", "EMAIL"],
                "limit": 5
            }
        },
        {
            "name": "3. Получение списка сделок",
            "method": "crm.deal.list",
            "params": {
                "filter": {"TYPE_PAYMENT": "Рассрочка"},
                "select": ["ID", "TITLE", "OPPORTUNITY"],
                "limit": 5
            }
        },
        {
            "name": "4. Получение полных данных сделки",
            "method": "crm.deal.get",
            "params": {
                "id": "819"  # Замените на реальный ID сделки
            }
        },
        {
            "name": "5. Обновление сделки (тест прав)",
            "method": "crm.deal.update",
            "params": {
                "id": "819",  # Замените на реальный ID сделки
                "fields": {
                    "COMMENTS": "Тест обновления"
                }
            }
        }
    ]
    
    results = []
    
    for test in tests:
        print(f"\n{test['name']}")
        print("-"*80)
        
        try:
            url = f"{settings.BITRIX_WEBHOOK_URL}{test['method']}"
            response = requests.post(url, json=test['params'], timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                print(f"❌ Ошибка: {data.get('error_description', data.get('error'))}")
                results.append({"test": test['name'], "status": "error", "error": data.get('error')})
            else:
                print(f"✅ Успешно!")
                if "result" in data:
                    result = data["result"]
                    if isinstance(result, list):
                        print(f"   Получено записей: {len(result)}")
                    elif isinstance(result, dict):
                        print(f"   Получены данные: {list(result.keys())[:10]}")
                    else:
                        print(f"   Результат: {result}")
                results.append({"test": test['name'], "status": "success"})
                
        except requests.Timeout:
            print(f"❌ Timeout при запросе")
            results.append({"test": test['name'], "status": "timeout"})
        except requests.RequestException as e:
            print(f"❌ Ошибка запроса: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"   Детали: {error_data}")
                except:
                    print(f"   Статус: {e.response.status_code}")
            results.append({"test": test['name'], "status": "error", "error": str(e)})
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            results.append({"test": test['name'], "status": "error", "error": str(e)})
    
    print("\n" + "="*80)
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*80)
    
    success_count = sum(1 for r in results if r['status'] == 'success')
    total_count = len(results)
    
    print(f"\nУспешно: {success_count}/{total_count}")
    
    for result in results:
        status_icon = "✅" if result['status'] == 'success' else "❌"
        print(f"{status_icon} {result['test']}: {result['status']}")
        if result['status'] == 'error' and 'error' in result:
            print(f"   Ошибка: {result['error']}")
    
    print("\n" + "="*80)
    
    if success_count == total_count:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Подключение работает корректно.")
    else:
        print("⚠️ Некоторые тесты не прошли. Проверьте права вебхука в Bitrix24.")
    
    return results

if __name__ == "__main__":
    test_bitrix_connection()

