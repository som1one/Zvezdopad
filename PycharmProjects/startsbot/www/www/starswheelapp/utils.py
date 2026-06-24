# Содержимое файла: utils.py (Добавлена функция validate_init_data)
import logging
import aiohttp
from datetime import datetime, timedelta, timezone  # Добавлен timezone
from html import escape
import asyncio
import os
import hmac  # Новый импорт для validate_init_data
import hashlib  # Новый импорт для validate_init_data
import json  # Новый импорт для validate_init_data
from urllib.parse import parse_qsl, unquote  # Новый импорт для validate_init_data

# Переносим импорты, необходимые для этих функций
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram import Bot
# Импортируем функции БД
from database import get_user_lang, get_user_registration_time, get_sponsor_buttons, record_spent_stars, add_stars
# Импортируем настройки и тексты из правильных мест
from settings import REQUEST_API_KEY, ADMIN_IDS, AVAILABLE_LANGS, SUBGRAM_BOT_API_KEY  # AVAILABLE_LANGS из settings.py
from texts import TEXTS  # TEXTS из texts.py

log = logging.getLogger('utils')
adverts_log = logging.getLogger('adverts')


async def show_advert(user_id: int):
    """Показывает рекламу пользователю через Gramads."""
    # ВАЖНО: Токен лучше вынести в settings.py или переменные окружения
    gramads_token = '123'  # Пример, замените!
    if not gramads_token or "YOUR_TOKEN" in gramads_token:
        adverts_log.warning("Gramads token is not configured or is a placeholder.")
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    'https://api.gramads.net/ad/SendPost',
                    headers={
                        'Authorization': f'Bearer {gramads_token}',  # Используем переменную
                        'Content-Type': 'application/json',
                    },
                    json={'SendToChatId': user_id},
                    timeout=aiohttp.ClientTimeout(total=5)  # Добавим таймаут
            ) as response:
                response_text = await response.text()  # Получаем текст ответа для логгирования
                if not response.ok:
                    try:
                        error_details = await response.json()  # Пытаемся прочитать JSON ошибки
                        adverts_log.error(f'Gramads API Error ({response.status}) for user {user_id}: {error_details}')
                    except aiohttp.ContentTypeError:  # Если ответ не JSON
                        adverts_log.error(
                            f'Gramads API Error ({response.status}) for user {user_id}. Body: {response_text[:500]}')  # Логируем начало ответа
                # else: # Логирование успешной отправки не обязательно
                #     adverts_log.debug(f"Gramads advert potentially shown to {user_id}. Response: {response_text[:100]}")

    except asyncio.TimeoutError:
        adverts_log.error(f"Gramads connection timeout for user {user_id}.")
    except aiohttp.ClientConnectorError as e:
        adverts_log.error(f"Gramads connection error for user {user_id}: {e}")
    except Exception as e:
        # Логируем с traceback
        adverts_log.exception(f"Unexpected error showing advert to {user_id}: {e}")


def t(user_id, key):
    """Возвращает текст для пользователя на его языке."""
    lang = 'ru'  # Язык по умолчанию
    try:
        # Пытаемся получить язык пользователя
        lang = get_user_lang(user_id) or 'ru'  # Если get_user_lang вернет None, используем 'ru'
    except Exception as e:
        # Логируем ошибку получения языка, но продолжаем с языком по умолчанию
        log.error(f"Error getting language for user {user_id}: {e}. Falling back to 'ru'.")

    # Проверяем, есть ли такой язык в словаре TEXTS
    if lang not in TEXTS:
        log.warning(f"Language '{lang}' not found in TEXTS for user {user_id}. Falling back to 'ru'.")
        lang = 'ru'

    # Возвращаем текст или ключ, если перевод не найден
    return TEXTS[lang].get(key, f"MISSING_TEXT_{key}")


def get_language_markup():
    """Создает клавиатуру для выбора языка."""
    markup = InlineKeyboardMarkup(row_width=1)  # По одной кнопке в ряд
    for lang_code in AVAILABLE_LANGS:  # Используем AVAILABLE_LANGS из settings.py
        # Получаем название языка из текстов этого языка
        # Если язык или ключ не найдены, используем код языка в верхнем регистре
        lang_name = TEXTS.get(lang_code, {}).get(f'lang_{lang_code}', lang_code.upper())
        button = InlineKeyboardButton(text=lang_name, callback_data=f"set_lang:{lang_code}")
        markup.add(button)
    return markup


def mask_id(user_id):
    """Маскирует последние 3 цифры ID пользователя."""
    user_id_str = str(user_id)
    return user_id_str[:-3] + "***" if len(user_id_str) > 3 else user_id_str


def mask_username(username):
    """Маскирует последние 3 символа имени пользователя."""
    if username and len(username) > 3:
        return username[:-3] + "***"
    return username  # Возвращаем как есть, если короткое или None/пустое


def sanitize_username(username):
    """Удаляет или экранирует опасные символы из имени пользователя."""
    if not username:
        return "unknown"  # Или можно вернуть пустую строку, в зависимости от использования
    # Убираем базовые опасные символы и экранируем через html.escape
    sanitized = escape(username.replace("<", "").replace(">", ""))
    return sanitized


async def get_user_info(bot: Bot, user_id):
    """Получает имя и username пользователя по ID из Telegram API."""
    try:
        user = await bot.get_chat(user_id)
        # Используем first_name или full_name, если есть, иначе 'Без имени'
        full_name = user.full_name or user.first_name or "Без имени"
        username = user.username  # Может быть None
        return full_name, username
    except Exception as e:
        # Логируем ошибку и возвращаем значения по умолчанию
        log.error(f"Error retrieving user info for {user_id} from Telegram API: {e}")
        return "Неизвестный", None


async def create_temp_invite_link(bot: Bot, channel_id: int):
    """Создает временную ссылку-приглашение для канала."""
    try:
        # Создаем ссылку с лимитом на 1 вступление
        invite_link = await bot.create_chat_invite_link(channel_id, member_limit=1)
        return invite_link.invite_link
    except Exception as e:
        log.warning(f"Could not create temp invite link for {channel_id}: {e}. Trying fallback public link.")
        try:
            # Пытаемся сформировать публичную ссылку вида t.me/c/ID_КАНАЛА/1
            # Преобразуем channel_id в положительное число без -100
            numeric_channel_id = int(str(channel_id).replace('-100', ''))
            return f"https://t.me/c/{numeric_channel_id}/1"  # /1 может не работать для всех каналов
        except ValueError:
            log.error(f"Could not create fallback public link for non-numeric channel_id {channel_id}")
            # Возвращаем что-то, что покажет проблему, но не сломает код
            return f"tg://resolve?domain=error_chat_{channel_id}"


async def send_gift_with_retry(app, user_id, star_gift_id, retries=0, max_retries=1, bot_instance: Bot = None):
    """Отправляет подарок Stars с повторными попытками."""
    try:
        if not user_id or not star_gift_id:
            raise ValueError("User ID and Star Gift ID cannot be None.")

        # Pyrogram ожидает int или str для chat_id и int для gift_id
        log.info(f"Attempting to send gift {star_gift_id} to user {user_id}...")
        await app.send_gift(chat_id=int(user_id), gift_id=int(star_gift_id))
        log.info(f"Gift sent successfully to {user_id} (Gift ID: {star_gift_id})")
        return True  # Возвращаем успех

    except Exception as e:
        log.error(f"Error sending gift to {user_id} (Gift ID: {star_gift_id}, Attempt: {retries + 1}): {e}")
        if "BALANCE_TOO_LOW" in str(e):
            log.critical(f"Pyrogram account balance too low to send gift {star_gift_id} to {user_id}")
            # Уведомляем администраторов, если передан bot_instance
            if bot_instance:
                pyro_username = "???"
                try:  # Попробуем получить username аккаунта Pyrogram
                    me = await app.get_me()
                    if me: pyro_username = me.username
                except Exception:
                    pass
                for admin_id in ADMIN_IDS:
                    try:
                        await bot_instance.send_message(admin_id,
                                                        f"⚠️ Недостаточно средств на Pyrogram (@{pyro_username}) для подарка {star_gift_id} юзеру {user_id}!")
                    except Exception as admin_notify_err:
                        log.error(f"Failed to notify admin {admin_id} about low Pyrogram balance: {admin_notify_err}")
            raise e  # Передаем ошибку дальше, чтобы обработать ее в вызывающей функции
        elif retries < max_retries:
            wait_time = 5  # Секунд ожидания перед повтором
            log.warning(
                f"Retrying gift send for {user_id} in {wait_time} seconds... (Attempt {retries + 2}/{max_retries + 1})")
            await asyncio.sleep(wait_time)
            # Передаем bot_instance дальше при рекурсивном вызове
            return await send_gift_with_retry(app, user_id, star_gift_id, retries + 1, max_retries, bot_instance)
        else:
            log.error(f"Failed to send gift to {user_id} after {max_retries + 1} attempts.")
            raise e  # Передаем ошибку после исчерпания попыток
    # Возвращаем False, если все попытки не удались и не было исключения BALANCE_TOO_LOW
    # (хотя raise e должен был прервать выполнение)
    # return False


async def get_subbalance():
    """Получает баланс из SubGram API."""
    if not REQUEST_API_KEY or "YOUR" in REQUEST_API_KEY:  # Проверка ключа
        log.warning("SubGram API key (REQUEST_API_KEY) is not configured.")
        return "Ключ не задан"

    headers = {'Auth': REQUEST_API_KEY}
    url = "https://api.subgram.ru/get-balance/"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:  # Таймаут 10 сек
            async with session.post(url, headers=headers) as response:
                response_text = await response.text()  # Читаем ответ
                if response.status == 200:
                    try:
                        data = await response.json()  # Пытаемся парсить JSON
                        if data.get("status") == "ok":
                            balance = data.get("balance", 0)
                            return f"{balance:.2f}"  # Возвращаем баланс как строку
                        else:
                            # Логируем сообщение об ошибке от API
                            log.warning(f"SubGram API error message: {data.get('message', 'Unknown error')}")
                            return "Ошибка API"
                    except aiohttp.ContentTypeError:
                        # Если ответ не JSON (например, HTML страница обслуживания)
                        log.warning(
                            f"SubGram API returned non-JSON response (status {response.status}). Body: {response_text[:200]}")
                        return "Тех. работы?"
                else:
                    # Если статус не 200 OK
                    log.error(f"SubGram API request failed with status {response.status}. Body: {response_text[:200]}")
                    return "Ошибка запроса"
    except asyncio.TimeoutError:
        log.error("SubGram API connection timeout.")
        return "Таймаут"
    except aiohttp.ClientConnectorError as e:
        log.error(f"SubGram API connection error: {e}")
        return "Ошибка сети"
    except Exception as e:
        log.exception(f"Unexpected error getting SubGram balance: {e}")
        return "Неизвестная ошибка"


async def get_sponsors(user_id: int, chat_id: int = None) -> list | None:
    """
    Получает список спонсоров из SubGram API (POST /get-sponsors).
    Требует SUBGRAM_BOT_API_KEY (ключ бота).
    Возвращает список словарей с данными спонсоров или None при ошибке.
    """
    if not SUBGRAM_BOT_API_KEY:
        log.debug("SUBGRAM_BOT_API_KEY not configured, skipping get-sponsors.")
        return None

    headers = {
        'Auth': SUBGRAM_BOT_API_KEY,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    url = "https://api.subgram.org/get-sponsors"
    payload = {
        'user_id': user_id,
        'chat_id': chat_id or user_id,
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response_text = await response.text()
                log.debug(f"SubGram get-sponsors response for {user_id}: status={response.status}, body={response_text[:500]}")

                try:
                    data = await response.json(content_type=None)
                except Exception:
                    log.warning(f"SubGram get-sponsors returned non-JSON. Body: {response_text[:200]}")
                    return None

                status = data.get("status")
                code = data.get("code", response.status)

                if status == "ok" and code == 200:
                    # Спонсоры могут быть в поле "result", "response", "sponsors" или "links"
                    sponsors = data.get("result") or data.get("response") or data.get("sponsors") or data.get("links") or []
                    if isinstance(sponsors, list) and sponsors:
                        log.info(f"SubGram get-sponsors for user {user_id}: got {len(sponsors)} sponsor(s).")
                        return sponsors
                    else:
                        log.debug(f"SubGram get-sponsors for user {user_id}: no sponsors returned (user passed).")
                        return []
                elif code == 400:
                    # ОП приостановлена или другая бизнес-ошибка
                    log.warning(f"SubGram get-sponsors business error for {user_id}: {data.get('message', '')}")
                    return None
                else:
                    log.warning(f"SubGram get-sponsors error: {data.get('message', 'Unknown')} (code={code})")
                    return None

    except asyncio.TimeoutError:
        log.error(f"SubGram get-sponsors timeout for user {user_id}.")
        return None
    except aiohttp.ClientConnectorError as e:
        log.error(f"SubGram get-sponsors connection error for user {user_id}: {e}")
        return None
    except Exception as e:
        log.exception(f"Unexpected error in get_sponsors for user {user_id}: {e}")
        return None


def format_datetime(dt_str):
    """Форматирует строку времени в читаемый вид DD/MM/YY HH:MM."""
    if not dt_str:
        return "—"  # Возвращаем прочерк для пустых значений
    # Список форматов для попытки парсинга
    formats_to_try = [
        "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO с таймзоной (со смещением)
        "%Y-%m-%dT%H:%M:%S%z",  # ISO с таймзоной (без микросекунд)
        "%Y-%m-%dT%H:%M:%S.%f",  # ISO без таймзоны (с микросекундами)
        "%Y-%m-%dT%H:%M:%S",  # ISO без таймзоны (без микросекунд)
        "%Y-%m-%d %H:%M:%S.%f",  # SQL Server / др. формат
        "%Y-%m-%d %H:%M:%S",  # Стандартный SQL / SQLite формат
        "%Y-%m-%d_%H-%M-%S"  # Формат из бэкапов/generate_filename
    ]
    dt_obj = None
    for fmt in formats_to_try:
        try:
            dt_obj = datetime.strptime(dt_str, fmt)
            break  # Успешно распарсили, выходим из цикла
        except ValueError:
            continue  # Пробуем следующий формат
        except Exception as e:  # Ловим другие возможные ошибки парсинга
            log.error(f"Unexpected error parsing datetime string '{dt_str}' with format '{fmt}': {e}")
            continue

    if dt_obj:
        # Форматируем в нужный вид
        return dt_obj.strftime("%d/%m/%y %H:%M")
    else:
        # Если ни один формат не подошел, возвращаем исходную строку
        log.warning(f"Could not parse datetime string: '{dt_str}' with known formats.")
        return dt_str


def generate_filename(prefix: str, extension: str = "txt") -> str:
    """Генерирует имя файла с временной меткой в папке exports."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if not extension.startswith('.'):
        extension = '.' + extension

    export_dir = "exports"
    try:
        # Создаем папку 'exports', если ее нет
        os.makedirs(export_dir, exist_ok=True)
        # Возвращаем полный путь к файлу
        return os.path.join(export_dir, f"{prefix}_{timestamp}{extension}")
    except OSError as e:
        # В случае ошибки создания папки, логируем и возвращаем имя файла без пути
        log.error(f"Could not create directory '{export_dir}': {e}. Returning filename only.")
        return f"{prefix}_{timestamp}{extension}"


# --- НОВОЕ: Функция валидации initData ---
def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Проверяет подлинность данных инициализации Mini App (initData).

    :param init_data: Строка initData, полученная от Telegram.WebApp.initData
    :param bot_token: Токен вашего Telegram-бота.
    :return: Словарь с данными пользователя и другими параметрами, если валидация прошла, иначе None.
    """
    log.debug(f"Validating initData (first 100 chars): {init_data[:100]}...")
    try:
        # Разбираем строку initData на ключ-значение
        parsed_data = dict(parse_qsl(init_data))
    except Exception as e:
        log.error(f"Failed to parse initData string: {e}")
        return None  # Ошибка парсинга

    if "hash" not in parsed_data:
        log.error("Validation Error: Hash not found in initData")
        return None  # Отсутствует обязательное поле hash

    if "auth_date" not in parsed_data:
        log.error("Validation Error: auth_date not found in initData")
        return None  # Отсутствует обязательное поле auth_date

    # Проверка времени авторизации (например, не старше 24 часов = 86400 секунд)
    try:
        auth_date_ts = int(parsed_data["auth_date"])
        current_ts = int(datetime.now(timezone.utc).timestamp())
        if current_ts - auth_date_ts > 86400:  # 24 часа
            # Это предупреждение, а не ошибка, т.к. данные все еще могут быть валидными
            log.warning(f"initData is older than 24 hours: auth_date={auth_date_ts}, current={current_ts}")
            # Решите, возвращать ли None при старых данных. Пока оставляем для прохождения валидации хеша.
            # return None
    except ValueError:
        log.error("Validation Error: Invalid auth_date format in initData")
        return None  # Неверный формат времени

    # Сохраняем хеш из Telegram и удаляем его из словаря для проверки
    hash_from_telegram = parsed_data.pop("hash")

    # Формируем строку для проверки хеша: поля key=value, отсортированные по ключу, через \n
    # Важно использовать unquote для значений перед сортировкой, как рекомендует документация TG
    # Но сначала проверим без unquote, так как parse_qsl уже мог это сделать
    # items_for_hash = sorted(parsed_data.items()) # Сортируем по ключу
    # data_check_arr = [f"{key}={value}" for key, value in items_for_hash]

    # Альтернативный способ формирования строки (как в документации)
    data_check_arr = []
    for key, value in sorted(parsed_data.items()):  # Сортируем по ключу
        data_check_arr.append(f"{key}={value}")
    data_check_string = "\n".join(data_check_arr)

    log.debug(f"Data check string for hash validation:\n{data_check_string}")

    # Вычисляем хеш
    try:
        # Ключ для HMAC генерируется из токена бота
        secret_key = hmac.new("WebAppData".encode(), bot_token.encode(), hashlib.sha256).digest()
        # Считаем HMAC-SHA256 от строки data_check_string
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        log.debug(f"Calculated hash: {calculated_hash}")
        log.debug(f"Hash from Telegram: {hash_from_telegram}")
    except Exception as e:
        log.error(f"Error calculating hash: {e}")
        return None  # Ошибка при вычислении

    # Сравниваем хеши
    if calculated_hash == hash_from_telegram:
        log.info("initData validation SUCCESS")
        # Дополнительно парсим поле 'user', если оно есть
        if 'user' in parsed_data:
            try:
                # Значение поля 'user' может быть URL-кодированным JSON
                user_data_str = unquote(parsed_data['user'])
                parsed_data['user'] = json.loads(user_data_str)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                log.error(f"Failed to parse 'user' field JSON in initData: {e}")
                # Решите, что делать: удалить поле user или вернуть None
                # del parsed_data['user'] # Вариант: удалить некорректное поле
                # return None # Вариант: считать всю валидацию неуспешной
        return parsed_data  # Возвращаем словарь со всеми данными (включая user как словарь)
    else:
        log.error("initData validation FAILED: Hash mismatch")
        return None  # Хеши не совпали
