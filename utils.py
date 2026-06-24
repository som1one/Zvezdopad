import logging
import aiohttp
from datetime import datetime, timedelta, timezone
from html import escape
import asyncio
import os
import hmac
import hashlib
import json
from urllib.parse import parse_qsl, unquote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram import Bot
import asyncpg

import database
from settings import REQUEST_API_KEY, ADMIN_IDS, AVAILABLE_LANGS, TOKEN
from texts import TEXTS

log = logging.getLogger('utils')
adverts_log = logging.getLogger('adverts')


async def show_advert(user_id: int):
    gramads_token = os.environ.get("GRAMADS_TOKEN")
    if not gramads_token:
        adverts_log.warning("Gramads token not configured in environment variables (GRAMADS_TOKEN). Skipping advert.")
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post('https://api.gramads.net/ad/SendPost',
                                    headers={'Authorization': f'Bearer {gramads_token}',
                                             'Content-Type': 'application/json'},
                                    json={'SendToChatId': user_id},
                                    timeout=aiohttp.ClientTimeout(total=5)) as response:
                response_text = await response.text()
                if not response.ok:
                    try:
                        error_details = await response.json()
                    except aiohttp.ContentTypeError:
                        error_details = response_text[:500]
                    adverts_log.error(f'Gramads API Error ({response.status}) user {user_id}: {error_details}')
    except asyncio.TimeoutError:
        adverts_log.error(f"Gramads timeout user {user_id}.")
    except aiohttp.ClientConnectorError as e:
        adverts_log.error(f"Gramads connection error user {user_id}: {e}")
    except Exception as e:
        adverts_log.exception(f"Unexpected error showing advert user {user_id}: {e}")


_lang_cache = {}
_cache_ttl = timedelta(minutes=5)
_last_cache_clear = datetime.min


def t(user_id, key):
    global _last_cache_clear, _lang_cache
    now = datetime.now()
    if now - _last_cache_clear > _cache_ttl:
        _lang_cache = {}
        _last_cache_clear = now
        log.debug("Language cache cleared.")

    lang = _lang_cache.get(user_id)
    if lang is None:
        log.warning(f"Language for user {user_id} not in cache. Using 'ru'. Call async get_user_lang elsewhere.")
        lang = 'ru'

    if lang not in TEXTS: lang = 'ru'
    return TEXTS[lang].get(key, f"MISSING_TEXT_{key}")


def get_language_markup():
    markup = InlineKeyboardMarkup(row_width=1)
    for lang_code in AVAILABLE_LANGS:
        lang_name = TEXTS.get(lang_code, {}).get(f'lang_{lang_code}', lang_code.upper())
        button = InlineKeyboardButton(text=lang_name, callback_data=f"set_lang:{lang_code}")
        markup.add(button)
    return markup


def mask_id(user_id):
    user_id_str = str(user_id)
    return user_id_str[:-3] + "***" if len(user_id_str) > 3 else user_id_str


def mask_username(username):
    if username and len(username) > 3: return username[:-3] + "***"
    return username


def sanitize_username(username):
    if not username: return "unknown"
    return escape(username.replace("<", "").replace(">", ""))


async def get_user_info(bot: Bot, user_id):
    try:
        user = await bot.get_chat(user_id)
        full_name = user.full_name or user.first_name or "Без имени"
        username = user.username
        return full_name, username
    except Exception as e:
        log.error(f"Error retrieving user info {user_id} API: {e}");
        return "Неизвестный", None


async def create_temp_invite_link(bot: Bot, channel_id: int):
    try:
        invite_link = await bot.create_chat_invite_link(channel_id, member_limit=1)
        return invite_link.invite_link
    except Exception as e:
        log.warning(f"Could not create temp invite link {channel_id}: {e}. Trying fallback.")
        try:
            numeric_channel_id = int(
                str(channel_id).replace('-100', ''));
            return f"https://t.me/c/{numeric_channel_id}/1"
        except ValueError:
            log.error(
                f"Could not create fallback link non-numeric {channel_id}");
            return f"tg://resolve?domain=error_chat_{channel_id}"


async def send_gift_with_retry(app, user_id, star_gift_id, retries=0, max_retries=1,
                               bot_instance: Bot = None):
    try:
        if not user_id or not star_gift_id: raise ValueError("User ID and Star Gift ID cannot be None.")
        log.info(f"Attempting send gift {star_gift_id} to user {user_id}...")
        await app.send_gift(chat_id=int(user_id), gift_id=int(star_gift_id))
        log.info(f"Gift sent successfully {user_id} (Gift ID: {star_gift_id})")
        return True
    except Exception as e:
        log.error(f"Error sending gift to {user_id} (Gift ID: {star_gift_id}, Attempt: {retries + 1}): {e}")
        if "BALANCE_TOO_LOW" in str(e):
            log.critical(f"Pyrogram balance too low send gift {star_gift_id} user {user_id}")
            if bot_instance:
                pyro_username = "???"
                try:
                    me = await app.get_me();
                    pyro_username = me.username if me else "???"
                except Exception:
                    pass
                for admin_id in ADMIN_IDS:
                    try:
                        await bot_instance.send_message(admin_id,
                                                        f"⚠️ Недостаточно средств Pyrogram (@{pyro_username}) для подарка {star_gift_id} юзеру {user_id}!")
                    except Exception as admin_notify_err:
                        log.error(f"Failed notify admin {admin_id} low balance: {admin_notify_err}")
            raise e
        elif retries < max_retries:
            wait_time = 5
            log.warning(f"Retrying gift send {user_id} in {wait_time}s... (Attempt {retries + 2}/{max_retries + 1})")
            await asyncio.sleep(wait_time)
            return await send_gift_with_retry(app, user_id, star_gift_id, retries + 1, max_retries,
                                              bot_instance)
        else:
            log.error(f"Failed send gift {user_id} after {max_retries + 1} attempts.")
            raise e


async def get_subbalance():
    if not REQUEST_API_KEY or "YOUR" in REQUEST_API_KEY: log.warning(
        "SubGram API key not configured."); return "Ключ не задан"
    headers = {'Auth': REQUEST_API_KEY};
    url = "https://api.subgram.ru/get-balance/"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, headers=headers) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        data = await response.json()
                        if data.get("status") == "ok":
                            return f"{data.get('balance', 0):.2f}"
                        else:
                            log.warning(f"SubGram API error: {data.get('message', 'Unknown')}");
                            return "Ошибка API"
                    except aiohttp.ContentTypeError:
                        log.warning(
                            f"SubGram non-JSON response ({response.status}). Body: {response_text[:200]}");
                        return "Тех. работы?"
                else:
                    log.error(
                        f"SubGram API fail status {response.status}. Body: {response_text[:200]}");
                    return "Ошибка запроса"
    except asyncio.TimeoutError:
        log.error("SubGram API timeout.");
        return "Таймаут"
    except aiohttp.ClientConnectorError as e:
        log.error(f"SubGram connection error: {e}");
        return "Ошибка сети"
    except Exception as e:
        log.exception(f"Unexpected error getting SubGram balance: {e}");
        return "Неизв. ошибка"


async def get_sponsors(user_id: int, chat_id: int = None) -> list | None:
    """
    Получает список спонсоров из SubGram API (POST /get-sponsors).
    Возвращает список спонсоров или None при ошибке.
    """
    if not REQUEST_API_KEY or "YOUR" in REQUEST_API_KEY:
        log.debug("SubGram API key not configured, skipping get-sponsors.")
        return None

    headers = {
        'Auth': REQUEST_API_KEY,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    url = "https://api.subgram.org/get-sponsors"
    payload = {'user_id': user_id, 'chat_id': chat_id or user_id}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response_text = await response.text()
                log.debug(f"SubGram get-sponsors for {user_id}: status={response.status}, body={response_text[:500]}")

                try:
                    data = await response.json(content_type=None)
                except Exception:
                    log.warning(f"SubGram get-sponsors non-JSON. Body: {response_text[:200]}")
                    return None

                status = data.get("status")
                code = data.get("code", response.status)

                if status == "ok" and code == 200:
                    sponsors = data.get("result") or data.get("response") or data.get("sponsors") or data.get("links") or []
                    if isinstance(sponsors, list) and sponsors:
                        log.info(f"SubGram get-sponsors for {user_id}: got {len(sponsors)} sponsor(s).")
                        return sponsors
                    else:
                        log.debug(f"SubGram get-sponsors for {user_id}: no sponsors (user passed).")
                        return []
                elif code == 400:
                    log.warning(f"SubGram get-sponsors business error for {user_id}: {data.get('message', '')}")
                    return None
                else:
                    log.warning(f"SubGram get-sponsors error: {data.get('message', 'Unknown')} (code={code})")
                    return None

    except asyncio.TimeoutError:
        log.error(f"SubGram get-sponsors timeout for {user_id}.")
        return None
    except aiohttp.ClientConnectorError as e:
        log.error(f"SubGram get-sponsors connection error for {user_id}: {e}")
        return None
    except Exception as e:
        log.exception(f"Unexpected error in get_sponsors for {user_id}: {e}")
        return None


def format_datetime(dt_input):
    if not dt_input: return "—"
    dt_obj = None
    if isinstance(dt_input, datetime):
        dt_obj = dt_input
    elif isinstance(dt_input, str):
        formats_to_try = ["%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                          "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d_%H-%M-%S"]
        for fmt in formats_to_try:
            try:
                dt_obj = datetime.strptime(dt_input, fmt);
                break
            except ValueError:
                continue
            except Exception as e:
                log.error(f"Error parsing dt string '{dt_input}' fmt '{fmt}': {e}");
                continue
    else:
        try:
            dt_obj = datetime.fromtimestamp(float(dt_input), tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            pass

    if dt_obj:
        try:
            local_dt = dt_obj.astimezone()
        except ValueError:
            local_dt = dt_obj
        return local_dt.strftime("%d/%m/%y %H:%M")
    else:
        log.warning(f"Could not format datetime: '{dt_input}'");
        return str(dt_input)


def generate_filename(prefix: str, extension: str = "txt") -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    if not extension.startswith('.'): extension = '.' + extension
    export_dir = "exports"
    try:
        os.makedirs(export_dir, exist_ok=True)
        return os.path.join(export_dir, f"{prefix}_{timestamp}{extension}")
    except OSError as e:
        log.error(f"Could not create dir '{export_dir}': {e}.");
        return f"{prefix}_{timestamp}{extension}"


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    log.debug(f"Validating initData: {init_data[:100]}...")
    try:
        parsed_data = dict(parse_qsl(init_data))
    except Exception as e:
        log.error(f"Failed parse initData: {e}");
        return None

    if "hash" not in parsed_data: log.error("Validation Error: Hash not found"); return None
    if "auth_date" not in parsed_data: log.error("Validation Error: auth_date not found"); return None

    try:
        auth_date_ts = int(parsed_data["auth_date"])
        current_ts = int(datetime.now(timezone.utc).timestamp())
        if current_ts - auth_date_ts > 86400: log.warning(
            f"initData older than 24h: auth={auth_date_ts}, now={current_ts}")
    except ValueError:
        log.error("Validation Error: Invalid auth_date format");
        return None

    hash_from_telegram = parsed_data.pop("hash")
    data_check_arr = [f"{key}={value}" for key, value in sorted(parsed_data.items())]
    data_check_string = "\n".join(data_check_arr)
    log.debug(f"Data check string:\n{data_check_string}")

    try:
        secret_key = hmac.new("WebAppData".encode(), bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        log.debug(f"Calculated hash: {calculated_hash}")
        log.debug(f"Telegram hash: {hash_from_telegram}")
    except Exception as e:
        log.error(f"Error calculating hash: {e}");
        return None

    if calculated_hash == hash_from_telegram:
        log.info("initData validation SUCCESS")
        if 'user' in parsed_data:
            try:
                user_data_str = unquote(parsed_data['user']);
                parsed_data['user'] = json.loads(user_data_str)
            except Exception as e:
                log.error(f"Failed parse 'user' field JSON: {e}")
        return parsed_data
    else:
        log.error("initData validation FAILED: Hash mismatch");
        return None
