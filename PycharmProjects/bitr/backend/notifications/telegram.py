import logging
import requests
from typing import Optional
import traceback

logger = logging.getLogger(__name__)

def _get_telegram_settings():
    """Безопасное получение настроек Telegram"""
    try:
        from core.config import settings
        telegram_token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        telegram_chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)
        return telegram_token, telegram_chat_id
    except Exception as e:
        logger.warning(f"Ошибка при получении настроек Telegram: {e}", exc_info=True)
        return None, None

def send_telegram_notification(message: str, chat_id: Optional[str] = None) -> bool:
    """
    Отправка уведомления в Telegram
    
    Args:
        message: Текст сообщения
        chat_id: ID чата (если не указан, используется из настроек)
    
    Returns:
        True если отправка успешна, False в противном случае
    """
    try:
        # Валидация входных данных
        if not message or not isinstance(message, str):
            logger.warning("Telegram: пустое или некорректное сообщение")
            return False
        
        if len(message.strip()) == 0:
            logger.warning("Telegram: сообщение пустое после trim")
            return False
        
        # Получаем настройки
        telegram_token, default_chat_id = _get_telegram_settings()
        telegram_chat_id = chat_id or default_chat_id
        
        if not telegram_token or not telegram_chat_id:
            logger.warning(f"Telegram уведомления не настроены: token={'установлен' if telegram_token else 'НЕ установлен'}, chat_id={'установлен' if telegram_chat_id else 'НЕ установлен'}")
            return False
        
        logger.info(f"Telegram: попытка отправки уведомления в chat {telegram_chat_id}")
        
        # Валидация токена и chat_id
        if not isinstance(telegram_token, str) or len(telegram_token.strip()) == 0:
            logger.warning("Telegram: некорректный токен")
            return False
        
        if not isinstance(telegram_chat_id, str) and not isinstance(telegram_chat_id, int):
            logger.warning(f"Telegram: некорректный chat_id (тип: {type(telegram_chat_id)})")
            return False
        
        # Формируем URL и payload
        try:
            url = f"https://api.telegram.org/bot{telegram_token.strip()}/sendMessage"
            payload = {
                "chat_id": str(telegram_chat_id).strip(),
                "text": message,
                "parse_mode": "HTML"
            }
        except Exception as e:
            logger.error(f"Telegram: ошибка при формировании запроса: {e}")
            return False
        
        # Отправляем запрос
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            if result.get("ok"):
                logger.info(f"Telegram уведомление отправлено успешно в chat {telegram_chat_id}")
                return True
            else:
                error_description = result.get("description", "Unknown error")
                logger.error(f"Telegram API вернул ошибку: {error_description}")
                return False
                
        except requests.exceptions.Timeout:
            logger.warning("Telegram: таймаут при отправке уведомления (10 сек)")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Telegram: ошибка подключения: {e}")
            return False
        except requests.exceptions.HTTPError as e:
            error_text = ""
            try:
                error_response = e.response.json() if e.response else {}
                error_text = error_response.get("description", str(e))
            except:
                error_text = str(e)
            logger.error(f"Telegram HTTP ошибка: {error_text} (status: {e.response.status_code if e.response else 'unknown'})")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram: ошибка запроса: {e}")
            return False
        
    except Exception as e:
        logger.error(f"Telegram: неожиданная ошибка при отправке уведомления: {e}\n{traceback.format_exc()}")
        return False

def format_payment_notification(deal_id: str, amount: int, payment_id: str, source: str = "yookassa", title: Optional[str] = None, email: Optional[str] = None) -> str:
    """
    Форматирование уведомления о платеже для Telegram
    
    Args:
        deal_id: ID сделки
        amount: Сумма платежа в копейках (int)
        payment_id: ID платежа
        source: Источник платежа (yookassa, admin_cash)
        title: Название сделки (опционально)
        email: Email клиента (опционально)
    
    Returns:
        Отформатированное сообщение
    """
    try:
        # Валидация и нормализация входных данных
        if not deal_id:
            deal_id = "неизвестно"
        else:
            deal_id = str(deal_id).strip()
        
        if not payment_id:
            payment_id = "неизвестно"
        else:
            payment_id = str(payment_id).strip()
        
        # Обработка amount (может быть int, float, str)
        try:
            if isinstance(amount, str):
                amount = float(amount)
            amount = float(amount)
            if amount < 0:
                amount = 0
        except (ValueError, TypeError) as e:
            logger.warning(f"Telegram: некорректная сумма платежа: {amount}, ошибка: {e}")
            amount = 0
        
        # Конвертируем копейки в рубли (amount всегда в копейках)
        amount_rub = amount / 100.0
        
        # Нормализация source
        source = str(source).lower() if source else "yookassa"
        source_emoji = "💳" if source == "yookassa" else "💵"
        source_name = "YooKassa" if source == "yookassa" else "Наличные"
        
        # Формирование сообщения
        message = f"{source_emoji} <b>Новый платеж</b>\n\n"
        message += f"💰 Сумма: <b>{amount_rub:,.2f} ₽</b>\n"
        message += f"📋 Сделка: <b>{deal_id}</b>\n"
        
        if title:
            title_str = str(title).strip()
            if title_str:
                # Экранируем HTML-символы для безопасности
                title_str = title_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                message += f"📝 Название: {title_str}\n"
        
        if email:
            email_str = str(email).strip()
            if email_str:
                # Экранируем HTML-символы
                email_str = email_str.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                message += f"👤 Клиент: {email_str}\n"
        
        message += f"🔗 Платеж: {payment_id}\n"
        message += f"📦 Источник: {source_name}"
        
        return message
        
    except Exception as e:
        logger.error(f"Telegram: ошибка при форматировании уведомления: {e}\n{traceback.format_exc()}")
        # Возвращаем минимальное сообщение в случае ошибки
        try:
            amount_rub = float(amount) / 100.0 if amount else 0
            return f"💳 <b>Новый платеж</b>\n\n💰 Сумма: <b>{amount_rub:,.2f} ₽</b>\n📋 Сделка: <b>{deal_id}</b>\n🔗 Платеж: {payment_id}"
        except:
            return f"💳 <b>Новый платеж</b>\n\n📋 Сделка: <b>{deal_id}</b>"

