import os
import logging
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from payments.router import router as payments_router
from installments.router import router as installments_router
from auth.magic_link import router as auth_router
from admin.router import router as admin_router
from models.payment_log import init_db
from core.config import settings

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Bitrix Installment API")

# Обработчик ошибок валидации
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Логируем ошибки валидации запросов"""
    body_bytes = await request.body()
    logger.error(f"Ошибка валидации запроса {request.method} {request.url.path}")
    logger.error(f"Ошибки валидации: {exc.errors()}")
    logger.error(f"Body: {body_bytes.decode('utf-8') if body_bytes else 'empty'}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()}
    )

# CORS - для разработки разрешаем все origins
ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "")
if ALLOWED_ORIGINS_ENV:
    ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_ENV.split(",") if origin.strip()]
else:
    # Для локальной разработки разрешаем все origins
    # В FastAPI нужно указать конкретные origins или использовать специальный подход
    ALLOWED_ORIGINS = [
        "http://localhost",
        "http://localhost:80",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://127.0.0.1:3000"
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Инициализация БД при старте с повторными попытками
@app.on_event("startup")
def startup_event():
    import time
    max_retries = 10
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            init_db()
            logger.info("✅ Database initialized successfully")
            break
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Database connection failed (attempt {attempt + 1}/{max_retries}): {e}")
                logger.info(f"   Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(f"❌ Failed to initialize database after {max_retries} attempts: {e}")
                raise

# Роутеры
app.include_router(payments_router)
app.include_router(installments_router)
app.include_router(auth_router)
app.include_router(admin_router)

@app.get("/")
def root():
    return {"status": "ok", "version": "1.0.0", "message": "Bitrix Installment API"}

@app.get("/api")
def api_root():
    return {"status": "ok", "version": "1.0.0", "message": "Bitrix Installment API"}

@app.get("/health")
def health_check():
    """Health check endpoint для мониторинга"""
    return {"status": "healthy"}

@app.get("/api/health")
def api_health_check():
    """Health check endpoint для мониторинга (под /api)"""
    return {"status": "healthy"}

