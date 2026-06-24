from datetime import datetime
from calendar import monthrange
import logging

logger = logging.getLogger(__name__)

def _parse_iso_dt(value) -> datetime | None:
    if not value or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def normalize_deal(deal):
    """
    Нормализует данные сделки для фронтенда.
    Обрабатывает ошибки и НЕ подставляет выдуманные суммы/сроки.
    Если сумма или срок не заданы — возвращает пустой график платежей и
    выставляет total_amount/term_months как 0.
    """
    try:
        # Единый парсинг значений Bitrix (устойчиво к строкам/числам/пустым)
        from bitrix.parsing import parse_money_to_int, parse_int, parse_iso_date_to_ddmmyyyy, resolve_enum_values

        total = parse_money_to_int(deal.get("OPPORTUNITY"))
        paid = parse_money_to_int(deal.get("UF_PAID_AMOUNT"))
        term = parse_int(deal.get("UF_TERM_MONTHS"))
        initial_payment = parse_money_to_int(deal.get("initial_payment"))
        if initial_payment < 0:
            initial_payment = 0
        if total > 0 and initial_payment > total:
            initial_payment = total

        # Сумма рассрочки для графика = общая сумма сделки - первоначальный взнос
        installment_total = max(0, total - initial_payment)
        # ВАЖНО: initial_payment — параметр расчёта графика (уменьшает сумму рассрочки),
        # но НЕ является фактом оплаты. Поэтому прогресс по графику считаем от paid_amount.
        paid_for_schedule = max(0, min(paid, installment_total))
        
        # Валидация данных
        total_missing = total <= 0
        term_missing = term <= 0
        
        if paid < 0:
            logger.warning(f"Оплаченная сумма < 0: {paid}. Устанавливается 0")
            paid = 0
        
        if total > 0 and paid > total:
            logger.warning(f"Оплаченная сумма ({paid}) больше общей ({total}). Устанавливается {total}")
            paid = total

        # Проектные поля: берём уже нормализованные из bitrix.client (если есть),
        # иначе считаем напрямую (через crm.deal.fields с кешом в bitrix.parsing)
        project_type = deal.get("project_type") or resolve_enum_values("UF_CRM_1759329251984", deal.get("UF_CRM_1759329251984"))
        project_start_date = deal.get("project_start_date") or parse_iso_date_to_ddmmyyyy(deal.get("UF_CRM_1759329496690"))
        object_location = deal.get("object_location") or (str(deal.get("UF_CRM_1765399691") or "") if deal.get("UF_CRM_1765399691") is not None else "")

        # Распределения оплат по месяцам (наличные + ЮKassa) из БД
        cash_allocations = deal.get("CASH_ALLOCATIONS") or []
        paid_by_month_index = {}
        try:
            for a in cash_allocations:
                idx = int(a.get("month_index"))
                amt = parse_money_to_int(a.get("amount"))
                if idx >= 0 and amt > 0:
                    paid_by_month_index[idx] = paid_by_month_index.get(idx, 0) + amt
        except Exception:
            paid_by_month_index = {}

        # Если не задана сумма или срок — нельзя корректно построить график
        if total_missing or term_missing:
            missing_fields = []
            if total_missing:
                missing_fields.append("total_amount")
            if term_missing:
                missing_fields.append("term_months")

            return {
                "deal": {
                    "contract_number": deal.get("ID", "UNKNOWN"),
                    "total_amount": total if total > 0 else 0,
                    "paid_amount": paid,
                    "initial_payment": initial_payment,
                    "installment_amount": installment_total,
                    "term_months": term if term > 0 else 0,
                    "paid_months": 0,
                    "email": deal.get("EMAIL") or deal.get("email"),
                    "title": deal.get("TITLE") or deal.get("title"),
                    "client_name": deal.get("CONTACT_NAME") or "",
                    "client_phone": deal.get("CONTACT_PHONE") or deal.get("client_phone") or "",
                    "missing_fields": missing_fields,
                    # Новые поля
                    "project_type": project_type,
                    "project_start_date": project_start_date,
                    "object_location": object_location,
                    # Дополнительные поля из Bitrix24
                    "contact_id": deal.get("CONTACT_ID"),
                    "assigned_by_id": deal.get("ASSIGNED_BY_ID"),
                    "stage_id": deal.get("STAGE_ID"),
                    "stage_name": deal.get("STAGE_NAME"),
                    "date_create": deal.get("DATE_CREATE"),
                    "date_modify": deal.get("DATE_MODIFY"),
                    "begindate": deal.get("BEGINDATE"),
                    "closedate": deal.get("CLOSEDATE"),
                    "currency_id": deal.get("CURRENCY_ID", "RUB"),
                    "comments": deal.get("COMMENTS"),
                    "source_id": deal.get("SOURCE_ID"),
                    "source_name": deal.get("SOURCE_NAME"),
                    "company_id": deal.get("COMPANY_ID"),
                    "company_name": deal.get("COMPANY_TITLE"),
                    "category_id": deal.get("CATEGORY_ID")
                },
                "payments": []
            }

        # Если рассрочка по сумме = 0 (всё закрыто первоначальным взносом), график не нужен
        if installment_total <= 0:
            paid_months_count = 0
            return {
                "deal": {
                    "contract_number": deal.get("ID", "UNKNOWN"),
                    "total_amount": total,
                    "paid_amount": paid,
                    "initial_payment": initial_payment,
                    "installment_amount": installment_total,
                    "term_months": term,
                    "paid_months": paid_months_count,
                    "email": deal.get("EMAIL") or deal.get("email"),
                    "title": deal.get("TITLE") or deal.get("title"),
                    "client_name": deal.get("CONTACT_NAME") or "",
                    "client_phone": deal.get("CONTACT_PHONE") or deal.get("client_phone") or "",
                    "missing_fields": [],
                    "project_type": project_type,
                    "project_start_date": project_start_date,
                    "object_location": object_location,
                    "contact_id": deal.get("CONTACT_ID"),
                    "assigned_by_id": deal.get("ASSIGNED_BY_ID"),
                    "stage_id": deal.get("STAGE_ID"),
                    "stage_name": deal.get("STAGE_NAME"),
                    "date_create": deal.get("DATE_CREATE"),
                    "date_modify": deal.get("DATE_MODIFY"),
                    "begindate": deal.get("BEGINDATE"),
                    "closedate": deal.get("CLOSEDATE"),
                    "currency_id": deal.get("CURRENCY_ID", "RUB"),
                    "comments": deal.get("COMMENTS"),
                    "source_id": deal.get("SOURCE_ID"),
                    "source_name": deal.get("SOURCE_NAME"),
                    "company_id": deal.get("COMPANY_ID"),
                    "company_name": deal.get("COMPANY_TITLE"),
                    "category_id": deal.get("CATEGORY_ID")
                },
                "payments": []
            }

        monthly = installment_total // term
        remainder = installment_total % term  # Остаток для последнего платежа

        # Начальная дата графика:
        # 1) если есть schedule_start_date (фиксируется при настройке графика в нашей БД) — используем её
        # 2) иначе fallback на даты сделки из Bitrix
        # 3) иначе на текущее время
        schedule_day = parse_int(deal.get("schedule_day") or deal.get("SCHEDULE_DAY")) or 10
        # ограничим до разумного диапазона, чтобы не упасть на 0/31 в феврале
        if schedule_day < 1:
            schedule_day = 1
        if schedule_day > 28:
            # 29-31 будем обрабатывать через clamp к последнему дню месяца ниже, но базовый "порог" оставим
            schedule_day = min(schedule_day, 31)

        base_dt = (
            _parse_iso_dt(deal.get("schedule_start_date") or deal.get("SCHEDULE_START_DATE"))
            or _parse_iso_dt(deal.get("BEGINDATE") or deal.get("DATE_CREATE") or deal.get("DATE_MODIFY"))
            or datetime.now()
        )

        # Первый платёж — в ближайший schedule_day:
        # если базовая дата до дня платежа — в этом месяце, иначе — в следующем.
        if base_dt.day < schedule_day:
            start_year, start_month = base_dt.year, base_dt.month
        else:
            if base_dt.month == 12:
                start_year, start_month = base_dt.year + 1, 1
            else:
                start_year, start_month = base_dt.year, base_dt.month + 1
        # clamp day to month length
        last_day = monthrange(start_year, start_month)[1]
        start_date = datetime(start_year, start_month, min(schedule_day, last_day))

        payments = []
        cumulative_scheduled = 0  # Накопленная сумма по графику
        
        # Названия месяцев на русском
        month_names = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        # Если есть аллокации, но paid_amount (минус initial) больше суммы аллокаций,
        # достраиваем "виртуальную" часть (legacy/ручные правки) последовательно по месяцам.
        alloc_sum = sum(int(v) for v in paid_by_month_index.values()) if paid_by_month_index else 0
        extra_paid_to_allocate = max(0, paid_for_schedule - alloc_sum)

        remaining_paid_seq = paid_for_schedule  # fallback последовательное распределение

        for i in range(term):
            # Дата платежа - schedule_day каждого месяца (с клэмпом по длине месяца)
            year = start_date.year
            month = start_date.month + i
            while month > 12:
                month -= 12
                year += 1
            last_day = monthrange(year, month)[1]
            payment_date = datetime(year, month, min(start_date.day, last_day))
            
            # Сумма платежа (последний платеж включает остаток)
            amount = monthly + (remainder if i == term - 1 else 0)

            # Статусы по месяцам:
            # - если есть распределения по месяцам — используем их + докидываем недостающую часть по paid_for_schedule
            # - иначе делаем корректный fallback: распределяем paid_for_schedule последовательно, включая partial
            if paid_by_month_index:
                base_paid = int(paid_by_month_index.get(i, 0) or 0)
                # докидываем "лишнее paid" (если в БД нет аллокаций на всю сумму)
                extra = 0
                if extra_paid_to_allocate > 0 and base_paid < amount:
                    extra = min(amount - base_paid, extra_paid_to_allocate)
                    extra_paid_to_allocate -= extra
                paid_in_month = base_paid + extra
            else:
                paid_in_month = min(int(amount), int(remaining_paid_seq))
                remaining_paid_seq -= paid_in_month

            remaining_in_month = max(0, amount - paid_in_month)
            if remaining_in_month <= 0:
                status = "paid"
            elif paid_in_month > 0:
                status = "partial"
            else:
                status = "pending"

            cumulative_scheduled += amount
            
            month_name = month_names[payment_date.month - 1]
            
            payments.append({
                "index": i,
                "month": f"{month_name} {payment_date.year}",
                "date": payment_date.strftime("%d.%m.%Y"),
                "amount": amount,
                "status": status,
                "paid_in_month": paid_in_month,
                "remaining_in_month": remaining_in_month
            })
        
        # Рассчитываем количество оплаченных месяцев
        paid_months_count = sum(1 for p in payments if p["status"] == "paid")

        return {
            "deal": {
                "contract_number": deal.get("ID", "UNKNOWN"),
                "total_amount": total,
                "paid_amount": paid,
                "initial_payment": initial_payment,
                "installment_amount": installment_total,
                "term_months": term,
                "paid_months": paid_months_count,
                "email": deal.get("EMAIL") or deal.get("email"),
                "title": deal.get("TITLE") or deal.get("title"),
                "client_name": deal.get("CONTACT_NAME") or "",
                "client_phone": deal.get("CONTACT_PHONE") or deal.get("client_phone") or "",
                "missing_fields": [],
                # Новые поля для отображения
                "project_type": project_type,
                "project_start_date": project_start_date,
                "object_location": object_location,
                # Дополнительные поля из Bitrix24
                "contact_id": deal.get("CONTACT_ID"),
                "assigned_by_id": deal.get("ASSIGNED_BY_ID"),
                "stage_id": deal.get("STAGE_ID"),
                "stage_name": deal.get("STAGE_NAME"),
                "date_create": deal.get("DATE_CREATE"),
                "date_modify": deal.get("DATE_MODIFY"),
                "begindate": deal.get("BEGINDATE"),
                "closedate": deal.get("CLOSEDATE"),
                "currency_id": deal.get("CURRENCY_ID", "RUB"),
                "comments": deal.get("COMMENTS"),
                "source_id": deal.get("SOURCE_ID"),
                "source_name": deal.get("SOURCE_NAME"),
                "company_id": deal.get("COMPANY_ID"),
                "company_name": deal.get("COMPANY_TITLE"),
                "category_id": deal.get("CATEGORY_ID")
            },
            "payments": payments
        }
    except KeyError as e:
        logger.error(f"Отсутствует обязательное поле в данных сделки: {e}")
        raise ValueError(f"Неполные данные сделки: отсутствует поле {e}")
    except (ValueError, TypeError) as e:
        logger.error(f"Ошибка при обработке данных сделки: {e}. Данные: {deal}")
        raise ValueError(f"Некорректные данные сделки: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при нормализации сделки: {e}", exc_info=True)
        raise
