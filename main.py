import asyncio
import logging
import logging.handlers  # Добавлено для RotatingFileHandler
import os
import sys
import pathlib
import mimetypes
import asyncpg

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.webhook import configure_app, web
from aiohttp import web as aiohttp_web
from pyrogram import Client

import database
from settings import (
    TOKEN, API_I, API_H, WEBHOOK_HOST, WEBHOOK_PATH_PREFIX,
    WEBAPP_HOST, WEBAPP_PORT, ADMIN_IDS
)
from scheduler import setup_scheduler
from handlers import register_all_handlers
from handlers.user_donations import log as user_donations_log
from handlers.api import (
    handle_options, handle_start_spin, handle_confirm_spin_action,
    handle_get_user_state, handle_get_game_history, handle_play_luck_game,
    handle_attempt_robbery, handle_play_slots
)

mimetypes.add_type('application/javascript', '.js')
log = logging.getLogger(__name__)

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
LOG_FILENAME = "error.log"
INFO_LOG_FILENAME = "info.log"  # Используем отдельную переменную
LOG_MAX_BYTES = 5 * 1024 * 1024
INFO_LOG_MAX_BYTES = 15 * 1024 * 1024  # Увеличим размер для debug лога
LOG_BACKUP_COUNT = 3
INFO_LOG_BACKUP_COUNT = 5  # И количество бэкапов

# Устанавливаем базовый уровень для корневого логгера на DEBUG
logging.getLogger().setLevel(logging.DEBUG)

# Форматтер
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Обработчик для вывода в консоль (DEBUG)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(logging.DEBUG)  # <-- Установлен DEBUG
logging.getLogger().addHandler(stream_handler)

# Обработчик для записи ОШИБОК в файл с ротацией (ERROR)
try:
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILENAME, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding='utf-8'
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.ERROR)  # <-- Оставляем ERROR
    logging.getLogger().addHandler(file_handler)
    logging.error(f"File logging (ERROR level) configured to: {LOG_FILENAME}")  # Используем error для важного сообщения
except Exception as e:
    logging.exception("!!! FAILED TO CONFIGURE ERROR FILE LOGGING !!!")

# Обработчик для записи INFO/DEBUG в файл с ротацией
try:
    info_file_handler = logging.handlers.RotatingFileHandler(
        INFO_LOG_FILENAME, maxBytes=INFO_LOG_MAX_BYTES, backupCount=INFO_LOG_BACKUP_COUNT, encoding='utf-8'
    )
    info_file_handler.setFormatter(log_formatter)
    info_file_handler.setLevel(logging.DEBUG)  # <-- Установлен DEBUG
    logging.getLogger().addHandler(info_file_handler)
    logging.info(f"File logging (DEBUG level) configured to: {INFO_LOG_FILENAME}")  # Используем info
except Exception as e:
    logging.exception("!!! FAILED TO CONFIGURE INFO/DEBUG FILE LOGGING !!!")

# Приглушаем библиотеки, кроме указанных
logging.getLogger('aiogram').setLevel(logging.INFO)  # <--- Установлен INFO для aiogram
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('pyrogram').setLevel(logging.ERROR)  # <--- Оставлен ERROR для pyrogram
logging.getLogger('asyncpg').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.INFO)  # Планировщик можно INFO

# Устанавливаем DEBUG для наших модулей
logging.getLogger('utils').setLevel(logging.DEBUG)
logging.getLogger('database').setLevel(logging.DEBUG)  # Можно DEBUG для отладки запросов
logging.getLogger('handlers').setLevel(logging.DEBUG)  # Все обработчики на DEBUG
logging.getLogger('scheduler').setLevel(logging.DEBUG)  # Планировщик тоже на DEBUG

# Переопределяем уровень для user_donations, если нужно (например, INFO)
# user_donations_log.setLevel(logging.INFO) # Закомментировано, т.к. handlers уже DEBUG

logging.critical(
    "Logging configured. Base level: DEBUG, File (Error): ERROR, File (Info): DEBUG.")  # Используем critical
# --- КОНЕЦ НАСТРОЙКИ ЛОГИРОВАНИЯ ---

pyrogram_client: Client | None = None


async def on_startup(app: aiohttp_web.Application):
    logging.critical("Executing on_startup...")  # Используем critical
    bot: Bot = app['bot']
    webhook_full_url: str = app['webhook_full_url']
    pyro_client: Client | None = app.get('pyrogram_client')

    try:
        await database.init_db_pool()
        app['db_pool'] = database.db_pool
        logging.info("Database pool initialized.")
    except Exception as e:
        logging.exception("!!! DATABASE POOL INITIALIZATION FAILED !!!")
        sys.exit("Fatal: Database pool initialization failed.")

    logging.info(f"Setting webhook: {webhook_full_url}")
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url != webhook_full_url:
            logging.info("Deleting old webhook...")
            await bot.delete_webhook(drop_pending_updates=True)
            await asyncio.sleep(0.5)
            logging.info(f"Setting new webhook to {webhook_full_url}...")
            set_result = await bot.set_webhook(url=webhook_full_url)
            logging.info(f"Webhook set result: {set_result}")
        else:
            logging.info("Webhook URL already matches.")
    except Exception as e:
        logging.exception("!!! FAILED TO SET WEBHOOK !!!")

    global pyrogram_client
    if pyrogram_client and not pyrogram_client.is_initialized:
        try:
            logging.info("Starting Pyrogram client...")
            await pyrogram_client.start()
            me = await pyrogram_client.get_me()
            logging.info(f"Pyrogram client started as @{me.username}")
        except Exception as e:
            logging.exception(f"Failed start Pyrogram client: {e}")
    elif not pyrogram_client:
        logging.warning("Pyrogram client not initialized, skipping.")
    else:
        logging.info("Pyrogram client already initialized.")

    setup_scheduler(bot, pyro_client)
    logging.critical("Startup process finished.")  # Используем critical


async def on_shutdown(app: aiohttp_web.Application):
    logging.critical("Executing on_shutdown...")  # Используем critical
    bot: Bot = app['bot'];
    dp: Dispatcher = app['dp']

    logging.info("Attempting to delete webhook...")
    try:
        await bot.delete_webhook(drop_pending_updates=True);
        logging.info("Webhook deleted.")
    except Exception as e:
        logging.error(f"Failed delete webhook shutdown: {e}")

    global pyrogram_client
    if pyrogram_client and pyrogram_client.is_connected:
        try:
            logging.info("Stopping Pyrogram client...");
            await pyrogram_client.stop();
            logging.info("Pyrogram client stopped.")
        except Exception as e:
            logging.error(f"Error stopping Pyrogram client: {e}")
    else:
        logging.warning("Pyrogram client not running/initialized during shutdown.")

    logging.info("Closing PostgreSQL connection pool...")
    await database.close_db_pool()

    logging.info("Closing FSM storage...")
    if dp.storage:
        await dp.storage.close();
        await dp.storage.wait_closed();
        logging.info("FSM storage closed.")
    else:
        logging.warning("No FSM storage found.")

    logging.info("Closing bot session...")
    try:
        session = await bot.get_session()
        if session and not session.closed:
            await session.close();
            await asyncio.sleep(0.2);
            logging.info("Bot session closed.")
        elif session and session.closed:
            logging.info("Bot session already closed.")
        else:
            logging.warning("Could not get bot session.")
    except Exception as e:
        logging.error(f"Error closing bot session: {e}")
    logging.critical("Shutdown process complete.")  # Используем critical


def main():
    logging.critical("--- SCRIPT main.py STARTED ---")
    webhook_url_path = f"{WEBHOOK_PATH_PREFIX.rstrip('/')}/{TOKEN}"
    webhook_full_url = f"{WEBHOOK_HOST.rstrip('/')}{webhook_url_path}"
    logging.info(f"Webhook path: {webhook_url_path}")
    logging.info(f"Webhook full URL: {webhook_full_url}")

    logging.info("Initializing Aiogram Bot and Dispatcher...")
    storage = MemoryStorage()
    bot = Bot(token=TOKEN, parse_mode='HTML', disable_web_page_preview=True)
    dp = Dispatcher(bot, storage=storage)
    logging.info("Aiogram initialized.")

    global pyrogram_client
    try:
        pyrogram_client = Client("ClientStars", api_id=API_I, api_hash=API_H, no_updates=True)
        logging.info("Pyrogram client initialized.")
    except Exception as e:
        logging.exception("!!! PYROGRAM INIT FAILED !!!");
        pyrogram_client = None

    logging.info("Registering Aiogram handlers...")
    register_all_handlers(dp, bot, pyrogram_client)
    logging.info("Aiogram handlers registered.")

    logging.info("Creating aiohttp web application...")
    app = aiohttp_web.Application()
    app['bot'] = bot
    app['dp'] = dp
    app['pyrogram_client'] = pyrogram_client
    app['webhook_full_url'] = webhook_full_url
    app['WEBHOOK_HOST'] = WEBHOOK_HOST
    logging.info("aiohttp application created.")

    logging.info("Configuring static file serving...")
    STATIC_ROOT = pathlib.Path(__file__).parent / "static_webapp"
    logging.info(f"Static files root: {STATIC_ROOT}")
    if not STATIC_ROOT.is_dir(): logging.error(f"Static dir not found: {STATIC_ROOT}")

    async def handle_mini_app_index(request):
        index_path = STATIC_ROOT / 'index.html'
        if index_path.is_file():
            return aiohttp_web.FileResponse(index_path)
        else:
            logging.error(f"Mini App index.html not found: {index_path}");
            return aiohttp_web.Response(text="Not Found", status=404)

    app.router.add_get('/', handle_mini_app_index)
    app.router.add_static('/', path=STATIC_ROOT, name='webapp_static', show_index=False, follow_symlinks=True)
    logging.info("Static routes configured.")

    logging.info("Registering API routes...")
    app.router.add_post('/api/get_user_state', handle_get_user_state)
    app.router.add_route('OPTIONS', '/api/get_user_state', handle_options)
    app.router.add_post('/api/start_spin', handle_start_spin)
    app.router.add_route('OPTIONS', '/api/start_spin', handle_options)
    app.router.add_post('/api/confirm_spin_action', handle_confirm_spin_action)
    app.router.add_route('OPTIONS', '/api/confirm_spin_action', handle_options)
    app.router.add_post('/api/get_game_history', handle_get_game_history)
    app.router.add_route('OPTIONS', '/api/get_game_history', handle_options)
    app.router.add_post('/api/play_luck_game', handle_play_luck_game)
    app.router.add_route('OPTIONS', '/api/play_luck_game', handle_options)
    app.router.add_post('/api/attempt_robbery', handle_attempt_robbery)
    app.router.add_route('OPTIONS', '/api/attempt_robbery', handle_options)
    app.router.add_post('/api/play_slots', handle_play_slots)
    app.router.add_route('OPTIONS', '/api/play_slots', handle_options)
    logging.info("API routes registered.")

    logging.info(f"Configuring Aiogram webhook handler: {webhook_url_path}")
    configure_app(dispatcher=dp, app=app, path=webhook_url_path)
    logging.info("Aiogram webhook configured.")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    logging.info("on_startup/on_shutdown handlers registered.")

    logging.info(f"Starting aiohttp web server {WEBAPP_HOST}:{WEBAPP_PORT}")
    try:
        aiohttp_web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT, access_log=None)
    except OSError as e:
        logging.exception(f"!!! FAILED RUN AIOHTTP (OSError): {e} - Port {WEBAPP_PORT} busy?")
    except Exception as e:
        logging.exception(f"!!! FAILED RUN AIOHTTP (General Error): {e}")


if __name__ == '__main__':
    main()
