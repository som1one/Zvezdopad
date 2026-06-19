import os
from dotenv import load_dotenv

load_dotenv()

PAYMENT_BOT_TOKEN = os.getenv("PAYMENT_BOT_TOKEN", "")
MAIN_BOT_USERNAME = os.getenv("MAIN_BOT_USERNAME", "юз мейн бота")

PG_DBNAME = os.getenv("PG_DBNAME", "zvezdopad_db")
PG_USER = os.getenv("PG_USER", "root")
PG_PASSWORD = os.getenv("PG_PASSWORD", "2f7h2c3r")
PG_HOST = os.getenv("PG_HOST_DOCKER", "db")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_POOL_MIN_SIZE = int(os.getenv("PG_POOL_MIN_SIZE_PAYMENT", 1))
PG_POOL_MAX_SIZE = int(os.getenv("PG_POOL_MAX_SIZE_PAYMENT", 30))

BOOST_OPTIONS = {
    "speed_boost_7d": {
        "name": "Ускоритель Фарма (7 дней)",
        "price_stars": 150,
        "description": "Увеличивает скорость получения звезд от фарма на 50% на 7 дней.",
        "duration_hours": 7 * 24,
        "type": "farm_speed",
        "effect_value": 1.5
    },
    "luck_boost_3h": {
        "name": "Эликсир Удачи (3 часа)",
        "price_stars": 75,
        "description": "Повышает шанс выигрыша в мини-играх на 10% на 3 часа.",
        "duration_hours": 3,
        "type": "game_luck",
        "effect_value": 10
    },
}

ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "1387831254, 7372997904, 7894577123")
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip().isdigit()]

INVOICE_PHOTO_URL_TOPUP = "https://cdn-icons-png.flaticon.com/512/1019/1019607.png"
INVOICE_PHOTO_URL_BOOST = "https://cdn-icons-png.flaticon.com/512/2621/2621158.png"
