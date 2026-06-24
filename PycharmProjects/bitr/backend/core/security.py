from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import re
import logging
from jose import jwt, JWTError
from core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)  # Не требует обязательного токена

class User:
    def __init__(self, identifier: str, identifier_type: str = "email", is_admin: bool = False):
        self.identifier = identifier  # Email или телефон
        self.identifier_type = identifier_type
        self.is_admin = bool(is_admin)
        # Для обратной совместимости
        self.email = identifier if identifier_type == "email" else None
        self.phone = identifier if identifier_type == "phone" else None

def _normalize_phone_for_compare(phone: str) -> str:
    if not phone or not isinstance(phone, str):
        return ""
    digits = "".join([c for c in phone if c.isdigit()])
    # сравниваем по последним 10 цифрам (без кода страны)
    return digits[-10:] if len(digits) >= 10 else digits

def _parse_admin_identifiers(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(",")]
    return [p for p in parts if p]

def is_admin_identifier(identifier: str, identifier_type: str) -> bool:
    admins = _parse_admin_identifiers(getattr(settings, "ADMIN_IDENTIFIERS", None))
    if not admins:
        return False
    if identifier_type == "phone":
        needle = _normalize_phone_for_compare(identifier)
        if not needle:
            return False
        for a in admins:
            if _normalize_phone_for_compare(a) == needle:
                return True
        return False
    # email/string compare (case-insensitive)
    needle = (identifier or "").strip().lower()
    for a in admins:
        if a.strip().lower() == needle:
            return True
    return False

def validate_email(email: str) -> bool:
    """
    Валидация email адреса.
    
    Args:
        email: Email адрес для проверки
    
    Returns:
        True если email валиден, False иначе
    """
    if not email or not isinstance(email, str):
        return False
    
    # Базовый паттерн для email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    # Проверяем длину (максимум 254 символа по RFC 5321)
    if len(email) > 254:
        return False
    
    # Проверяем паттерн
    if not re.match(pattern, email):
        return False
    
    # Проверяем, что не дефолтный тестовый email
    if email == "dev_user@example.com" or email == "admin@example.com":
        return False
    
    return True

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """
    Получает текущего пользователя из JWT токена.
    Проверяет, что пользователь существует в Bitrix24.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация. Отправьте токен в заголовке Authorization: Bearer <token>"
        )
    
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"]
        )
        identifier = payload.get("sub")
        identifier_type = payload.get("type", "email")  # По умолчанию email для обратной совместимости
        is_admin = bool(payload.get("is_admin")) or is_admin_identifier(identifier, identifier_type)
        
        if not identifier:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен: идентификатор не найден"
            )

        # Админ-токены не должны зависеть от наличия рассрочки в Bitrix24
        if is_admin:
            return User(identifier=identifier, identifier_type=identifier_type, is_admin=True)
        
        # Проверяем, что пользователь существует в Bitrix24 (есть сделка с рассрочкой)
        try:
            from bitrix.client import get_installment_deal, get_installment_deal_by_phone
            
            if identifier_type == "phone":
                deal = get_installment_deal_by_phone(identifier)
            else:
                deal = get_installment_deal(identifier)
            
            if not deal:
                identifier_display = f"телефон {identifier}" if identifier_type == "phone" else f"email {identifier}"
                logger.warning(f"Пользователь с {identifier_display} не найден в Bitrix24 или не имеет рассрочки")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Пользователь с {identifier_display} не найден в Bitrix24 или не имеет рассрочки. Обратитесь к администратору."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Ошибка при проверке пользователя в Bitrix24: {e}", exc_info=True)
            # В случае ошибки подключения к Bitrix24 - блокируем запрос для безопасности
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Сервис Bitrix24 временно недоступен. Попробуйте позже."
            )
        
        return User(identifier=identifier, identifier_type=identifier_type, is_admin=is_admin)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Неверный или истекший токен: {str(e)}"
        )


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав. Требуется админ-доступ."
        )
    return user

