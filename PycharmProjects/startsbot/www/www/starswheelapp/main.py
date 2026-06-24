# Содержимое файла: main.py (Обновлено для раздачи статики Mini App и исправлен MIME-тип)
import asyncio
import logging
import os
import sys
import pathlib  # <--- ДОБАВЛЕН ИМПОРТ
import mimetypes # <--- ДОБАВЛЕН ИМПОРТ

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage  # В ПРОДАКШЕНЕ ЗАМЕНИТЬ!
from aiogram.dispatcher.webhook import configure_app, web
from aiohttp import web as aiohttp_web
from pyrogram import Client

import database
from settings import (
    TOKEN, API_I, API_H,
    WEBHOOK_HOST, WEBHOOK_PATH_PREFIX, WEBAPP_HOST, WEBAPP_PORT,
    ADMIN_IDS
)
from scheduler import setup_scheduler
from handlers import register_all_handlers
# Импортируем ВСЕ нужные обработчики API из handlers.api
from handlers.api import (
    handle_options, handle_start_spin, handle_confirm_spin_action,
    handle_get_user_state, handle_get_game_history, handle_play_luck_game,
    handle_attempt_robbery, handle_play_slots  # <--- ДОБАВЛЕНЫ НЕДОСТАЮЩИЕ
)
# Middleware для тех. работ
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from database import is_maintenance_mode, get_maintenance_message

# --- ЯВНОЕ УКАЗАНИЕ MIME-ТИПА ДЛЯ .JS ---
mimetypes.add_type('application/javascript', '.js')
log = logging.getLogger(__name__) # Логгер лучше инициализировать после настройки mimetypes
log.info("MIME type for .js explicitly set to application/javascript")
# ------------------------------------------

# --- КОНФИГУРАЦИЯ ЛОГГИРОВАНИЯ ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger('aiogram').setLevel(logging.WARNING)
logging.getLogger('aiohttp').setLevel(logging.WARNING)
logging.getLogger('pyrogram').setLevel(logging.WARNING)
# log = logging.getLogger(__name__) # Перенесено выше, после mimetypes
# -----------------------------------------------

# --- ПРОВЕРКИ НАСТРОЕК ---
if not WEBHOOK_HOST or "замени_на" in WEBHOOK_HOST.lower() or "your_url" in WEBHOOK_HOST.lower():
    sys.exit("Ошибка: WEBHOOK_HOST не настроен или содержит плейсхолдер в settings.py")
if not WEBHOOK_PATH_PREFIX or not WEBHOOK_PATH_PREFIX.startswith('/'):
    sys.exit("Ошибка: WEBHOOK_PATH_PREFIX должен начинаться с / в settings.py")
# ---------------------------------------


# --- MIDDLEWARE: Режим тех. работ ---
class MaintenanceMiddleware(BaseMiddleware):
    """Перехватывает все входящие обновления и отвечает текстом тех. работ, если режим включен."""

    async def on_process_message(self, message, data):
        if is_maintenance_mode():
            # Пропускаем админов
            if message.from_user and message.from_user.id in ADMIN_IDS:
                return
            maintenance_text = get_maintenance_message()
            await message.answer(maintenance_text, parse_mode="HTML")
            raise CancelHandler()  # Прерываем обработку

    async def on_process_callback_query(self, callback_query, data):
        if is_maintenance_mode():
            # Пропускаем админов
            if callback_query.from_user and callback_query.from_user.id in ADMIN_IDS:
                return
            maintenance_text = get_maintenance_message()
            await callback_query.answer(maintenance_text, show_alert=True)
            raise CancelHandler()  # Прерываем обработку
# ------------------------------------


pyrogram_client: Client | None = None


# --- ФУНКЦИИ on_startup и on_shutdown ---
async def on_startup(app: aiohttp_web.Application):
    log.info("Executing on_startup...")
    bot: Bot = app['bot']
    webhook_full_url: str = app['webhook_full_url']
    pyro_client: Client | None = app.get('pyrogram_client')

    log.warning(f"Setting webhook: {webhook_full_url}")
    try:
        webhook_info = await bot.get_webhook_info()
        log.debug(f"Current webhook: {webhook_info}")
        if webhook_info.url != webhook_full_url:
            log.info("Deleting old webhook...")
            await bot.delete_webhook(drop_pending_updates=True)
            await asyncio.sleep(0.5)
            log.info(f"Setting new webhook to {webhook_full_url}...")
            set_result = await bot.set_webhook(url=webhook_full_url)
            log.info(f"Webhook set result: {set_result}")
        else:
            log.info("Webhook URL already matches. Skipping set_webhook.")
    except Exception as e:
        log.exception("!!! FAILED TO SET WEBHOOK !!!")

    global pyrogram_client
    if pyrogram_client and not pyrogram_client.is_initialized:
        try:
            log.info("Starting Pyrogram client...")
            await pyrogram_client.start()
            me = await pyrogram_client.get_me()
            log.info(f"Pyrogram client started successfully as @{me.username}")
        except Exception as e:
            log.exception(f"Failed to start Pyrogram client: {e}")
    elif not pyrogram_client:
        log.warning("Pyrogram client (app) not initialized, skipping start.")
    else:
        log.info("Pyrogram client already initialized.")

    # Передаем и бота, и pyrogram_client в планировщик
    setup_scheduler(bot, pyro_client)
    log.info("Scheduler setup complete.")
    log.info("Startup process finished.")


async def on_shutdown(app: aiohttp_web.Application):
    log.info("Executing on_shutdown...")
    bot: Bot = app['bot']
    dp: Dispatcher = app['dp']
    log.warning("Attempting to delete webhook...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Webhook deleted successfully.")
    except Exception as e:
        log.error(f"Failed to delete webhook during shutdown: {e}")

    global pyrogram_client
    if pyrogram_client and pyrogram_client.is_connected:
        try:
            log.info("Stopping Pyrogram client...")
            await pyrogram_client.stop()
            log.info("Pyrogram client stopped successfully.")
        except Exception as e:
            log.error(f"Error stopping Pyrogram client: {e}")
    else:
        log.info("Pyrogram client was not running or not initialized, skipping stop.")

    log.info("Closing FSM storage...")
    if dp.storage:
        await dp.storage.close()
        await dp.storage.wait_closed()
        log.info("FSM storage closed.")
    else:
        log.warning("No FSM storage found to close.")

    log.info("Closing bot session...")
    try:
        session = await bot.get_session()
        if session and not session.closed:
            await session.close()
            await asyncio.sleep(0.2)  # Даем время на закрытие
            log.info("Bot session closed.")
        elif session and session.closed:
            log.info("Bot session already closed.")
        else:
            log.warning("Could not get bot session to close.")
    except Exception as e:
        log.error(f"Error closing bot session: {e}")

    log.info("Shutdown process complete.")


# ---------------------------------------------------

def main():
    log.critical("--- SCRIPT main.py STARTED ---")
    webhook_url_path = f"{WEBHOOK_PATH_PREFIX.rstrip('/')}/{TOKEN}"
    webhook_full_url = f"{WEBHOOK_HOST.rstrip('/')}{webhook_url_path}"
    log.info(f"Calculated Webhook path: {webhook_url_path}")
    log.info(f"Calculated Webhook full URL: {webhook_full_url}")

    log.info("Initializing Database...")
    try:
        database.check_and_create_tables()
        log.info("Database initialized successfully.")
    except Exception as db_init_err:
        log.exception("!!! DATABASE INITIALIZATION FAILED !!!")
        sys.exit(f"Fatal: Database initialization failed: {db_init_err}")

    log.info("Initializing Aiogram Bot and Dispatcher...")
    storage = MemoryStorage()  # РЕКОМЕНДУЕТСЯ ЗАМЕНИТЬ НА RedisStorage В ПРОДАКШЕНЕ
    bot = Bot(token=TOKEN, parse_mode='HTML', disable_web_page_preview=True)
    dp = Dispatcher(bot, storage=storage)
    dp.middleware.setup(MaintenanceMiddleware())  # Подключаем middleware тех. работ
    log.info("Aiogram Bot and Dispatcher initialized successfully.")

    global pyrogram_client
    try:
        # Используем имя сессии "ClientStars" как в вашем коде
        pyrogram_client = Client("ClientStars", api_id=API_I, api_hash=API_H, no_updates=True)
        log.info("Pyrogram client initialized successfully.")
    except Exception as e:
        log.exception("!!! PYROGRAM INITIALIZATION FAILED !!!")
        pyrogram_client = None  # Устанавливаем в None, если инициализация не удалась
        log.warning("Continuing without Pyrogram client features (like sending gifts).")

    log.info("Registering Aiogram handlers...")
    # Передаем pyrogram_client в регистратор
    register_all_handlers(dp, bot, pyrogram_client)
    log.info("Aiogram handlers registered successfully.")

    log.info("Creating aiohttp web application...")
    app = aiohttp_web.Application()
    # Сохраняем объекты в приложении для доступа в on_startup/on_shutdown и обработчиках
    app['bot'] = bot
    app['dp'] = dp
    app['pyrogram_client'] = pyrogram_client
    app['webhook_full_url'] = webhook_full_url
    log.info("aiohttp application created.")

    # --- НАЧАЛО: Добавленный код для раздачи статики ---
    log.info("Configuring static file serving for Mini App...")
    # Определяем путь к папке 'static_webapp' относительно текущего файла (main.py)
    STATIC_ROOT = pathlib.Path(__file__).parent / "static_webapp"
    log.info(f"Static files root path: {STATIC_ROOT}")

    if not STATIC_ROOT.is_dir():
        log.error(f"Static webapp directory not found at: {STATIC_ROOT}")
        # Можно либо завершить выполнение, либо продолжить без Mini App
        # sys.exit(f"Fatal: Static webapp directory not found at {STATIC_ROOT}")

    # Функция для отдачи index.html по корневому URL '/'
    async def handle_mini_app_index(request):
        index_path = STATIC_ROOT / 'index.html'
        log.debug(f"Request for / received. Trying to serve: {index_path}")
        if index_path.is_file():
            return aiohttp_web.FileResponse(index_path)
        else:
            log.error(f"Mini App index.html not found at: {index_path}")
            return aiohttp_web.Response(text="Mini App index.html not found", status=404)

    # Регистрируем обработчик для '/'
    app.router.add_get('/', handle_mini_app_index)
    log.info(f"Route GET '/' registered for Mini App index.html")

    # Регистрируем статический маршрут для ВСЕХ остальных файлов (js, css, images, sounds...)
    # Запросы вида /js/main.js будут искать файл в static_webapp/js/main.js
    # Имя 'webapp_static' используется внутренне aiohttp, должно быть уникальным
    app.router.add_static('/', path=STATIC_ROOT, name='webapp_static', show_index=False, follow_symlinks=True)
    log.info(f"Static route '/' registered to serve files from: {STATIC_ROOT}")
    # --- КОНЕЦ: Добавленный код для раздачи статики ---

    # --- Регистрация ВСЕХ API эндпоинтов ---
    log.info("Registering API routes...")
    app.router.add_post('/api/get_user_state', handle_get_user_state)
    app.router.add_route('OPTIONS', '/api/get_user_state', handle_options)

    app.router.add_post('/api/start_spin', handle_start_spin)
    app.router.add_route('OPTIONS', '/api/start_spin', handle_options)

    app.router.add_post('/api/confirm_spin_action', handle_confirm_spin_action)
    app.router.add_route('OPTIONS', '/api/confirm_spin_action', handle_options)

    # Добавляем недостающие API роуты
    app.router.add_post('/api/get_game_history', handle_get_game_history)
    app.router.add_route('OPTIONS', '/api/get_game_history', handle_options)

    app.router.add_post('/api/play_luck_game', handle_play_luck_game)
    app.router.add_route('OPTIONS', '/api/play_luck_game', handle_options)

    app.router.add_post('/api/attempt_robbery', handle_attempt_robbery)
    app.router.add_route('OPTIONS', '/api/attempt_robbery', handle_options)

    app.router.add_post('/api/play_slots', handle_play_slots)
    app.router.add_route('OPTIONS', '/api/play_slots', handle_options)

    log.info("All API routes registered successfully.")
    # -----------------------------------------

    # --- Настройка вебхука Aiogram ---
    log.info(f"Configuring Aiogram webhook handler at path: {webhook_url_path}")
    configure_app(dispatcher=dp, app=app, path=webhook_url_path)
    log.info("Aiogram webhook handler configured successfully.")
    # --------------------------------

    # --- Регистрация функций startup/shutdown ---
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    log.info("on_startup and on_shutdown handlers registered.")
    # ------------------------------------------

    # --- Запуск веб-сервера ---
    log.info(f"Attempting to start aiohttp web server on {WEBAPP_HOST}:{WEBAPP_PORT}")
    try:
        # Используем access_log_format для более детального логирования запросов, если нужно
        # access_log_format = '%a %t "%r" %s %b "%{Referer}i" "%{User-Agent}i"'
        aiohttp_web.run_app(
            app,
            host=WEBAPP_HOST,
            port=WEBAPP_PORT,
            access_log=logging.getLogger('aiohttp.access')  # Используем стандартный логгер доступа
        )
    except OSError as e:
        # Частая ошибка - порт уже занят
        log.exception(f"!!! FAILED TO RUN AIOHTTP APP (OSError): {e} - Is port {WEBAPP_PORT} already in use?")
    except Exception as e:
        log.exception(f"!!! FAILED TO RUN AIOHTTP APP (General Error): {e}")
    # -------------------------


if __name__ == '__main__':
    main()