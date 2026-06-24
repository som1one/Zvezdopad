from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.payment_log import get_db
from models.deal import Deal
from bitrix.client import get_installment_deal
from installments.service import normalize_deal
from core.security import get_current_user
import logging
from bitrix.parsing import parse_int, parse_money_to_int
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/installment", tags=["installment"])

@router.get("/my")
def my_installment(
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Получает данные о рассрочке для текущего пользователя.
    
    Логика поиска рассрочки:
    1. Сначала проверяем локальную БД по email (быстрее и надежнее)
    2. Если найдено в БД - используем deal_id для получения полных данных из Bitrix24
    3. Если не найдено в БД - ищем в Bitrix24 по email через контакт
    4. Если найдено в Bitrix24 - создаем запись в БД или обновляем существующую
    5. Объединяем данные из обоих источников (БД - источник истины для paid_amount и term_months)
    
    Преимущества:
    - БД работает быстрее для первичной проверки
    - БД содержит актуальные данные об оплате
    - Bitrix24 используется как источник дополнительной информации
    """
    user_identifier = user.email or user.phone or user.identifier
    logger.info(f"Запрос рассрочки для пользователя: {user_identifier} (тип: {user.identifier_type})")
    
    # 1. Сначала проверяем локальную БД (быстрее и надежнее для paid_amount)
    # Ищем по email если есть, иначе по deal_id через Bitrix24
    db_deal = None
    if user.email:
        db_deal = db.query(Deal).filter(Deal.email == user.email).first()
    elif user.identifier_type == "phone" and user.identifier:
        # При входе по телефону мы сохраняем идентификатор в поле email (исторически так называется)
        db_deal = db.query(Deal).filter(Deal.email == user.identifier).first()
    bitrix_deal = None
    
    if db_deal:
        logger.info(f"Найдена сделка в БД: {db_deal.deal_id} для {user_identifier}")
        # ВАЖНО: Получаем ПОЛНЫЕ данные из Bitrix24 по deal_id
        # Это необходимо для получения всех полей, включая пользовательские (UF_*)
        try:
            import bitrix.client as bitrix_client
            bitrix_deal = bitrix_client._get_full_deal(db_deal.deal_id)
            if bitrix_deal:
                logger.info(
                    f"Получены ПОЛНЫЕ данные из Bitrix24 для сделки {db_deal.deal_id}. "
                    f"Поля: {len(bitrix_deal.keys())} шт."
                )
            else:
                logger.warning(f"Не удалось получить полные данные из Bitrix24 для сделки {db_deal.deal_id}")
        except Exception as e:
            logger.warning(f"Ошибка при получении данных из Bitrix24 для сделки {db_deal.deal_id}: {e}")
            # Используем только данные из БД
            bitrix_deal = None
    
    # 2. Если не найдено в БД, ищем в Bitrix24
    if not db_deal:
        logger.info(f"Сделка не найдена в БД для {user_identifier}, ищем в Bitrix24")
        from bitrix.client import get_installment_deal_by_phone
        if user.identifier_type == "phone":
            bitrix_deal = get_installment_deal_by_phone(user.identifier)
        else:
            bitrix_deal = get_installment_deal(user.identifier)
    
    # 3. Если не найдено нигде - ошибка
    if not bitrix_deal and not db_deal:
        logger.warning(f"Рассрочка не найдена ни в Bitrix24, ни в БД для {user_identifier}")
        raise HTTPException(
            status_code=404,
            detail="Рассрочка не найдена. Обратитесь к администратору."
        )
    
    # 4. Обрабатываем данные
    if bitrix_deal:
        # Объединяем данные из Bitrix24 с данными из БД
        deal_id = bitrix_deal.get("ID")
        
        # Если db_deal еще не найден, ищем по deal_id
        if not db_deal:
            db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
        
        # ВАЖНО: Объединяем данные из Bitrix24 с данными из БД
        # БД - источник истины для paid_amount и term_months (обновляются при платежах)
        if db_deal:
            # Обновляем данные из Bitrix24 актуальными значениями из БД
            # paid_amount из БД - это источник истины, так как обновляется при каждом платеже
            bitrix_deal["UF_PAID_AMOUNT"] = str(db_deal.paid_amount)
            bitrix_deal["UF_TERM_MONTHS"] = str(db_deal.term_months)
            bitrix_deal["initial_payment"] = int(getattr(db_deal, "initial_payment", 0) or 0)

            # Фиксируем базовую дату графика (один раз), чтобы график не зависел от DATE_CREATE в Bitrix.
            # Если график уже настроен (term_months > 0), но schedule_start_date ещё не задан — ставим "сейчас".
            try:
                if (db_deal.term_months or 0) > 0 and getattr(db_deal, "schedule_start_date", None) is None:
                    db_deal.schedule_start_date = datetime.utcnow()
                    if getattr(db_deal, "schedule_day", None) in (None, 0):
                        db_deal.schedule_day = 10
                    db.commit()
                    db.refresh(db_deal)
            except Exception:
                db.rollback()

            bitrix_deal["SCHEDULE_START_DATE"] = (
                db_deal.schedule_start_date.isoformat() if getattr(db_deal, "schedule_start_date", None) else None
            )
            bitrix_deal["SCHEDULE_DAY"] = int(getattr(db_deal, "schedule_day", 10) or 10)
            bitrix_deal["EMAIL"] = db_deal.email  # Email из БД
            bitrix_deal["TITLE"] = db_deal.title  # Title из БД (может быть обновлен)
            
            # ВАЖНО: Если OPPORTUNITY в Bitrix24 = 0, используем total_amount из БД
            opportunity = bitrix_deal.get("OPPORTUNITY", "0")
            if isinstance(opportunity, str):
                opportunity = opportunity.replace(" ", "").replace(",", "")
            opportunity_float = float(opportunity) if opportunity else 0
            
            if opportunity_float == 0 and db_deal.total_amount > 0:
                bitrix_deal["OPPORTUNITY"] = str(db_deal.total_amount)
                logger.info(f"Используем total_amount из БД: {db_deal.total_amount} вместо OPPORTUNITY=0 для сделки {deal_id}")
            
            logger.info(
                f"Объединены данные: Bitrix24 (полные поля) + БД (paid_amount={db_deal.paid_amount}, "
                f"term_months={db_deal.term_months}, total_amount={bitrix_deal.get('OPPORTUNITY', 'N/A')}) для сделки {deal_id}"
            )
        else:
            # Если данных нет в БД, создаем запись с дефолтными значениями
            # Берём реальные значения из Bitrix24 (если пустые/0 — останутся 0)
            term_months = parse_int(bitrix_deal.get("UF_TERM_MONTHS"))
            paid_amount = parse_money_to_int(bitrix_deal.get("UF_PAID_AMOUNT"))
            
            # Получаем email из контакта Bitrix24, если есть
            user_email = user.email
            if not user_email and user.identifier_type == "phone":
                # Пытаемся получить email из контакта Bitrix24
                try:
                    contact_id = bitrix_deal.get("CONTACT_ID")
                    if contact_id:
                        import bitrix.client as bitrix_client
                        import requests
                        from core.config import settings
                        contact_res = requests.get(
                            f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.get",
                            params={"ID": contact_id},
                            timeout=10
                        )
                        if contact_res.status_code == 200:
                            contact = contact_res.json().get('result', {})
                            contact_email = contact.get('EMAIL')
                            if contact_email:
                                if isinstance(contact_email, list) and len(contact_email) > 0:
                                    if isinstance(contact_email[0], dict):
                                        user_email = contact_email[0].get('VALUE', '')
                                    else:
                                        user_email = str(contact_email[0])
                                elif isinstance(contact_email, str):
                                    user_email = contact_email
                except:
                    pass
            
            # Сумма из Bitrix24 (OPPORTUNITY). Если 0 — оставляем 0 (не выдумываем).
            total_from_bitrix = parse_money_to_int(bitrix_deal.get("OPPORTUNITY"))
            
            db_deal = Deal(
                deal_id=deal_id,
                title=bitrix_deal.get("TITLE", ""),
                email=user_email or user.identifier,  # Используем email или телефон как идентификатор
                total_amount=total_from_bitrix,
                paid_amount=paid_amount,
                initial_payment=0,
                term_months=term_months
            )
            db.add(db_deal)
            db.commit()
            db.refresh(db_deal)
            
            # Обновляем данные для нормализации
            bitrix_deal["UF_TERM_MONTHS"] = str(term_months)
            bitrix_deal["UF_PAID_AMOUNT"] = str(paid_amount)
        
        # Используем объединенные данные (Bitrix24 + БД)
        deal_data = bitrix_deal
    else:
        # Если есть только db_deal (Bitrix24 недоступен или данные не найдены)
        # Создаем минимальную структуру данных из БД
        logger.info(f"Используем только данные из БД для сделки {db_deal.deal_id} (Bitrix24 недоступен)")
        deal_data = {
            "ID": db_deal.deal_id,
            "TITLE": db_deal.title,
            "OPPORTUNITY": str(db_deal.total_amount),
            "UF_TERM_MONTHS": str(db_deal.term_months),
            "UF_PAID_AMOUNT": str(db_deal.paid_amount),
            "initial_payment": int(getattr(db_deal, "initial_payment", 0) or 0),
            "EMAIL": db_deal.email,
            # Дополнительные поля для совместимости
            "CONTACT_ID": None,
            "STAGE_ID": None,
            "DATE_CREATE": None,
            "DATE_MODIFY": None
        }
    
    # Нормализуем данные для фронтенда
    try:
        # Подтягиваем распределения оплат по месяцам (наличные + ЮKassa), чтобы график показывал paid/partial
        try:
            from models.cash_allocation import CashAllocation
            _deal_id_for_allocs = str(deal_data.get("ID") or (db_deal.deal_id if db_deal else ""))
            if _deal_id_for_allocs:
                alloc_rows = db.query(CashAllocation).filter(CashAllocation.deal_id == _deal_id_for_allocs).all()
                deal_data["CASH_ALLOCATIONS"] = [
                    {"month_index": a.month_index, "amount": a.amount, "payment_id": a.payment_id}
                    for a in alloc_rows
                ]
        except Exception as e:
            logger.debug(f"Could not load allocations for deal: {e}")

        normalized = normalize_deal(deal_data)

        # Прокидываем признак админа и ссылку на сделку в CRM (для админ-кнопки на фронте)
        try:
            deal_id_for_url = deal_data.get("ID") or normalized.get("deal", {}).get("contract_number")
            base = settings.BITRIX_WEBHOOK_URL.split("/rest/")[0].rstrip("/")
            crm_url = f"{base}/crm/deal/details/{deal_id_for_url}/" if deal_id_for_url else ""
        except Exception:
            crm_url = ""

        if isinstance(normalized, dict) and isinstance(normalized.get("deal"), dict):
            normalized["deal"]["is_admin"] = bool(getattr(user, "is_admin", False))
            normalized["deal"]["crm_deal_url"] = crm_url

        logger.info(f"Данные о рассрочке успешно получены для {user_identifier}, сделка {deal_data.get('ID')}")
        return normalized
    except ValueError as e:
        logger.error(f"Ошибка при нормализации данных сделки: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки данных рассрочки: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке рассрочки: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера при обработке данных рассрочки"
        )

