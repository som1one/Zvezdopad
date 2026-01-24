import requests
from core.config import settings
from typing import Optional, Dict, Any, List
import logging
from bitrix.parsing import enrich_project_fields_inplace

logger = logging.getLogger(__name__)

def get_installment_deal(email: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные о рассрочке из Bitrix24 по email пользователя.
    
    Сначала ищет контакт по email, затем находит связанную сделку с типом оплаты "Рассрочка".
    """
    try:
        # 1. Найти контакт по email
        contact_url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.list"
        contact_payload = {
            "filter": {"EMAIL": email},
            "select": ["ID"],
            "limit": 1
        }
        
        contact_res = requests.post(contact_url, json=contact_payload, timeout=10)
        contact_res.raise_for_status()
        contact_data = contact_res.json()
        
        if not contact_data.get("result"):
            logger.info(
                f"Контакт не найден в Bitrix24 для email {email}. "
                f"Рассрочка не может быть найдена без контакта."
            )
            # Если контакт не найден, значит пользователя нет в Bitrix24
            # Не возвращаем случайную сделку - возвращаем None
            return None
        
        contact_id = contact_data["result"][0]["ID"]
        logger.debug(f"Найден контакт {contact_id} для email {email}")
        
        # 2. Найти сделку с типом оплаты "Рассрочка" для этого контакта
        deal_url = f"{settings.BITRIX_WEBHOOK_URL}/crm.deal.list"
        deal_payload = {
            "filter": {
                "CONTACT_ID": contact_id,
                "TYPE_PAYMENT": "Рассрочка"
            },
            "select": [
                "ID",
                "TITLE",
                "OPPORTUNITY",
                "CONTACT_ID"
            ],
            "order": {"DATE_CREATE": "DESC"},
            "limit": 1
        }
        
        deal_res = requests.post(deal_url, json=deal_payload, timeout=10)
        deal_res.raise_for_status()
        deal_data = deal_res.json()
        
        if not deal_data.get("result"):
            logger.warning(
                f"Сделка с типом 'Рассрочка' не найдена для контакта {contact_id} "
                f"(email: {email})"
            )
            return None
        
        deal = deal_data["result"][0]
        deal_id = deal["ID"]
        logger.debug(f"Найдена сделка {deal_id} для контакта {contact_id}")
        
        # 3. Получить полные данные сделки (включая пользовательские поля)
        full_deal = _get_full_deal(deal_id)
        
        if full_deal:
            logger.info(
                f"Успешно получены данные сделки {deal_id} для email {email}, "
                f"сумма: {full_deal.get('OPPORTUNITY', 'N/A')}"
            )
        else:
            logger.warning(f"Не удалось получить полные данные сделки {deal_id} для email {email}")
        
        return full_deal
        
    except requests.Timeout as e:
        logger.error(
            f"Timeout при запросе к Bitrix24 для email {email}. "
            f"URL: {contact_url if 'contact_url' in locals() else 'unknown'}, "
            f"timeout: 10s, error: {e}"
        )
        return None
    except requests.RequestException as e:
        logger.error(
            f"Ошибка сети при запросе к Bitrix24 для email {email}. "
            f"URL: {contact_url if 'contact_url' in locals() else 'unknown'}, "
            f"status_code: {getattr(e.response, 'status_code', 'N/A') if hasattr(e, 'response') else 'N/A'}, "
            f"error: {e}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Неожиданная ошибка при получении сделки для email {email}. "
            f"Тип ошибки: {type(e).__name__}, error: {e}",
            exc_info=True
        )
        return None


def get_installment_deal_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные о рассрочке из Bitrix24 по телефону пользователя.
    
    Сначала ищет контакт по телефону, затем находит связанную сделку с типом оплаты "Рассрочка".
    Bitrix24 может хранить телефоны в разных форматах, поэтому пробуем разные варианты поиска.
    """
    try:
        # Нормализуем телефон (убираем пробелы, скобки, дефисы, плюсы)
        cleaned = phone.replace(" ", "").replace("(", "").replace(")", "").replace("-", "").replace("+", "").strip()
        
        # Варианты для поиска: с +7, без +7, с 8, только цифры
        search_variants = []
        if cleaned.startswith("7"):
            search_variants.append(f"+7{cleaned[1:]}")
            search_variants.append(f"7{cleaned[1:]}")
            search_variants.append(cleaned[1:])  # Без первой 7
        elif cleaned.startswith("8"):
            search_variants.append(f"+7{cleaned[1:]}")
            search_variants.append(f"7{cleaned[1:]}")
            search_variants.append(cleaned)
        else:
            search_variants.append(f"+7{cleaned}")
            search_variants.append(f"7{cleaned}")
            search_variants.append(cleaned)
        
        # Также добавляем исходный номер для поиска
        if phone not in search_variants:
            search_variants.insert(0, phone)
        
        logger.info(f"Поиск контакта по телефону {phone}, нормализованный: {cleaned}, варианты поиска: {search_variants}")
        
        # 1. Найти контакт по телефону - пробуем разные варианты
        contact_url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.list"
        contact_id = None
        
        for search_phone in search_variants:
            # Пробуем точный поиск
            contact_payload = {
                "filter": {"PHONE": search_phone},
                "select": ["ID"],
                "limit": 1
            }
            
            contact_res = requests.post(contact_url, json=contact_payload, timeout=10)
            contact_res.raise_for_status()
            contact_data = contact_res.json()
            
            if contact_data.get("result"):
                contact_id = contact_data["result"][0]["ID"]
                logger.debug(f"Найден контакт {contact_id} для телефона {phone} (вариант поиска: {search_phone})")
                break
        
        # Если не нашли точным поиском, пробуем получить все контакты и искать вручную
        if not contact_id:
            logger.debug(f"Точный поиск не дал результатов, пробуем получить все контакты со сделками рассрочки")
            # Получаем все сделки с рассрочкой и проверяем их контакты
            deals = get_all_installment_deals()
            for deal in deals:
                deal_contact_id = deal.get('CONTACT_ID')
                if not deal_contact_id:
                    continue
                
                try:
                    contact_res = requests.get(
                        f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.get",
                        params={"ID": deal_contact_id},
                        timeout=10
                    )
                    if contact_res.status_code == 200:
                        contact = contact_res.json().get('result', {})
                        contact_phone = contact.get('PHONE')
                        
                        # Проверяем все варианты телефона контакта
                        contact_phones = []
                        if contact_phone:
                            if isinstance(contact_phone, list):
                                for p in contact_phone:
                                    if isinstance(p, dict):
                                        contact_phones.append(p.get('VALUE', ''))
                                    else:
                                        contact_phones.append(str(p))
                            elif isinstance(contact_phone, str):
                                contact_phones.append(contact_phone)
                        
                        # Если телефона нет в PHONE, проверяем NAME (иногда телефон хранится там)
                        if not contact_phones:
                            contact_name = contact.get('NAME', '')
                            if contact_name and any(c.isdigit() for c in contact_name) and ('+' in contact_name or len([c for c in contact_name if c.isdigit()]) >= 10):
                                contact_phones.append(contact_name)
                        
                        # Нормализуем телефоны контакта и сравниваем
                        for contact_phone_val in contact_phones:
                            if not contact_phone_val:
                                continue
                            cleaned_contact = contact_phone_val.replace(" ", "").replace("(", "").replace(")", "").replace("-", "").replace("+", "").strip()
                            cleaned_input = cleaned.replace(" ", "").replace("(", "").replace(")", "").replace("-", "").replace("+", "").strip()
                            
                            # Сравниваем последние 10 цифр (обычно это номер без кода страны)
                            # Убираем первые символы если они есть (7 или +7)
                            contact_digits = cleaned_contact[-10:] if len(cleaned_contact) >= 10 else cleaned_contact
                            input_digits = cleaned_input[-10:] if len(cleaned_input) >= 10 else cleaned_input
                            
                            # Также пробуем сравнить без первых 1-2 цифр (на случай если в одном формате есть код страны, в другом нет)
                            contact_tail = cleaned_contact[-9:] if len(cleaned_contact) >= 9 else cleaned_contact
                            input_tail = cleaned_input[-9:] if len(cleaned_input) >= 9 else cleaned_input
                            
                            if (contact_digits == input_digits or 
                                cleaned_contact == cleaned_input or
                                contact_tail == input_tail or
                                cleaned_contact.endswith(input_digits) or
                                cleaned_input.endswith(contact_digits)):
                                contact_id = deal_contact_id
                                logger.info(f"Найден контакт {contact_id} для телефона {phone} через сравнение (контакт: {contact_phone_val}, нормализованный: {cleaned_contact})")
                                break
                        
                        if contact_id:
                            break
                except Exception as e:
                    logger.debug(f"Ошибка при проверке контакта {deal_contact_id}: {e}")
                    continue
        
        if not contact_id:
            logger.info(
                f"Контакт не найден в Bitrix24 для телефона {phone} после всех попыток поиска. "
                f"Рассрочка не может быть найдена без контакта."
            )
            return None
        
        # 2. Найти сделку с типом оплаты "Рассрочка" для этого контакта
        deal_url = f"{settings.BITRIX_WEBHOOK_URL}/crm.deal.list"
        deal_payload = {
            "filter": {
                "CONTACT_ID": contact_id,
                "TYPE_PAYMENT": "Рассрочка"
            },
            "select": [
                "ID",
                "TITLE",
                "OPPORTUNITY",
                "CONTACT_ID"
            ],
            "order": {"DATE_CREATE": "DESC"},
            "limit": 1
        }
        
        deal_res = requests.post(deal_url, json=deal_payload, timeout=10)
        deal_res.raise_for_status()
        deal_data = deal_res.json()
        
        if not deal_data.get("result"):
            logger.warning(
                f"Сделка с типом 'Рассрочка' не найдена для контакта {contact_id} "
                f"(телефон: {phone})"
            )
            return None
        
        deal = deal_data["result"][0]
        deal_id = deal["ID"]
        logger.debug(f"Найдена сделка {deal_id} для контакта {contact_id}")
        
        # 3. Получить полные данные сделки (включая пользовательские поля)
        full_deal = _get_full_deal(deal_id)
        
        if full_deal:
            logger.info(
                f"Успешно получены данные сделки {deal_id} для телефона {phone}, "
                f"сумма: {full_deal.get('OPPORTUNITY', 'N/A')}"
            )
        else:
            logger.warning(f"Не удалось получить полные данные сделки {deal_id} для телефона {phone}")
        
        return full_deal
        
    except requests.Timeout as e:
        logger.error(
            f"Timeout при запросе к Bitrix24 для телефона {phone}. "
            f"URL: {contact_url if 'contact_url' in locals() else 'unknown'}, "
            f"timeout: 10s, error: {e}"
        )
        return None
    except requests.RequestException as e:
        logger.error(
            f"Ошибка сети при запросе к Bitrix24 для телефона {phone}. "
            f"URL: {contact_url if 'contact_url' in locals() else 'unknown'}, "
            f"status_code: {getattr(e.response, 'status_code', 'N/A') if hasattr(e, 'response') else 'N/A'}, "
            f"error: {e}"
        )
        return None
    except Exception as e:
        logger.error(
            f"Неожиданная ошибка при получении сделки для телефона {phone}. "
            f"Тип ошибки: {type(e).__name__}, error: {e}",
            exc_info=True
        )
        return None


def _find_deal_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Пытается найти сделку напрямую, если контакт не найден"""
    try:
        deal_url = f"{settings.BITRIX_WEBHOOK_URL}/crm.deal.list"
        deal_payload = {
            "filter": {
                "TYPE_PAYMENT": "Рассрочка"
            },
            "select": [
                "ID",
                "TITLE",
                "OPPORTUNITY",
                "CONTACT_ID"
            ],
            "order": {"DATE_CREATE": "DESC"},
            "limit": 10  # Берем последние 10 сделок
        }
        
        logger.debug(f"Поиск сделки напрямую для email {email}, URL: {deal_url}")
        deal_res = requests.post(deal_url, json=deal_payload, timeout=10)
        deal_res.raise_for_status()
        deal_data = deal_res.json()
        
        if not deal_data.get("result"):
            logger.info(f"Сделки с типом 'Рассрочка' не найдены при прямом поиске для email {email}")
            return None
        
        # Улучшенная логика: пытаемся найти сделку, связанную с контактом, у которого есть этот email
        deals = deal_data["result"]
        
        # Сначала пытаемся найти контакт по email и связать со сделкой
        try:
            contact_url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.list"
            contact_payload = {
                "filter": {"EMAIL": email},
                "select": ["ID"],
                "limit": 1
            }
            contact_res = requests.post(contact_url, json=contact_payload, timeout=10)
            contact_res.raise_for_status()
            contact_data = contact_res.json()
            
            if contact_data.get("result"):
                contact_id = str(contact_data["result"][0]["ID"])  # Приводим к строке для сравнения
                # Ищем сделку с этим контактом
                for deal in deals:
                    # CONTACT_ID может быть строкой или числом, приводим к строке
                    deal_contact_id = str(deal.get("CONTACT_ID", "")) if deal.get("CONTACT_ID") else ""
                    if deal_contact_id == contact_id:
                        deal_id = deal["ID"]
                        logger.info(f"Найдена сделка {deal_id} для контакта {contact_id} (email: {email})")
                        return _get_full_deal(deal_id)
        except Exception as e:
            logger.debug(f"Не удалось найти контакт для email {email}: {e}")
        
        # Если не нашли по контакту, берем первую сделку (fallback)
        # Логируем предупреждение, так как это может быть не та сделка
        deal = deals[0]
        deal_id = deal["ID"]
        logger.warning(
            f"Не удалось точно определить сделку для email {email}, "
            f"используем первую найденную сделку {deal_id} (может быть неверной)"
        )
        return _get_full_deal(deal_id)
        
    except requests.Timeout as e:
        logger.error(
            f"Timeout при поиске сделки напрямую для email {email}. "
            f"URL: {deal_url if 'deal_url' in locals() else 'unknown'}, timeout: 10s, error: {e}"
        )
        return None
    except requests.RequestException as e:
        logger.error(
            f"Ошибка сети при поиске сделки напрямую для email {email}. "
            f"URL: {deal_url if 'deal_url' in locals() else 'unknown'}, "
            f"status_code: {getattr(e.response, 'status_code', 'N/A') if hasattr(e, 'response') else 'N/A'}, "
            f"error: {e}",
            exc_info=True
        )
        return None
    except Exception as e:
        logger.error(
            f"Неожиданная ошибка при поиске сделки напрямую для email {email}. "
            f"Тип ошибки: {type(e).__name__}, error: {e}",
            exc_info=True
        )
        return None


def _get_full_deal(deal_id: str) -> Dict[str, Any]:
    """Получает полные данные сделки включая все поля и имя контакта"""
    try:
        url = f"{settings.BITRIX_WEBHOOK_URL}/crm.deal.get"
        payload = {"id": deal_id}
        
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        data = res.json()
        deal = data.get("result", {})
        
        # Пытаемся получить имя контакта, если есть CONTACT_ID
        contact_id = deal.get("CONTACT_ID")
        if contact_id:
            try:
                contact_res = requests.get(
                    f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.get",
                    # Bitrix24 обычно принимает ID (в вашем проекте это уже использовалось)
                    params={"ID": contact_id},
                    timeout=5
                )
                if contact_res.status_code == 200:
                    contact = contact_res.json().get("result", {})
                    # Формируем имя контакта
                    first_name = contact.get("NAME") or ""
                    last_name = contact.get("LAST_NAME") or ""
                    full_name = f"{first_name} {last_name}".strip()
                    if full_name:
                        deal["CONTACT_NAME"] = full_name
                    # Телефон контакта (берем первый VALUE)
                    phone_val = ""
                    contact_phone = contact.get("PHONE")
                    if isinstance(contact_phone, list) and contact_phone:
                        first = contact_phone[0]
                        if isinstance(first, dict):
                            phone_val = first.get("VALUE") or ""
                        else:
                            phone_val = str(first)
                    elif isinstance(contact_phone, str):
                        phone_val = contact_phone
                    if phone_val:
                        deal["CONTACT_PHONE"] = phone_val
            except Exception as e:
                logger.debug(f"Не удалось получить имя контакта {contact_id}: {e}")

        # Нормализуем проектные поля (enum/date/string) в единые ключи
        enrich_project_fields_inplace(deal)
        
        return deal
        
    except requests.Timeout as e:
        logger.error(
            f"Timeout при получении полных данных сделки {deal_id} из Bitrix24. "
            f"URL: {url if 'url' in locals() else 'unknown'}, timeout: 10s, error: {e}"
        )
        return {}
    except requests.RequestException as e:
        logger.error(
            f"Ошибка сети при получении полных данных сделки {deal_id} из Bitrix24. "
            f"URL: {url if 'url' in locals() else 'unknown'}, "
            f"status_code: {getattr(e.response, 'status_code', 'N/A') if hasattr(e, 'response') else 'N/A'}, "
            f"error: {e}",
            exc_info=True
        )
        return {}
    except Exception as e:
        logger.error(
            f"Неожиданная ошибка при получении полных данных сделки {deal_id} из Bitrix24. "
            f"Тип ошибки: {type(e).__name__}, error: {e}",
            exc_info=True
        )
        return {}

def get_all_installment_deals() -> List[Dict[str, Any]]:
    """
    Получает все сделки с типом оплаты "Рассрочка" из Bitrix24.
    
    ВАЖНО: Пользовательские поля (UF_TERM_MONTHS, UF_PAID_AMOUNT) 
    НЕ возвращаются в crm.deal.list, даже если указаны в select.
    Это особенность Bitrix24 API, а не проблема с разрешениями.
    
    Для получения этих полей нужно использовать crm.deal.get для каждой сделки.
    Однако, мы используем локальную БД как источник истины для этих данных.
    
    Returns:
        List[Dict]: Список всех сделок с рассрочкой (без пользовательских полей UF_*)
    """
    try:
        deal_url = f"{settings.BITRIX_WEBHOOK_URL}/crm.deal.list"
        all_deals = []
        start = 0
        limit = 50  # Bitrix24 по умолчанию возвращает 50 записей
        
        logger.info(f"Получаем все сделки с типом 'Рассрочка' из Bitrix24. URL: {deal_url}")
        
        while True:
            deal_payload = {
                "filter": {
                    "TYPE_PAYMENT": "Рассрочка"
                },
                "select": [
                    "ID",
                    "TITLE",
                    "OPPORTUNITY",
                    "CONTACT_ID",
                    "ASSIGNED_BY_ID",
                    "STAGE_ID",
                    "DATE_CREATE",
                    "DATE_MODIFY",
                    "BEGINDATE",
                    "CLOSEDATE",
                    "CURRENCY_ID",
                    # ВАЖНО: UF_TERM_MONTHS и UF_PAID_AMOUNT НЕ возвращаются в crm.deal.list
                    # Это особенность Bitrix24 API - пользовательские поля часто не включены в список
                    # Для получения этих полей нужно использовать crm.deal.get для каждой сделки
                    # Однако, мы используем локальную БД как источник истины для этих полей
                    "COMMENTS",
                    "SOURCE_ID",
                    "COMPANY_ID",
                    "CATEGORY_ID"
                ],
                "order": {"DATE_CREATE": "DESC"},
                "start": start
            }
            
            deal_res = requests.post(deal_url, json=deal_payload, timeout=30)
            deal_res.raise_for_status()
            deal_data = deal_res.json()
            
            deals_batch = deal_data.get("result", [])
            if not deals_batch:
                break
            
            all_deals.extend(deals_batch)
            logger.info(f"Получено {len(deals_batch)} сделок (всего: {len(all_deals)})")
            
            # Если получено меньше limit, значит это последняя страница
            if len(deals_batch) < limit:
                break
            
            start += limit
        
        logger.info(f"Всего найдено {len(all_deals)} сделок с типом 'Рассрочка' в Bitrix24")
        return all_deals
        
    except requests.Timeout as e:
        logger.error(
            f"Timeout при получении всех сделок из Bitrix24. "
            f"URL: {deal_url if 'deal_url' in locals() else 'unknown'}, timeout: 30s, error: {e}"
        )
        return []
    except requests.RequestException as e:
        logger.error(
            f"Ошибка сети при получении всех сделок из Bitrix24. "
            f"URL: {deal_url if 'deal_url' in locals() else 'unknown'}, "
            f"status_code: {getattr(e.response, 'status_code', 'N/A') if hasattr(e, 'response') else 'N/A'}, "
            f"error: {e}",
            exc_info=True
        )
        return []
    except Exception as e:
        logger.error(
            f"Неожиданная ошибка в get_all_installment_deals. "
            f"Тип ошибки: {type(e).__name__}, error: {e}",
            exc_info=True
        )
        return []


def update_paid_amount(deal_id: str, amount: int, max_retries: int = 3, retry_delay: float = 1.0):
    """
    Обновляет оплаченную сумму в Bitrix24 с retry логикой.
    Если поле UF_PAID_AMOUNT не существует, обновление не произойдет.
    В этом случае данные должны храниться в локальной БД.
    
    Args:
        deal_id: ID сделки в Bitrix24
        amount: Новая общая оплаченная сумма (не прибавка, а полная сумма!)
        max_retries: Максимальное количество попыток (по умолчанию 3)
        retry_delay: Задержка между попытками в секундах (по умолчанию 1.0)
    
    Returns:
        True если обновление успешно, False иначе
    """
    import time
    
    for attempt in range(max_retries):
        try:
            url = f"{settings.BITRIX_WEBHOOK_URL}/crm.deal.update"
            
            payload = {
                "id": deal_id,
                "fields": {
                    "UF_PAID_AMOUNT": amount
                }
            }
            
            res = requests.post(url, json=payload, timeout=10)
            res.raise_for_status()
            
            # Проверяем ответ от Bitrix24
            result = res.json()
            if result.get("result") is True:
                logger.info(
                    f"Успешно обновлена оплаченная сумма в Bitrix24 для сделки {deal_id}: {amount} "
                    f"(попытка {attempt + 1}/{max_retries})"
                )
                return True
            else:
                # Bitrix24 вернул ошибку в ответе
                error_msg = result.get("error", "Unknown error")
                logger.warning(
                    f"Bitrix24 вернул ошибку при обновлении сделки {deal_id}: {error_msg} "
                    f"(попытка {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Экспоненциальная задержка
                    continue
                return False
                
        except requests.Timeout as e:
            logger.warning(
                f"Timeout при обновлении Bitrix24 для сделки {deal_id} "
                f"(попытка {attempt + 1}/{max_retries}): {e}"
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            return False
            
        except requests.RequestException as e:
            logger.warning(
                f"Ошибка при обновлении оплаченной суммы в Bitrix24 для сделки {deal_id} "
                f"(попытка {attempt + 1}/{max_retries}): {e}"
            )
            # Если поле не существует, это нормально - данные хранятся в БД
            # Но для других ошибок пробуем повторить
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            return False
        except Exception as e:
            logger.error(
                f"Неожиданная ошибка при обновлении Bitrix24 для сделки {deal_id} "
                f"(попытка {attempt + 1}/{max_retries}): {e}",
                exc_info=True
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            return False
    
    logger.error(
        f"Не удалось обновить Bitrix24 для сделки {deal_id} после {max_retries} попыток"
    )
    return False
