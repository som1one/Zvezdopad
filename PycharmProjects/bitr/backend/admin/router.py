from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from models.payment_log import get_db, PaymentLog
from models.deal import Deal
from bitrix.client import get_all_installment_deals, get_installment_deal
from installments.service import normalize_deal
from payments.logger import log_payment
from core.security import require_admin
from bitrix.parsing import parse_int, parse_money_to_int
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

class CashPaymentAllocation(BaseModel):
    month_index: int
    amount: int

class CashPaymentRequest(BaseModel):
    # Для обратной совместимости (старый режим): сумма одним числом
    amount: Optional[int] = None
    deal_id: str
    # Новый режим: распределение по месяцам графика
    allocations: Optional[List[CashPaymentAllocation]] = None
    comment: Optional[str] = None
    idempotency_key: Optional[str] = None
    payment_date: Optional[str] = None  # дата оплаты в формате YYYY-MM-DD (если не указана, используется текущая дата)

class DealSettingsRequest(BaseModel):
    total_amount: Optional[int] = None
    term_months: Optional[int] = None
    initial_payment: Optional[int] = None
    email: Optional[str] = None
    title: Optional[str] = None

class DealResponse(BaseModel):
    deal_id: str
    title: str
    email: Optional[str]
    total_amount: int
    paid_amount: int
    remaining_amount: int
    term_months: int
    status: str  # "active", "paid", "overdue"

@router.get("/deals")
def get_all_deals(
    db: Session = Depends(get_db),
    user = Depends(require_admin)
):
    """
    Получает все рассрочки из Bitrix24 и локальной БД.
    Объединяет данные для отображения в админке.
    """
    logger.info(f"Admin {user.email} requested all deals")
    
    try:
        # Получаем все рассрочки из Bitrix24
        bitrix_deals = get_all_installment_deals()
        logger.info(f"Found {len(bitrix_deals)} deals in Bitrix24")
        
        # Получаем все сделки из локальной БД
        db_deals = db.query(Deal).all()
        db_deals_dict = {deal.deal_id: deal for deal in db_deals}
        logger.info(f"Found {len(db_deals)} deals in local DB")
        
        # Создаем словарь для быстрого поиска сделок из Bitrix24
        bitrix_deals_dict = {deal.get("ID"): deal for deal in bitrix_deals if deal.get("ID")}
        
        # Объединяем данные: сначала из Bitrix24, потом добавляем те, что есть только в БД
        result = []
        processed_deal_ids = set()
        
        # 1. Обрабатываем сделки из Bitrix24
        for bitrix_deal in bitrix_deals:
            deal_id = bitrix_deal.get("ID")
            db_deal = db_deals_dict.get(deal_id)
            
            # ВАЖНО: crm.deal.list может не отдавать UF_* поля (term/paid и т.д.).
            # Для отображения корректного срока/оплаты, когда сделки ещё нет в нашей БД,
            # подтягиваем полные данные через crm.deal.get.
            full_deal = None
            try:
                import bitrix.client as bitrix_client
                # Запрашиваем full_deal только если нет записи в БД (иначе источник истины — БД)
                if db_deal is None:
                    full_deal = bitrix_client._get_full_deal(deal_id)
            except Exception as e:
                logger.warning(f"Не удалось получить полные данные для сделки {deal_id}: {e}")
                full_deal = None

            # Получаем сумму из Bitrix24, проверяем разные варианты
            opportunity = bitrix_deal.get("OPPORTUNITY")
            if opportunity is None or opportunity == "" or opportunity == 0:
                # Если OPPORTUNITY пустое, пытаемся взять из full_deal
                if full_deal:
                    opportunity = full_deal.get("OPPORTUNITY", "0")
                    logger.debug(f"Получены полные данные для сделки {deal_id}, OPPORTUNITY: {opportunity}")
            
            # Используем данные из БД для paid_amount и term_months (источник истины)
            if db_deal:
                paid_amount = db_deal.paid_amount
                term_months = db_deal.term_months
                initial_payment = int(getattr(db_deal, "initial_payment", 0) or 0)
            else:
                # Если записи нет, берём реальные значения из Bitrix (через full_deal).
                # Это важно, иначе term_months будет 0 и фронт может скрывать сделки.
                paid_amount = parse_money_to_int((full_deal or {}).get("UF_PAID_AMOUNT"))
                term_months = parse_int((full_deal or {}).get("UF_TERM_MONTHS"))
                initial_payment = 0
            
            # Преобразуем сумму в число (ничего не выдумываем)
            # Если full_deal есть, он обычно точнее (OPPORTUNITY может быть строкой/пустым в list)
            if full_deal and full_deal.get("OPPORTUNITY") not in (None, "", 0):
                total_amount = parse_money_to_int(full_deal.get("OPPORTUNITY"))
            else:
                total_amount = parse_money_to_int(opportunity)
            
            # Определяем статус на основе процента оплаты
            if total_amount > 0 and paid_amount >= total_amount:
                deal_status = "paid"
            elif paid_amount > 0:
                deal_status = "active"
            elif total_amount > 0:
                deal_status = "pending"
            else:
                deal_status = "active"  # Если сумма неизвестна, считаем активной
            
            result.append({
                "deal_id": deal_id,
                "title": (bitrix_deal.get("TITLE") or (full_deal or {}).get("TITLE") or ""),
                "email": db_deal.email if db_deal else None,
                "total_amount": total_amount,
                "paid_amount": paid_amount,
                "initial_payment": initial_payment,
                "remaining_amount": max(0, total_amount - paid_amount),
                "term_months": term_months,
                "status": deal_status,
                # Дополнительные поля из Bitrix24
                "contact_id": bitrix_deal.get("CONTACT_ID"),
                "assigned_by_id": bitrix_deal.get("ASSIGNED_BY_ID"),
                "stage_id": bitrix_deal.get("STAGE_ID"),
                "date_create": bitrix_deal.get("DATE_CREATE"),
                "date_modify": bitrix_deal.get("DATE_MODIFY"),
                "begindate": bitrix_deal.get("BEGINDATE"),
                "closedate": bitrix_deal.get("CLOSEDATE"),
                "currency_id": bitrix_deal.get("CURRENCY_ID", "RUB"),
                "comments": bitrix_deal.get("COMMENTS"),
                "source_id": bitrix_deal.get("SOURCE_ID"),
                "company_id": bitrix_deal.get("COMPANY_ID"),
                "category_id": bitrix_deal.get("CATEGORY_ID")
            })
            processed_deal_ids.add(deal_id)
        
        # 2. Добавляем сделки из БД, которых нет в Bitrix24 (или которые не прошли фильтр)
        for db_deal in db_deals:
            deal_id = db_deal.deal_id
            if deal_id in processed_deal_ids:
                continue  # Уже обработана
            
            # Если сделки нет в Bitrix24, все равно показываем её из БД
            logger.info(f"Deal {deal_id} found in DB but not in Bitrix24 list, adding from DB")
            
            # Пытаемся получить данные из Bitrix24 напрямую (может быть, просто не прошла фильтр)
            full_deal = None
            try:
                import bitrix.client as bitrix_client
                full_deal = bitrix_client._get_full_deal(deal_id)
            except Exception as e:
                logger.debug(f"Could not fetch deal {deal_id} from Bitrix24: {e}")
                full_deal = None
            
            # Используем данные из БД как источник истины
            total_amount = db_deal.total_amount or 0
            paid_amount = db_deal.paid_amount or 0
            term_months = db_deal.term_months or 0
            initial_payment = int(getattr(db_deal, "initial_payment", 0) or 0)
            
            # Если в Bitrix24 есть данные, используем их для title и других полей
            title = db_deal.title or ""
            if full_deal:
                title = full_deal.get("TITLE") or title
            
            # Определяем статус
            if total_amount > 0 and paid_amount >= total_amount:
                deal_status = "paid"
            elif paid_amount > 0:
                deal_status = "active"
            elif total_amount > 0:
                deal_status = "pending"
            else:
                deal_status = "active"
            
            result.append({
                "deal_id": deal_id,
                "title": title,
                "email": db_deal.email,
                "total_amount": total_amount,
                "paid_amount": paid_amount,
                "initial_payment": initial_payment,
                "remaining_amount": max(0, total_amount - paid_amount),
                "term_months": term_months,
                "status": deal_status,
                # Дополнительные поля из Bitrix24 (если есть) или пустые
                "contact_id": full_deal.get("CONTACT_ID") if full_deal else None,
                "assigned_by_id": full_deal.get("ASSIGNED_BY_ID") if full_deal else None,
                "stage_id": full_deal.get("STAGE_ID") if full_deal else None,
                "date_create": full_deal.get("DATE_CREATE") if full_deal else None,
                "date_modify": full_deal.get("DATE_MODIFY") if full_deal else None,
                "begindate": full_deal.get("BEGINDATE") if full_deal else None,
                "closedate": full_deal.get("CLOSEDATE") if full_deal else None,
                "currency_id": full_deal.get("CURRENCY_ID", "RUB") if full_deal else "RUB",
                "comments": full_deal.get("COMMENTS") if full_deal else None,
                "source_id": full_deal.get("SOURCE_ID") if full_deal else None,
                "company_id": full_deal.get("COMPANY_ID") if full_deal else None,
                "category_id": full_deal.get("CATEGORY_ID") if full_deal else None
            })
        
        logger.info(f"Returning {len(result)} deals to admin ({len(bitrix_deals)} from Bitrix24, {len(db_deals)} from DB)")
        return result
        
    except Exception as e:
        logger.error(f"Error getting all deals: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении списка рассрочек: {str(e)}"
        )

@router.get("/bitrix/test")
def test_bitrix_data_endpoint(
    db: Session = Depends(get_db),
    user = Depends(require_admin)
):
    """
    Тестовый endpoint для просмотра всех данных из Bitrix24.
    Показывает все поля, которые приходят из Bitrix24.
    """
    logger.info(f"Admin {user.email} testing Bitrix24 data")
    
    try:
        from bitrix.client import get_all_installment_deals, _get_full_deal
        
        # Получаем список всех рассрочек
        all_deals = get_all_installment_deals()
        
        result = {
            "summary": {
                "total_deals": len(all_deals),
                "fields_in_list": []
            },
            "deals": []
        }
        
        if all_deals:
            # Показываем поля первой сделки из списка
            result["summary"]["fields_in_list"] = list(all_deals[0].keys())
            
            # Для каждой сделки получаем полные данные
            for deal_summary in all_deals:
                deal_id = deal_summary.get("ID")
                deal_info = {
                    "id": deal_id,
                    "summary_data": deal_summary
                }
                
                # Получаем полные данные
                try:
                    full_deal = _get_full_deal(deal_id)
                    if full_deal:
                        deal_info["full_data"] = full_deal
                        deal_info["full_data_fields"] = list(full_deal.keys())
                    else:
                        deal_info["full_data"] = None
                except Exception as e:
                    deal_info["full_data_error"] = str(e)
                
                # Данные из локальной БД
                db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
                if db_deal:
                    deal_info["local_db"] = {
                        "title": db_deal.title,
                        "email": db_deal.email,
                        "total_amount": db_deal.total_amount,
                        "paid_amount": db_deal.paid_amount,
                        "term_months": db_deal.term_months
                    }
                else:
                    deal_info["local_db"] = None
                
                result["deals"].append(deal_info)
        
        return result
        
    except Exception as e:
        logger.error(f"Error testing Bitrix24 data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении данных из Bitrix24: {str(e)}"
        )

@router.get("/deals/export")
def export_all_deals_endpoint(
    db: Session = Depends(get_db),
    user = Depends(require_admin)
):
    """
    Экспортирует все рассрочки с полной информацией, включая график платежей.
    """
    logger.info(f"Admin {user.email} exporting all deals")
    
    try:
        from installments.service import normalize_deal
        
        # Получаем все сделки из Bitrix24
        bitrix_deals = get_all_installment_deals()
        
        # Получаем все сделки из локальной БД
        db_deals = db.query(Deal).all()
        db_deals_dict = {deal.deal_id: deal for deal in db_deals}
        
        # Объединяем данные и нормализуем
        result = []
        for bitrix_deal in bitrix_deals:
            deal_id = bitrix_deal.get("ID")
            db_deal = db_deals_dict.get(deal_id)
            
            # Формируем данные для normalize_deal
            deal_data = bitrix_deal.copy()
            if db_deal:
                deal_data["UF_PAID_AMOUNT"] = str(db_deal.paid_amount)
                deal_data["UF_TERM_MONTHS"] = str(db_deal.term_months)
                deal_data["EMAIL"] = db_deal.email
                deal_data["TITLE"] = db_deal.title
            
            try:
                normalized = normalize_deal(deal_data)
                deal_info = normalized["deal"]
                payments = normalized["payments"]
                
                # Определяем статус
                total_amount = deal_info.get("total_amount", 0)
                paid_amount = deal_info.get("paid_amount", 0)
                
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
                    "title": deal_info.get("title", ""),
                    "email": deal_info.get("email"),
                    "total_amount": total_amount,
                    "paid_amount": paid_amount,
                    "remaining_amount": max(0, total_amount - paid_amount),
                    "term_months": deal_info.get("term_months", 0),
                    "paid_months": deal_info.get("paid_months", 0),
                    "status": status,
                    "payments_count": len(payments),
                    "payments": payments,
                    "date_create": bitrix_deal.get("DATE_CREATE"),
                    "stage_id": bitrix_deal.get("STAGE_ID"),
                    "contact_id": bitrix_deal.get("CONTACT_ID"),
                    "in_db": db_deal is not None
                })
            except Exception as e:
                logger.warning(f"Error normalizing deal {deal_id}: {e}")
                # Добавляем минимальную информацию даже при ошибке
                result.append({
                    "deal_id": deal_id,
                    "title": bitrix_deal.get("TITLE", ""),
                    "email": db_deal.email if db_deal else None,
                    "total_amount": 0,
                    "paid_amount": db_deal.paid_amount if db_deal else 0,
                    "remaining_amount": 0,
                    "term_months": db_deal.term_months if db_deal else 0,
                    "paid_months": 0,
                    "status": "error",
                    "payments_count": 0,
                    "payments": [],
                    "error": str(e),
                    "in_db": db_deal is not None
                })
        
        # Статистика
        stats = {
            "total_deals": len(result),
            "in_db": sum(1 for d in result if d['in_db']),
            "paid": sum(1 for d in result if d['status'] == 'paid'),
            "active": sum(1 for d in result if d['status'] == 'active'),
            "pending": sum(1 for d in result if d['status'] == 'pending'),
            "total_amount": sum(d['total_amount'] for d in result),
            "paid_amount": sum(d['paid_amount'] for d in result),
            "remaining_amount": sum(d['remaining_amount'] for d in result)
        }
        
        return {
            "stats": stats,
            "deals": result
        }
        
    except Exception as e:
        logger.error(f"Error exporting deals: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при экспорте данных: {str(e)}"
        )

@router.get("/deals/{deal_id}")
def get_deal_details(
    deal_id: str,
    db: Session = Depends(get_db),
    user = Depends(require_admin)
):
    """
    Получает детальную информацию о рассрочке для админки.
    """
    logger.info(f"Admin {user.email} requested deal {deal_id}")
    
    try:
        # Получаем данные из Bitrix24
        # Сначала пытаемся найти по deal_id
        bitrix_deal = None
        try:
            # Используем внутреннюю функцию через импорт
            import bitrix.client as bitrix_client
            bitrix_deal = bitrix_client._get_full_deal(deal_id)
        except Exception as e:
            logger.warning(f"Could not get deal from Bitrix24: {e}")
            pass
        
        # Если не нашли, ищем в локальной БД
        db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
        
        if not bitrix_deal and not db_deal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Рассрочка не найдена"
            )
        
        # Объединяем данные
        if bitrix_deal:
            deal_data = bitrix_deal.copy()
        else:
            # Создаем структуру из данных БД
            deal_data = {
                "ID": db_deal.deal_id,
                "TITLE": db_deal.title,
                "OPPORTUNITY": str(db_deal.total_amount),
                "UF_TERM_MONTHS": str(db_deal.term_months),
                "UF_PAID_AMOUNT": str(db_deal.paid_amount)
            }
        
        # Используем данные из БД как источник истины
        if db_deal:
            deal_data["UF_PAID_AMOUNT"] = str(db_deal.paid_amount)
            deal_data["UF_TERM_MONTHS"] = str(db_deal.term_months)
            deal_data["initial_payment"] = int(getattr(db_deal, "initial_payment", 0) or 0)
            # Фиксируем базовую дату графика (один раз), чтобы он не зависел от DATE_CREATE в Bitrix
            try:
                if (db_deal.term_months or 0) > 0 and getattr(db_deal, "schedule_start_date", None) is None:
                    db_deal.schedule_start_date = datetime.utcnow()
                    if getattr(db_deal, "schedule_day", None) in (None, 0):
                        db_deal.schedule_day = 10
                    db.commit()
                    db.refresh(db_deal)
            except Exception:
                db.rollback()

            deal_data["SCHEDULE_START_DATE"] = (
                db_deal.schedule_start_date.isoformat() if getattr(db_deal, "schedule_start_date", None) else None
            )
            deal_data["SCHEDULE_DAY"] = int(getattr(db_deal, "schedule_day", 10) or 10)
            # Добавляем email и title из БД, если их нет в Bitrix24
            if not deal_data.get("EMAIL") and db_deal.email:
                deal_data["EMAIL"] = db_deal.email
            if not deal_data.get("TITLE") and db_deal.title:
                deal_data["TITLE"] = db_deal.title
        
        # Подтягиваем распределения наличных платежей по месяцам (если есть)
        try:
            from models.cash_allocation import CashAllocation
            alloc_rows = db.query(CashAllocation).filter(CashAllocation.deal_id == str(deal_id)).all()
            deal_data["CASH_ALLOCATIONS"] = [
                {"month_index": a.month_index, "amount": a.amount, "payment_id": a.payment_id}
                for a in alloc_rows
            ]
        except Exception as e:
            logger.debug(f"Could not load cash allocations for deal {deal_id}: {e}")

        # Нормализуем для фронтенда
        normalized = normalize_deal(deal_data)
        
        # Добавляем email и title в нормализованные данные
        if db_deal:
            normalized["deal"]["email"] = db_deal.email
            normalized["deal"]["title"] = db_deal.title
        
        return normalized
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting deal {deal_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении данных о рассрочке: {str(e)}"
        )

@router.post("/deals/{deal_id}/cash-payment")
def record_cash_payment(
    deal_id: str,
    request: CashPaymentRequest,
    db: Session = Depends(get_db),
    user = Depends(require_admin)
):
    """
    Отмечает оплату наличными для рассрочки.
    Обновляет paid_amount в БД и создает запись в логах.
    """
    logger.info(f"Admin {user.email} recording cash payment for deal {deal_id}")

    # Собираем распределения и итоговую сумму
    allocations = request.allocations or []
    total_amount = 0
    if allocations:
        for a in allocations:
            if a.amount <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сумма по месяцу должна быть > 0")
            if a.month_index < 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный month_index")
            total_amount += a.amount
    else:
        if request.amount is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите либо amount, либо allocations")
        total_amount = int(request.amount)
    
    # Валидация суммы
    if total_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сумма должна быть больше 0"
        )
    
    # Проверка максимальной суммы платежа (защита от ошибок ввода)
    # Максимальная сумма - 10 миллионов рублей (разумный лимит)
    MAX_PAYMENT_AMOUNT = 10_000_000
    if total_amount > MAX_PAYMENT_AMOUNT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Сумма платежа ({total_amount} ₽) превышает максимально допустимую ({MAX_PAYMENT_AMOUNT} ₽). "
                   f"Проверьте правильность введенной суммы."
        )
    
    try:
        # Получаем сделку из БД с блокировкой строки для предотвращения race condition
        # Используем SELECT FOR UPDATE для блокировки строки до конца транзакции
        db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).with_for_update().first()
        
        if not db_deal:
            # Если сделки нет в БД, создаем её
            bitrix_deal = None
            try:
                import bitrix.client as bitrix_client
                bitrix_deal = bitrix_client._get_full_deal(deal_id)
            except Exception as e:
                logger.warning(f"Could not get deal from Bitrix24: {e}")
                pass
            
            if not bitrix_deal:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Рассрочка не найдена"
                )
            
            from bitrix.parsing import parse_money_to_int, parse_int

            # Создаем запись в БД. В поле email (исторически так называется) сохраняем идентификатор админа,
            # если нет лучшего идентификатора клиента.
            email_to_use = user.email or user.phone or user.identifier
            
            db_deal = Deal(
                deal_id=deal_id,
                title=bitrix_deal.get("TITLE", ""),
                email=email_to_use,
                total_amount=parse_money_to_int(bitrix_deal.get("OPPORTUNITY")),
                paid_amount=0,
                term_months=parse_int(bitrix_deal.get("UF_TERM_MONTHS"))
            )
            db.add(db_deal)
            db.flush()
            # После создания также блокируем строку
            db.refresh(db_deal)

        # Если общая сумма неизвестна — не позволяем фиксировать оплату (иначе будет неконсистентность)
        if db_deal.total_amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя записать оплату наличными: у сделки не задана общая сумма (total_amount=0). "
                       "Сначала укажите сумму в настройках сделки."
            )
        
        # Проверяем остаток (строка уже заблокирована)
        remaining = db_deal.total_amount - db_deal.paid_amount
        if total_amount > remaining:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Сумма платежа ({total_amount} ₽) превышает остаток по рассрочке ({remaining} ₽)"
            )
        
        if remaining <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Рассрочка уже полностью оплачена"
            )
        
        # Идемпотентность: если передан ключ — используем его как payment_id
        import uuid
        if request.idempotency_key:
            payment_id = f"cash_{request.idempotency_key}".strip()
            existing = db.query(PaymentLog).filter(PaymentLog.payment_id == payment_id).first()
            if existing:
                return {
                    "success": True,
                    "deal_id": deal_id,
                    "old_paid_amount": db_deal.paid_amount,
                    "new_paid_amount": db_deal.paid_amount,
                    "payment_amount": existing.amount,
                    "payment_id": existing.payment_id,
                    "idempotent": True
                }
        else:
            payment_id = f"cash_{uuid.uuid4().hex[:16]}"

        # Проверка на дублирование (fallback) — защита от двойного клика без ключа
        time_threshold = datetime.utcnow() - timedelta(seconds=30)
        recent_duplicate = db.query(PaymentLog).filter(
            and_(
                PaymentLog.deal_id == deal_id,
                PaymentLog.amount == total_amount,
                PaymentLog.source == "admin_cash",
                PaymentLog.created_at >= time_threshold
            )
        ).first()
        if recent_duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Похожий платеж на сумму {total_amount} ₽ был создан недавно. "
                       f"Если это не ошибка, повторите попытку через минуту."
            )
        
        # Обновляем paid_amount (суммируем)
        old_paid = db_deal.paid_amount
        new_paid = old_paid + total_amount
        
        # Проверяем, чтобы не превысило общую сумму
        if new_paid > db_deal.total_amount:
            new_paid = db_deal.total_amount
        
        db_deal.paid_amount = new_paid

        # Создаем запись в логах платежей в ТОМ ЖЕ транзакционном контексте
        # В комментарий добавляем краткое распределение по месяцам
        alloc_summary = None
        if allocations:
            alloc_summary = " | ".join([f"#{a.month_index+1}:{a.amount}" for a in allocations[:20]])
        final_comment = request.comment or ""
        if alloc_summary:
            combined = (alloc_summary + (f" | {final_comment}" if final_comment else ""))[:500]
        else:
            combined = (final_comment[:500] if final_comment else None)

        # Парсим дату оплаты, если указана
        payment_date = None
        if request.payment_date:
            try:
                payment_date = datetime.strptime(request.payment_date, "%Y-%m-%d")
            except ValueError:
                logger.warning(f"Invalid payment_date format: {request.payment_date}, using current date")
                payment_date = datetime.utcnow()
        
        log_entry = PaymentLog(
            deal_id=str(deal_id),
            payment_id=payment_id,
            amount=total_amount,
            status="paid",
            source="admin_cash",
            comment=combined,
            created_at=datetime.utcnow(),
            payment_date=payment_date or datetime.utcnow()
        )
        db.add(log_entry)

        # Сохраняем распределение по месяцам (если передано)
        if allocations:
            from models.cash_allocation import CashAllocation
            for a in allocations:
                db.add(CashAllocation(
                    deal_id=str(deal_id),
                    payment_id=payment_id,
                    month_index=a.month_index,
                    amount=a.amount
                ))

        db.commit()
        db.refresh(db_deal)
        db.refresh(log_entry)
        
        logger.info(f"Updated paid_amount: {old_paid} + {total_amount} = {new_paid} for deal {deal_id}")
        
        # Обновляем Bitrix24 (если поле существует)
        try:
            from bitrix.client import update_paid_amount
            update_paid_amount(deal_id, db_deal.paid_amount)
            logger.info(f"Updated Bitrix24 paid_amount: {db_deal.paid_amount}")
        except Exception as bitrix_error:
            logger.warning(f"Error updating Bitrix24: {bitrix_error}")
            # Не критично, если Bitrix недоступен
        
        # Отправляем уведомление в Telegram (не критично, если не получится)
        try:
            from notifications.telegram import send_telegram_notification, format_payment_notification
            try:
                # Безопасное получение данных
                deal_title = str(db_deal.title) if db_deal.title else None
                deal_email = str(db_deal.email) if db_deal.email else None
                
                notification_message = format_payment_notification(
                    deal_id=str(deal_id) if deal_id else "неизвестно",
                    amount=int(total_amount) if total_amount else 0,
                    payment_id=str(payment_id) if payment_id else "неизвестно",
                    source="admin_cash",
                    title=deal_title,
                    email=deal_email
                )
                send_telegram_notification(notification_message)
            except Exception as format_error:
                logger.warning(f"Failed to format Telegram notification: {format_error}", exc_info=True)
        except ImportError as import_error:
            logger.debug(f"Telegram notifications module not available: {import_error}")
        except Exception as e:
            logger.warning(f"Failed to send Telegram notification: {e}", exc_info=True)
            # Не прерываем обработку платежа из-за ошибки уведомления
        
        return {
            "success": True,
            "deal_id": deal_id,
            "old_paid_amount": old_paid,
            "new_paid_amount": new_paid,
            "payment_amount": total_amount,
            "payment_id": payment_id,
            "comment": log_entry.comment
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording cash payment: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при записи оплаты наличными: {str(e)}"
        )

@router.post("/database/clear")
def clear_database(
    user = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Очищает все таблицы базы данных и автоматически заполняет данными из Bitrix24.
    ОПАСНАЯ ОПЕРАЦИЯ! Использовать только для тестирования или полного сброса.
    """
    logger.warning(f"Admin {user.email} is clearing the database")
    
    try:
        from models.cash_allocation import CashAllocation
        from models.payment_log import PaymentLog
        
        # Очищаем таблицы в правильном порядке (сначала зависимые)
        deleted_allocations = db.query(CashAllocation).delete()
        deleted_logs = db.query(PaymentLog).delete()
        deleted_deals = db.query(Deal).delete()
        
        db.commit()
        
        logger.warning(f"Database cleared: {deleted_deals} deals, {deleted_logs} payment logs, {deleted_allocations} allocations")
        
        # Автоматически заполняем БД данными из Bitrix24
        logger.info("Начало автоматической синхронизации данных из Bitrix24...")
        sync_result = sync_bitrix_to_db(db)
        
        return {
            "success": True,
            "message": "База данных успешно очищена и заполнена данными из Bitrix24",
            "deleted": {
                "deals": deleted_deals,
                "payment_logs": deleted_logs,
                "cash_allocations": deleted_allocations
            },
            "synced": sync_result
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing database: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при очистке базы данных: {str(e)}"
        )


def sync_bitrix_to_db(db: Session) -> dict:
    """
    Синхронизирует данные из Bitrix24 в БД.
    Возвращает статистику синхронизации.
    """
    try:
        from bitrix.client import get_all_installment_deals, _get_full_deal
        from bitrix.parsing import parse_money_to_int, parse_int
        from core.config import settings
        import requests
        
        # Получаем все сделки с рассрочкой из Bitrix24
        bitrix_deals = get_all_installment_deals()
        logger.info(f"Найдено {len(bitrix_deals)} сделок с рассрочкой в Bitrix24")
        
        if not bitrix_deals:
            return {
                "success": True,
                "message": "Не найдено сделок с рассрочкой в Bitrix24",
                "synced_count": 0,
                "error_count": 0
            }
        
        success_count = 0
        error_count = 0
        
        for bitrix_deal in bitrix_deals:
            deal_id = bitrix_deal.get("ID")
            if not deal_id:
                error_count += 1
                continue
            
            try:
                # Получаем полные данные сделки
                full_deal = _get_full_deal(deal_id)
                if not full_deal:
                    error_count += 1
                    continue
                
                # Получаем email контакта
                contact_id = bitrix_deal.get("CONTACT_ID") or full_deal.get("CONTACT_ID")
                email = ""
                if contact_id:
                    try:
                        url = f"{settings.BITRIX_WEBHOOK_URL}/crm.contact.get"
                        params = {"ID": contact_id}
                        res = requests.get(url, params=params, timeout=10)
                        if res.status_code == 200:
                            contact = res.json().get("result", {})
                            email_val = contact.get("EMAIL")
                            if isinstance(email_val, list) and email_val:
                                first = email_val[0]
                                email = first.get("VALUE", "") if isinstance(first, dict) else str(first)
                            elif isinstance(email_val, str):
                                email = email_val
                    except Exception:
                        pass
                
                # Парсим данные
                title = full_deal.get("TITLE") or bitrix_deal.get("TITLE") or ""
                total_amount = parse_money_to_int(full_deal.get("OPPORTUNITY"))
                paid_amount = parse_money_to_int(full_deal.get("UF_PAID_AMOUNT"))
                term_months = parse_int(full_deal.get("UF_TERM_MONTHS"))
                initial_payment = parse_money_to_int(full_deal.get("UF_INITIAL_PAYMENT")) or 0
                
                # Создаем запись в БД
                db_deal = Deal(
                    deal_id=str(deal_id),
                    title=title,
                    email=email,
                    total_amount=total_amount,
                    paid_amount=paid_amount,
                    initial_payment=initial_payment,
                    term_months=term_months,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(db_deal)
                success_count += 1
                
            except Exception as e:
                logger.error(f"Ошибка при синхронизации сделки {deal_id}: {e}")
                error_count += 1
        
        db.commit()
        
        logger.info(f"Синхронизация завершена: успешно {success_count}, ошибок {error_count}")
        
        return {
            "success": True,
            "message": f"Синхронизировано {success_count} сделок из Bitrix24",
            "synced_count": success_count,
            "error_count": error_count,
            "total_found": len(bitrix_deals)
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при синхронизации из Bitrix24: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Ошибка при синхронизации: {str(e)}",
            "synced_count": 0,
            "error_count": 0
        }

@router.post("/telegram/test")
def test_telegram_notification(
    user = Depends(require_admin)
):
    """
    Тестовый endpoint для проверки Telegram уведомлений
    """
    try:
        from notifications.telegram import send_telegram_notification, format_payment_notification
        from core.config import settings
        
        # Проверяем настройки
        telegram_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        telegram_chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)
        
        if not telegram_token or not telegram_chat_id:
            return {
                "success": False,
                "error": "Telegram не настроен",
                "details": {
                    "token_set": bool(telegram_token),
                    "chat_id_set": bool(telegram_chat_id)
                }
            }
        
        # Отправляем тестовое сообщение
        test_message = format_payment_notification(
            deal_id="TEST",
            amount=10000,  # 100 рублей
            payment_id="test-payment-123",
            source="yookassa",
            title="Тестовая сделка",
            email="test@example.com"
        )
        
        result = send_telegram_notification(test_message)
        
        if result:
            return {
                "success": True,
                "message": "Тестовое уведомление отправлено успешно"
            }
        else:
            return {
                "success": False,
                "error": "Не удалось отправить уведомление (проверьте логи backend)"
            }
            
    except ImportError as e:
        return {
            "success": False,
            "error": f"Ошибка импорта: {e}"
        }
    except Exception as e:
        logger.error(f"Ошибка при тестировании Telegram: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }

@router.put("/deals/{deal_id}/settings")
def update_deal_settings(
    deal_id: str,
    request: DealSettingsRequest,
    db: Session = Depends(get_db),
    user = Depends(require_admin)
):
    """
    Обновляет настройки рассрочки (срок, сумма, email, название).
    """
    logger.info(f"Admin {user.email} updating settings for deal {deal_id}")
    
    try:
        # Получаем сделку из БД (если нет — создаём из Bitrix24, чтобы настройки можно было сохранять)
        db_deal = db.query(Deal).filter(Deal.deal_id == deal_id).first()
        if not db_deal:
            bitrix_deal = None
            try:
                import bitrix.client as bitrix_client
                bitrix_deal = bitrix_client._get_full_deal(deal_id)
            except Exception as e:
                logger.warning(f"Could not get deal {deal_id} from Bitrix24 to create local record: {e}")

            if not bitrix_deal:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Рассрочка не найдена"
                )

            db_deal = Deal(
                deal_id=str(deal_id),
                title=str(bitrix_deal.get("TITLE") or ""),
                email=(request.email or None),
                total_amount=parse_money_to_int(bitrix_deal.get("OPPORTUNITY")),
                paid_amount=parse_money_to_int(bitrix_deal.get("UF_PAID_AMOUNT")),
                initial_payment=0,
                term_months=parse_int(bitrix_deal.get("UF_TERM_MONTHS")),
            )
            db.add(db_deal)
            db.commit()
            db.refresh(db_deal)
        
        # Обновляем поля, если они указаны
        updated_fields = []
        prev_term_months = int(getattr(db_deal, "term_months", 0) or 0) if db_deal else 0
        
        if request.total_amount is not None:
            if request.total_amount < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Общая сумма не может быть отрицательной"
                )
            # Не позволяем уменьшать общую сумму меньше чем уже оплачено
            if request.total_amount < db_deal.paid_amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Общая сумма ({request.total_amount} ₽) не может быть меньше уже оплаченной суммы ({db_deal.paid_amount} ₽)"
                )
            db_deal.total_amount = request.total_amount
            updated_fields.append(f"total_amount={request.total_amount}")
        
        if request.term_months is not None:
            if request.term_months < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Срок не может быть отрицательным"
                )
            if request.term_months > 120:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Срок не может превышать 120 месяцев"
                )
            db_deal.term_months = request.term_months
            updated_fields.append(f"term_months={request.term_months}")
            # Если график создаётся впервые (term 0 -> >0) или база графика ещё не фиксировалась — фиксируем сейчас.
            try:
                if request.term_months > 0 and (
                    prev_term_months <= 0 or getattr(db_deal, "schedule_start_date", None) is None
                ):
                    if getattr(db_deal, "schedule_start_date", None) is None:
                        db_deal.schedule_start_date = datetime.utcnow()
                    if getattr(db_deal, "schedule_day", None) in (None, 0):
                        db_deal.schedule_day = 10
                    updated_fields.append("schedule_start_date=now")
                # Если срок сбрасывается в 0, очищаем schedule_start_date и schedule_day
                elif request.term_months == 0:
                    if hasattr(db_deal, "schedule_start_date"):
                        db_deal.schedule_start_date = None
                    if hasattr(db_deal, "schedule_day"):
                        db_deal.schedule_day = None
            except Exception:
                pass

        # Первоначальный взнос: параметр расчёта графика (installment_amount = total_amount - initial_payment).
        # ВАЖНО: initial_payment НЕ является фактом оплаты и НЕ должен менять paid_amount автоматически.
        if request.initial_payment is not None:
            if request.initial_payment < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Первоначальный взнос не может быть отрицательным"
                )
            # Если задана общая сумма (или уже есть в БД) — не даём ставить взнос больше total
            total_for_check = request.total_amount if request.total_amount is not None else (db_deal.total_amount or 0)
            if total_for_check > 0 and request.initial_payment > total_for_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Первоначальный взнос ({request.initial_payment} ₽) не может быть больше общей суммы ({total_for_check} ₽)"
                )

            new_initial = int(request.initial_payment)
            db_deal.initial_payment = new_initial
            updated_fields.append(f"initial_payment={new_initial}")
        
        if request.email is not None:
            from core.security import validate_email
            if request.email and not validate_email(request.email):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Некорректный email адрес"
                )
            db_deal.email = request.email or None
            updated_fields.append(f"email={request.email}")
        
        if request.title is not None:
            db_deal.title = request.title or ""
            updated_fields.append(f"title={request.title}")
        
        if not updated_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не указаны поля для обновления"
            )
        
        db.commit()
        db.refresh(db_deal)
        
        logger.info(f"Successfully updated deal {deal_id} settings: {', '.join(updated_fields)}")
        
        # Обновляем Bitrix24 (если поля существуют)
        try:
            from bitrix.client import update_paid_amount
            # Обновляем только paid_amount в Bitrix24, если оно изменилось
            update_paid_amount(deal_id, db_deal.paid_amount)
        except Exception as bitrix_error:
            logger.warning(f"Error updating Bitrix24: {bitrix_error}")
            # Не критично, если Bitrix недоступен
        
        return {
            "success": True,
            "deal_id": deal_id,
            "updated_fields": updated_fields,
            "deal": {
                "deal_id": db_deal.deal_id,
                "title": db_deal.title,
                "email": db_deal.email,
                "total_amount": db_deal.total_amount,
                "paid_amount": db_deal.paid_amount,
                "initial_payment": getattr(db_deal, "initial_payment", 0) or 0,
                "term_months": db_deal.term_months
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating deal settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при обновлении настроек рассрочки: {str(e)}"
        )


@router.get("/yookassa/check")
def check_yookassa(
    user=Depends(require_admin),
):
    """
    Быстрая проверка, что ключи ЮKassa корректные (GET /v3/me).
    Возвращает только маску секретного ключа.
    """
    import os
    import requests

    shop_id = os.getenv("YOOKASSA_SHOP_ID", "") or ""
    secret = os.getenv("YOOKASSA_SECRET", "") or ""

    def mask(s: str) -> str:
        if not s:
            return ""
        if len(s) <= 8:
            return s[:2] + "…" + s[-2:]
        return s[:4] + "…" + s[-4:]

    try:
        sess = requests.Session()
        sess.auth = (shop_id, secret)
        resp = sess.get("https://api.yookassa.ru/v3/me", timeout=20)
        # тело может быть большим/содержать лишнее — вернём первые 300 символов
        body = (resp.text or "")[:300]
        ok = resp.status_code == 200
        return {
            "ok": ok,
            "status_code": resp.status_code,
            "shop_id": shop_id,
            "secret_mask": mask(secret),
            "body_preview": body,
        }
    except Exception as e:
        return {
            "ok": False,
            "status_code": None,
            "shop_id": shop_id,
            "secret_mask": mask(secret),
            "error": str(e),
        }

