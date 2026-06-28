import os
TOKEN = os.environ.get("BOT_TOKEN", "токен бота")

# --- НОВОЕ: Настройки подключения к PostgreSQL ---
PG_DBNAME = os.environ.get("PG_DBNAME", "zvezdopad_db")  # Имя вашей базы данных
PG_USER = os.environ.get("PG_USER", "root")  # Имя пользователя БД
PG_PASSWORD = os.environ.get("PG_PASSWORD", "2f7h2c3r")  # Пароль пользователя БД
PG_HOST = os.environ.get("PG_HOST", "localhost")  # Хост БД (localhost, если БД на том же сервере)
PG_PORT = os.environ.get("PG_PORT", "5432")  # Порт PostgreSQL (стандартный 5432)
# Настройки пула соединений (можно добавить позже)
PG_POOL_MIN_SIZE = int(os.environ.get("PG_POOL_MIN_SIZE", 1))
PG_POOL_MAX_SIZE = int(os.environ.get("PG_POOL_MAX_SIZE", 50))
# --------------------------------------------------

DONATE_PAY = 149
DONATE_TIME = 15

# --- Pyrogram API ID и Hash (рекомендуется брать из окружения) ---
API_I = int(os.environ.get("API_ID", "апи айди"))
API_H = os.environ.get("API_HASH", "апи хэш")
# ---------------------------------------------------------------
PAYMENT_BOT_USERNAME = "юз бота для оплаты"
LINK_1 = "https://t.me/"
LINK_2 = "https://t.me/"  # Чат
LINK_3 = "https://t.me/"  # Выплаты
LINK_4 = "https://t.me/"  # Стата Мини-игр
LINK_5 = "https://t.me/"  # Пост с отзывами

USER_BOT = os.environ.get("BOT_USERNAME", 'zvezdopadtg_bot')  # Имя бота тоже лучше из окружения
SUP_LOGIN = "юз поддержки"
ADMIN_IDS_STR = os.environ.get("ADMIN_IDS", "айди админов")
ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(',') if admin_id.strip().isdigit()]

ADMIN_IDD = ADMIN_IDS[0] if ADMIN_IDS else None  # Используем первого админа для ссылки по умолчанию
LINK_BOT = f"https://t.me/{USER_BOT}?start={ADMIN_IDD}" if ADMIN_IDD else f"https://t.me/{USER_BOT}"

TELEGRAPH1 = "https://telegra.ph/Kak-polzovatsya-botom-07-20"
TELEGRAPH2 = "https://telegra.ph/Kak-vyvesti-zvezdy-07-21"

CHANEL_ID_STR = os.environ.get("CHANEL_ID", "айди из env взять")  # <--- Каналы тоже лучше в окружение
CHANEL_ID = int(CHANEL_ID_STR) if CHANEL_ID_STR.startswith('-') else CHANEL_ID_STR

NEWS_CHANEL_ID_STR = os.environ.get("NEWS_CHANEL_ID", "айди из env взять")
NEWS_CHANEL_ID = int(NEWS_CHANEL_ID_STR) if NEWS_CHANEL_ID_STR.startswith('-') else NEWS_CHANEL_ID_STR

WIN_CHANEL_ID_STR = os.environ.get("WIN_CHANEL_ID", "айди из env взять")
WIN_CHANEL_ID = int(WIN_CHANEL_ID_STR) if WIN_CHANEL_ID_STR.startswith('-') else WIN_CHANEL_ID_STR

LOG_CH_USER_STR = os.environ.get("LOG_CH_USER", "айди из env взять")
LOG_CH_USER = int(LOG_CH_USER_STR) if LOG_CH_USER_STR.startswith('-') else LOG_CH_USER_STR

LOG_VER_USER_STR = os.environ.get("LOG_VER_USER", "айди из env взять")
LOG_VER_USER = int(LOG_VER_USER_STR) if LOG_VER_USER_STR.startswith('-') else LOG_VER_USER_STR

LOG_VIVOD_CHANEL_STR = os.environ.get("LOG_VIVOD_CHANEL", "айди из env взять")
LOG_VIVOD_CHANEL = int(LOG_VIVOD_CHANEL_STR) if LOG_VIVOD_CHANEL_STR.startswith('-') else LOG_VIVOD_CHANEL_STR

REQUEST_API_KEY = os.environ.get("SUBGRAM_API_KEY",
                                 'ключ сабграм')  # Ключ SubGram
REQUEST_OP_DELAY_HOURS = 0
REQUEST_OP_DELAY_MINUTES = 0

MIN_GIFT = 1.0
MAX_GIFT = 2.0
MIN_REF_REWARD = 1.0
MAX_REF_REWARD = 1.0
CLICK_MIN_REWARD = 0.5
CLICK_MAX_REWARD = 3.00

MIN_GIFT_L = 1.0
MAX_GIFT_L = 2.0
MIN_REF_REWARD_X2 = 2.0
MAX_REF_REWARD_X2 = 2.0
CLICK_MIN_REWARD_X2 = 0.20
CLICK_MAX_REWARD_X2 = 2.00

# Игры
WIN_CHANCE = 25

# Языки
AVAILABLE_LANGS = ['ru']

WHEEL_WEBAPP_URL = "https://starswheelapp.fun/"

FREE_SPIN_COOLDOWN_SECONDS = 24 * 60 * 60
FREE_SPIN_COST_EQUIVALENT = 25


WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "https://starswheelapp.fun")
WEBHOOK_PATH_PREFIX = "/webhook"

WEBAPP_HOST = os.environ.get("WEBAPP_HOST", "localhost")  # Слушаем локально
WEBAPP_PORT = int(os.environ.get("WEBAPP_PORT", "8080"))  # Порт для aiohttp

AVAILABLE_DAILY_GIFTS = {
    "🧸 Мишка (15⭐)": 5170233102089322756,
    "💝 Сердце (15⭐)": 5170145012310081615,
    "🌹 Роза (25⭐)": 5168103777563050263,
    "🎁 Подарок (25⭐)": 5170250947678437525,
    "🚀 Ракета (50⭐)": 5170564780938756245,
    "🍾 Шампанское (50⭐)": 6028601630662853006,
    "💐 Букет (50⭐)": 5170314324215857265,
    "🎂 Торт (50⭐)": 5170144170496491616,
    "🏆 Кубок (100⭐)": 5168043875654172773,
    "💍 Кольцо (100⭐)": 5170690322832818290,
    "💎 Алмаз (100⭐)": 5170521118301225164,
    "🕯 Cвеча (350⭐)": 5782984811920491178,
}
DEFAULT_DAILY_GIFT_KEY = "🧸 Мишка (15⭐)"

FLYER_API_KEY = os.environ.get('FLYER_API_KEY', '')  # Ключ FlyerBot для заданий
