# Содержимое файла: settings.py (Версия для VPS с доменом starswheelapp.fun)
import os

# В MAIN.PY - НАЙДИТЕ ССЫЛКИ И ПОМЕНЯЙТЕ НА СВОИ! #

TOKEN = os.environ.get('MAIN_BOT_TOKEN', '')  # токен-бота

DONATE_PAY = 149  # сумма доната
DONATE_TIME = 15  # время буста

API_I = int(os.environ.get('API_ID', '123'))  # userbot для автовыдачи звёзд
API_H = os.environ.get('API_HASH', '')  # userbot для автовыдачи звёзд

LINK_1 = "https://t.me/"  # Основной канал
LINK_2 = "https://t.me/"  # Чат
LINK_3 = "https://t.me/"  # Выплаты
LINK_4 = "https://t.me/"  # Стата Мини-игр
LINK_5 = "https://t.me/"  # Пост с отзывами

USER_BOT = os.environ.get('MAIN_BOT_USERNAME', '')
SUP_LOGIN = ""
ADMIN_IDS = [int(x) for x in os.environ.get('ADMIN_IDS', '123').split(',') if x]  # id админов
ADMIN_IDD = int(os.environ.get('ADMIN_IDS', '123').split(',')[0])
LINK_BOT = f"https://t.me/{USER_BOT}?start={ADMIN_IDD}"  # ваша реферальная ссылка на бота

REF_VIVOD_MIN = 20  # Минимальное количество рефералов за неделю для вывода

TELEGRAPH1 = "https://telegra.ph/Kak-polzovatsya-botom-07-20"  # Пример ссылки на гайд
TELEGRAPH2 = "https://telegra.ph/Kak-vyvesti-zvezdy-07-21"  # Пример ссылки на гайд по выводу

CHANEL_ID = int(os.environ.get('CHANEL_ID', '-100'))  # канал выплат (общий)
NEWS_CHANEL_ID = int(os.environ.get('NEWS_CHANEL_ID', '-100'))  # новостной канал (общий)
WIN_CHANEL_ID = int(os.environ.get('WIN_CHANEL_ID', '-100'))  # канал с выигрышами в мини-игре (общий)
LOG_CH_USER = int(os.environ.get('LOG_CH_USER', '-100'))  # канал логов новых пользователей (админский)
LOG_VER_USER = int(os.environ.get('LOG_VER_USER', '-100'))  # канал логов новых пользователей прошедших ОП (админский)
LOG_VIVOD_CHANEL = int(os.environ.get('LOG_VIVOD_CHANEL', '-100'))  # канал логов с выводами (админский)

REQUEST_API_KEY = ''  # получить в https://t.me/subgram_officialbot?start=759768292
SUBGRAM_BOT_API_KEY = os.environ.get('SUBGRAM_BOT_API_KEY', os.environ.get('SUBGRAM_API_KEY', ''))  # Ключ бота SubGram для /get-sponsors
REQUEST_OP_DELAY_HOURS = 0  # Задержка перед проверкой ОП в часах
REQUEST_OP_DELAY_MINUTES = 0  # Задержка перед проверкой ОП в минутах

# Награды (стандартные)
MIN_GIFT = 1.0  # Ежедневный подарок мин
MAX_GIFT = 2.0  # Ежедневный подарок макс

MIN_REF_REWARD = 1.0  # Награда за реферала мин
MAX_REF_REWARD = 1.0  # Награда за реферала макс

CLICK_MIN_REWARD = 0.5  # Награда за клик мин
CLICK_MAX_REWARD = 3.00  # Награда за клик макс

# Награды во время "Счастливого часа"
MIN_GIFT_L = 1.0  # Подарок счастливый час мин
MAX_GIFT_L = 2.0  # Подарок счастливый час макс

MIN_REF_REWARD_X2 = 2.0  # Реферал счастливый час мин
MAX_REF_REWARD_X2 = 2.0  # Реферал счастливый час макс

CLICK_MIN_REWARD_X2 = 0.20  # Клик счастливый час мин
CLICK_MAX_REWARD_X2 = 2.00  # Клик счастливый час макс

# Игры
WIN_CHANCE = 25  # Шанс победы в "Все или ничего" (%)

# Языки
AVAILABLE_LANGS = ['ru']  # Список доступных языков

# Колесо Фортуны
FREE_SPIN_COOLDOWN_SECONDS = 24 * 60 * 60  # Кулдаун бесплатного спина (24 часа в секундах)

WHEEL_WEBAPP_URL = "https://starswheelapp.fun/"  # URL для открытия Mini App

# --- Webhook Settings ---
# Домен, на котором будет доступен бот (публичный HTTPS URL)

WEBHOOK_HOST = "https://starswheelapp.fun"

FREE_SPIN_COST_EQUIVALENT = 25
# Токен добавится автоматически в main.py
WEBHOOK_PATH_PREFIX = "/webhook"

# Настройки встроенного веб-сервера aiogram (на чем слушает сам Python скрипт)
WEBAPP_HOST = "localhost"  # Слушаем локально (IIS будет проксировать)
WEBAPP_PORT = 8080  # Внутренний порт для main.py (должен совпадать с Rewrite URL в IIS)

# В MAIN.PY - НАЙДИТЕ ССЫЛКИ И ПОМЕНЯЙТЕ НА СВОИ! #

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
