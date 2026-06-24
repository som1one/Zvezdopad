import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import requests

from core.config import settings

logger = logging.getLogger(__name__)

# ---- Generic parsing helpers ----

def parse_money_to_int(value: Any) -> int:
    """
    Converts Bitrix money-like values to integer RUB.
    Accepts: int/float/"3050000.00"/"3 050 000,00"/None/"".
    """
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        try:
            return int(float(value))
        except Exception:
            return 0
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0
        # remove spaces and normalize decimal separator
        s = s.replace(" ", "").replace("\u00a0", "").replace(",", ".")
        try:
            return int(float(s))
        except Exception:
            return 0
    return 0


def parse_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0
        # allow "6.0"
        s_norm = s.replace(",", ".")
        try:
            return int(float(s_norm))
        except Exception:
            return 0
    return 0


def parse_iso_date_to_ddmmyyyy(value: Any) -> str:
    """
    Converts Bitrix ISO date/time strings to DD.MM.YYYY.
    Accepts: '2025-09-23T03:00:00+03:00', '2025-09-23', etc.
    """
    if not value or isinstance(value, bool):
        return ""
    if not isinstance(value, str):
        return ""
    s = value.strip()
    if not s:
        return ""
    try:
        # normalize Z
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except Exception:
        # fallback: try first 10 chars YYYY-MM-DD
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
            return dt.strftime("%d.%m.%Y")
        except Exception:
            return s


def ensure_list(value: Any) -> List[Any]:
    if value is None or value is False:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ---- Bitrix enum resolving (cached) ----

_DEAL_FIELDS_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_DEAL_FIELDS_TTL_SECONDS = 10 * 60  # 10 minutes


def _fetch_deal_fields() -> Dict[str, Any]:
    url = f"{settings.BITRIX_WEBHOOK_URL}/crm.deal.fields"
    res = requests.get(url, timeout=20)
    res.raise_for_status()
    return res.json().get("result", {}) or {}


def get_deal_fields_cached() -> Dict[str, Any]:
    now = time.time()
    cached = _DEAL_FIELDS_CACHE.get("data")
    ts = float(_DEAL_FIELDS_CACHE.get("ts") or 0.0)
    if cached is not None and (now - ts) < _DEAL_FIELDS_TTL_SECONDS:
        return cached
    try:
        data = _fetch_deal_fields()
        _DEAL_FIELDS_CACHE["data"] = data
        _DEAL_FIELDS_CACHE["ts"] = now
        return data
    except Exception as e:
        logger.warning(f"Failed to fetch crm.deal.fields: {e}")
        # fallback to stale cache if we have one
        if cached is not None:
            return cached
        return {}


def get_enum_id_to_value_map(field_id: str) -> Dict[str, str]:
    fields = get_deal_fields_cached()
    field = fields.get(field_id) or {}
    items = field.get("items") or []
    mapping: Dict[str, str] = {}
    for item in items:
        try:
            k = str(item.get("ID"))
            v = str(item.get("VALUE"))
            if k and v and k != "None":
                mapping[k] = v
        except Exception:
            continue
    return mapping


def resolve_enum_values(field_id: str, raw_value: Any) -> str:
    """
    Resolves Bitrix enum field raw values to a human readable string.
    raw_value can be list of IDs, single ID, False, etc.
    """
    ids = [str(x) for x in ensure_list(raw_value) if x not in (None, "", False)]
    if not ids:
        return ""
    mapping = get_enum_id_to_value_map(field_id)
    if not mapping:
        # return IDs if mapping is unavailable
        return " ".join(ids)
    return " ".join([mapping.get(i, i) for i in ids])


# ---- Deal enrichment (project fields) ----

PROJECT_TYPE_FIELD = "UF_CRM_1759329251984"       # Тип проекта (enum)
PROJECT_START_DATE_FIELD = "UF_CRM_1759329496690"  # Дата начала проекта (date/datetime)
OBJECT_LOCATION_FIELD = "UF_CRM_1765399691"        # Где находится объект (string)


def enrich_project_fields_inplace(deal: Dict[str, Any]) -> None:
    """
    Adds normalized keys:
      - project_type (string)
      - project_start_date (DD.MM.YYYY)
      - object_location (string)
    Does not remove original UF_CRM_* fields.
    """
    try:
        if not isinstance(deal, dict):
            return
        deal["project_type"] = deal.get("project_type") or resolve_enum_values(PROJECT_TYPE_FIELD, deal.get(PROJECT_TYPE_FIELD))
        deal["project_start_date"] = deal.get("project_start_date") or parse_iso_date_to_ddmmyyyy(deal.get(PROJECT_START_DATE_FIELD))
        obj = deal.get("object_location") or deal.get(OBJECT_LOCATION_FIELD) or ""
        deal["object_location"] = str(obj) if obj is not None else ""
    except Exception as e:
        logger.debug(f"Failed to enrich project fields: {e}")


