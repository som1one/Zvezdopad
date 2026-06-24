"""
Клиент для работы с пользователями и контактами Bitrix24.
"""

import requests
import logging
from typing import Optional, Dict, Any, List
from core.config import settings

logger = logging.getLogger(__name__)

def get_contact_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Получает контакт из Bitrix24 по email.
    
    Args:
        email: Email адрес для поиска
    
    Returns:
        Словарь с данными контакта или None если не найден
    """
    try:
        url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.list"
        payload = {
            "filter": {"EMAIL": email},
            "select": [
                "ID",
                "NAME",
                "LAST_NAME",
                "SECOND_NAME",
                "EMAIL",
                "PHONE",
                "BIRTHDATE",
                "COMPANY_ID",
                "ASSIGNED_BY_ID",
                "DATE_CREATE",
                "DATE_MODIFY"
            ]
        }
        
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        data = res.json()
        contacts = data.get("result", [])
        
        if contacts:
            logger.info(f"Найден контакт в Bitrix24 для email {email}: ID={contacts[0].get('ID')}")
            return contacts[0]
        else:
            logger.warning(f"Контакт не найден в Bitrix24 для email {email}")
            return None
            
    except requests.Timeout as e:
        logger.error(f"Timeout при получении контакта из Bitrix24 для email {email}: {e}")
        return None
    except requests.RequestException as e:
        logger.error(
            f"Ошибка сети при получении контакта из Bitrix24 для email {email}: {e}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Неожиданная ошибка при получении контакта из Bitrix24 для email {email}: {e}",
            exc_info=True
        )
        return None

def get_all_contacts(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Получает список всех контактов из Bitrix24.
    
    Args:
        limit: Максимальное количество контактов
    
    Returns:
        Список контактов
    """
    try:
        url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.list"
        payload = {
            "select": [
                "ID",
                "NAME",
                "LAST_NAME",
                "EMAIL",
                "PHONE"
            ],
            "order": {"DATE_CREATE": "DESC"},
            "limit": limit
        }
        
        res = requests.post(url, json=payload, timeout=30)
        res.raise_for_status()
        data = res.json()
        contacts = data.get("result", [])
        
        logger.info(f"Получено {len(contacts)} контактов из Bitrix24")
        return contacts
        
    except Exception as e:
        logger.error(f"Ошибка при получении контактов из Bitrix24: {e}", exc_info=True)
        return []

def verify_contact_exists(email: str) -> bool:
    """
    Проверяет, существует ли контакт в Bitrix24.
    
    Args:
        email: Email адрес для проверки
    
    Returns:
        True если контакт существует, False иначе
    """
    contact = get_contact_by_email(email)
    return contact is not None

