from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    BITRIX_WEBHOOK_URL: str
    YOOKASSA_SHOP_ID: str
    YOOKASSA_SECRET: str
    FRONTEND_URL: str
    YOOKASSA_WEBHOOK_URL: Optional[str] = None  # URL для webhook (если не указан, используется из настроек магазина)
    JWT_SECRET: str = "super-secret"
    
    # Production настройки
    ALLOWED_ORIGINS: Optional[str] = None  # Через запятую для нескольких доменов
    ENVIRONMENT: str = "development"  # development, production
    LOG_LEVEL: str = "INFO"
    # В development по умолчанию выключаем проверку подписи (иначе YooKassa webhooks будут отваливаться).
    # В production обязательно включить.
    VERIFY_WEBHOOK_SIGNATURE: bool = False  # Проверять подпись webhook (в продакшене обязательно)

    # Админ-доступ (список идентификаторов через запятую: email и/или телефон)
    # Примеры:
    # ADMIN_IDENTIFIERS=admin@example.com,+79991112233,79991112233
    ADMIN_IDENTIFIERS: Optional[str] = None

    # Отдельный вход для админов (телефон + пароль)
    ADMIN_LOGIN_PHONE: Optional[str] = None
    ADMIN_LOGIN_PASSWORD: Optional[str] = None
    
    # Telegram уведомления (опционально)
    TELEGRAM_BOT_TOKEN: Optional[str] = None  # Токен бота от @BotFather
    TELEGRAM_CHAT_ID: Optional[str] = None  # ID чата (можно получить у @userinfobot)
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

