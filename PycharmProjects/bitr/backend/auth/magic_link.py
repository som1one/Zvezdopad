from fastapi import APIRouter, HTTPException, status, Request
from typing import Optional
from jose import jwt, JWTError
from core.config import settings
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

def create_magic_token(identifier: str, identifier_type: str = "email"):
    """
    Создает JWT токен для magic link.
    Токен действителен 15 минут.
    
    Args:
        identifier: Email или телефон пользователя
        identifier_type: "email" или "phone"
    """
    # Определяем админа по конфигу (ADMIN_IDENTIFIERS)
    from core.security import is_admin_identifier
    payload = {
        "sub": identifier,
        "type": identifier_type,  # Сохраняем тип идентификатора
        "is_admin": is_admin_identifier(identifier, identifier_type),
        "exp": datetime.utcnow() + timedelta(minutes=15),
        "iat": datetime.utcnow()  # Время создания
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def create_admin_token(identifier: str, identifier_type: str = "phone"):
    """
    Создает JWT токен для админа (дольше живет, без проверки Bitrix).
    """
    payload = {
        "sub": identifier,
        "type": identifier_type,
        "is_admin": True,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


@router.post("/admin/login")
async def admin_login(request: Request):
    """
    Отдельный вход для админов по телефону + паролю из ENV.
    Body JSON: {"phone": "...", "password": "..."}
    """
    import re
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    phone = body.get("phone") if isinstance(body, dict) else None
    password = body.get("password") if isinstance(body, dict) else None

    if not phone or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите phone и password")

    if not settings.ADMIN_LOGIN_PHONE or not settings.ADMIN_LOGIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Админ-вход не настроен (ADMIN_LOGIN_PHONE/ADMIN_LOGIN_PASSWORD)"
        )

    normalized_phone = phone.replace(" ", "").replace("(", "").replace(")", "").replace("-", "").replace("+", "").strip()
    normalized_phone = f"+{normalized_phone}" if not normalized_phone.startswith("+") else normalized_phone
    # allow either +7... or 7...; compare by last 10 digits
    if not re.match(r'^\+?[0-9]{10,15}$', normalized_phone):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный телефон")

    def norm10(p: str) -> str:
        digits = "".join([c for c in (p or "") if c.isdigit()])
        return digits[-10:] if len(digits) >= 10 else digits

    if norm10(settings.ADMIN_LOGIN_PHONE) != norm10(normalized_phone):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный телефон или пароль")

    if password != settings.ADMIN_LOGIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный телефон или пароль")

    token = create_admin_token(identifier=normalized_phone, identifier_type="phone")
    return {"ok": True, "token": token}

@router.get("/verify")
def verify_token(token: str):
    """
    Проверяет токен и возвращает информацию о пользователе.
    Используется для проверки токена из magic link.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        identifier_type = payload.get("type", "email")
        return {
            "valid": True,
            "identifier": email,
            "identifier_type": identifier_type,
            "email": email if identifier_type == "email" else None,
            "phone": email if identifier_type == "phone" else None,
            "token": token  # Возвращаем тот же токен для использования
        }
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Неверный или истекший токен: {str(e)}"
        )

@router.post("/magic-link")
async def send_magic_link(request: Request):
    """
    Отправляет magic link для входа по телефону или email.
    
    Поддерживает:
    - Query параметры: ?phone=... или ?email=...
    - Body JSON: {"phone": "..."} или {"email": "..."}
    
    ВАЖНО: Проверяет, что пользователь существует в Bitrix24.
    """
    from bitrix.client import get_installment_deal, get_installment_deal_by_phone
    from fastapi import HTTPException, status
    import re
    
    # Получаем параметры из query
    phone = request.query_params.get("phone")
    email = request.query_params.get("email")
    
    # Если нет в query, пробуем получить из body
    if not phone and not email:
        try:
            body = await request.json()
            phone = body.get("phone") if isinstance(body, dict) else None
            email = body.get("email") if isinstance(body, dict) else None
        except:
            pass
    
    identifier = None
    identifier_type = None
    deal = None
    
    # Определяем, что введено: телефон или email
    print(f"DEBUG: phone={phone}, email={email}")
    logger.info(f"DEBUG: phone={phone}, email={email}")
    
    if phone:
        print(f"Получен телефон для входа: {phone}")
        logger.info(f"Получен телефон для входа: {phone}")
        # Нормализуем телефон (убираем все символы кроме цифр и плюса)
        normalized_phone = phone.replace(" ", "").replace("(", "").replace(")", "").replace("-", "").strip()
        print(f"Нормализованный телефон: {normalized_phone}")
        logger.info(f"Нормализованный телефон: {normalized_phone}")
        
        # Проверяем паттерн (должно быть 10-15 цифр, может начинаться с +)
        if re.match(r'^\+?[0-9]{10,15}$', normalized_phone):
            identifier = normalized_phone
            identifier_type = "phone"
            logger.info(f"Телефон прошел валидацию, ищем рассрочку для {identifier}")
            # Проверяем по телефону
            deal = get_installment_deal_by_phone(normalized_phone)
            logger.info(f"Результат поиска рассрочки по телефону {normalized_phone}: {'найдена' if deal else 'не найдена'}")
        else:
            logger.warning(f"Телефон {phone} (нормализованный: {normalized_phone}) не прошел валидацию regex")
    elif email:
        if '@' in email:
            identifier = email
            identifier_type = "email"
            # Проверяем по email
            deal = get_installment_deal(email)
    
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите телефон или email для входа. Используйте query параметр (?phone=... или ?email=...) или body JSON ({\"phone\": \"...\"} или {\"email\": \"...\"})"
        )
    
    if not deal:
        if identifier:
            identifier_display = f"телефон {phone}" if identifier_type == "phone" else f"email {email}"
            logger.warning(f"Рассрочка не найдена для {identifier_display} (identifier: {identifier})")
        else:
            identifier_display = phone or email or "неизвестный идентификатор"
            logger.warning(f"Не удалось определить тип идентификатора: {identifier_display}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с {identifier_display} не найден в Bitrix24 или не имеет рассрочки. Обратитесь к администратору."
        )
    
    token = create_magic_token(identifier, identifier_type)
    link = f"{settings.FRONTEND_URL}/auth/magic?token={token}"

    # TODO: Подключить отправку email/SMS
    # Сейчас просто логируем
    logger.info(f"Magic link для {identifier_type} {identifier}: {link}")
    print(f"MAGIC LINK для {identifier_type} {identifier}: {link}")

    identifier_display = phone if identifier_type == "phone" else email
    return {
        "ok": True,
        "message": f"Ссылка для входа отправлена на {identifier_display}",
        # В разработке возвращаем ссылку напрямую
        "link": link if settings.ENVIRONMENT == "development" else None
    }

