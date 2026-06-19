import logging
import json

from aiogram import types, Bot, Dispatcher
from aiogram.types import ContentType

log = logging.getLogger('handlers.webapp')


async def process_webapp_data(message: types.Message, bot: Bot):
    """Обрабатывает данные, полученные от Mini App (НЕ результаты спина)."""
    user_id = message.from_user.id
    user_name = message.from_user.username or f"id_{user_id}"
    log.info(f"--- process_webapp_data TRIGGERED by user {user_id} ---")
    log.debug(f"Raw message.web_app_data: {message.web_app_data}")

    if not message.web_app_data or not message.web_app_data.data:
        log.warning(f"No web_app_data from user {user_id}.")
        return

    try:
        data = json.loads(message.web_app_data.data)
        log.debug(f"Parsed WebApp data: {data}")
        action = data.get("action", None)
        log.info(f"[process_webapp_data] action='{action}', user={user_id}")

        if not action:
            log.warning(f"No 'action' in webapp data: {data}")
            return

        # --- Обработка ДРУГИХ возможных action ---
        if action == "request_donate":
            log.info(f"User {user_id} requested donate via sendData (Legacy?).")
            await message.reply("Запрос доната (webapp_data).")
        elif action in ["js_error", "js_promise_rejection", "js_init_error"]:
            log.error(f"JavaScript {action} from @{user_name} ({user_id}): {data.get('error')}")
        else:
            log.warning(f"Unknown webapp action='{action}' from user {user_id}. Data: {data}")

    except json.JSONDecodeError:
        log.error(f"Failed parse JSON from webapp for {user_id}: {message.web_app_data.data}")
    except Exception as e:
        log.exception(f"CRITICAL error process_webapp_data user {user_id}: {e}")


def register_webapp_handlers(dp: Dispatcher, bot: Bot):
    """Регистрация хендлера для данных WebApp (кроме результатов спина)."""
    dp.register_message_handler(
        lambda msg: process_webapp_data(msg, bot),
        content_types=ContentType.WEB_APP_DATA
    )
    log.info("WebApp data handler registered (handles non-spin actions).")
