import asyncio
import json
import logging
import asyncpg
import uuid
import random
import time
from datetime import datetime, timedelta, timezone
from html import escape

from aiohttp import web
from aiogram import Bot

import database
from database import (
    get_wheel_referral_req, get_wheel_daily_limit, get_referrals_count_week,
    get_daily_withdrawal_count, increment_daily_withdrawal_count,
    are_withdrawals_enabled, add_stars, get_user,
    get_users_balance, get_last_free_spin_time,
    create_wheel_win_request, add_game_history_record, get_user_username,
    get_game_history, get_user_withdrawals, is_user_blocked,
    get_referrals_count, get_last_robbery_time,
    update_last_robbery_time,
    get_random_user,
    get_active_luck_boost_percentage
)
from settings import (
    FREE_SPIN_COOLDOWN_SECONDS, TOKEN, ADMIN_IDS, SUP_LOGIN,
    CHANEL_ID, LOG_VIVOD_CHANEL, FREE_SPIN_COST_EQUIVALENT,
    WIN_CHANCE, WIN_CHANEL_ID
)
from utils import validate_init_data, format_datetime, t, mask_id
from keyboards import create_admin_withdrawal_markup
# Импорт p_settings для названий бустов
from payment_bot import payment_bot_settings as p_settings

log_api_notify = logging.getLogger('handlers.api.notify')
log = logging.getLogger('handlers.api')

active_spins = {}
SPIN_TIMEOUT_SECONDS = 120

items_config = [
    {"name": "Шампанское", "emoji": "🍾", "costNumber": 50, "distribution": {25: 0.758, 50: 12.5, 100: 5.82},
     "canSell": True},
    {"name": "Кольцо", "emoji": "💍", "costNumber": 100, "distribution": {25: 0.379, 50: 0.833, 100: 11.64},
     "canSell": True},
    {"name": "Свеча", "emoji": "🕯️", "costNumber": 350, "distribution": {25: 0.758, 50: 1.67, 100: 5.47},
     "canSell": False},
    {"name": "100 Звезд", "emoji": "⭐", "costNumber": 100, "distribution": {25: 0.379, 50: 0.833, 100: 11.64},
     "canSell": False},
    {"name": "Букет", "emoji": "💐", "costNumber": 50, "distribution": {25: 0.758, 50: 12.5, 100: 5.82},
     "canSell": True},
    {"name": "Бриллиант", "emoji": "💎", "costNumber": 100, "distribution": {25: 0.379, 50: 0.833, 100: 11.64},
     "canSell": True},
    {"name": "Ракета", "emoji": "🚀", "costNumber": 50, "distribution": {25: 0.758, 50: 12.5, 100: 5.82},
     "canSell": True},
    {"name": "Сердце", "emoji": "💝", "costNumber": 15, "distribution": {25: 22.35, 50: 8.09, 100: 3.49},
     "canSell": True},
    {"name": "Мишка", "emoji": "🧸", "costNumber": 15, "distribution": {25: 22.35, 50: 8.09, 100: 3.49},
     "canSell": True},
    {"name": "Подарок", "emoji": "🎁", "costNumber": 25, "distribution": {25: 25.0, 50: 13.49, 100: 5.82},
     "canSell": True},
    {"name": "Кубок", "emoji": "🏆", "costNumber": 100, "distribution": {25: 0.379, 50: 0.833, 100: 11.64},
     "canSell": True},
    {"name": "Роза", "emoji": "🌹", "costNumber": 25, "distribution": {25: 25.0, 50: 13.49, 100: 5.82}, "canSell": True},
    {"name": "Торт", "emoji": "🎂", "costNumber": 50, "distribution": {25: 0.758, 50: 12.5, 100: 5.82}, "canSell": True}
]
WHEEL_GIFT_MAP = {item['emoji']: item['costNumber'] for item in items_config if item.get('canSell')}
WHEEL_DIRECT_ADD_COST = {item['emoji']: item['costNumber'] for item in items_config if not item.get('canSell')}


def build_sectors_server(cost):
    return [{**item, 'weight': item['distribution'].get(cost, 0)} for item in items_config]


def weighted_random_server(sector_array, weight_total):
    if weight_total <= 0 or not sector_array: return -1
    r = random.random() * weight_total
    w = 0
    for i, sector in enumerate(sector_array):
        cW = sector.get('weight', 0)
        if cW <= 0: continue
        w += cW
        if r < w: return i
    for i in range(len(sector_array) - 1, -1, -1):
        if sector_array[i].get('weight', 0) > 0: return i
    return -1


async def send_wheel_win_to_admins(bot: Bot, request_id: int, user_id: int, user_name: str,
                                   prize_name: str, amount: float, emoji: str):
    user_mention = f"<a href='tg://user?id={user_id}'>{escape(user_name or f'ID: {user_id}')}</a>"

    channel_text = (
        f"🎡 <b>Заявка с Колеса Фортуны №{request_id}</b>\n\n"
        f"👤 Пользователь: {user_mention} (<code>{user_id}</code>)\n"
        f"🏆 <b>Приз:</b> {escape(prize_name)} {emoji}\n"
        f"💰 <b>Сумма (эквивалент):</b> {amount:.0f} ⭐"
    )
    markup = create_admin_withdrawal_markup(user_id, amount, emoji, request_id)

    if CHANEL_ID:
        try:
            await bot.send_message(CHANEL_ID, channel_text, reply_markup=markup, parse_mode="HTML")
            log_api_notify.info(f"Sent wheel withdrawal request {request_id} message to main channel {CHANEL_ID}.")
        except Exception as e:
            log_api_notify.error(f"Failed send wheel win request {request_id} to main channel {CHANEL_ID}: {e}")
    else:
        log_api_notify.warning("CHANEL_ID not set in settings. Cannot send wheel win notification.")


async def handle_get_user_state(request: web.Request):
    start_time = time.monotonic()
    bot: Bot = request.app['bot']
    user_id = None
    headers = {'Access-Control-Allow-Origin': '*'}
    try:
        post_data = await request.json()
        init_data_str = post_data.get('initData')
        if not init_data_str:
            return web.json_response({'ok': False, 'error': 'Missing initData'}, status=400, headers=headers)

        validated_data = validate_init_data(init_data_str, TOKEN)

        if not validated_data or 'user' not in validated_data:
            return web.json_response({'ok': False, 'error': 'Invalid initData'}, status=403, headers=headers)

        user_info = validated_data['user']
        user_id = user_info.get('id')
        user_photo_url = user_info.get('photo_url')

        if not user_id: raise ValueError("User ID missing")

        user_data = await database.get_user(user_id)
        withdrawal_requirement = await database.get_exchange_referral_req()

        active_boost_info_list = []
        now_utc = datetime.now(timezone.utc)

        active_speed_boosts = await database.get_active_boosts_by_type(user_id, "speed_boost")
        active_luck_boosts = await database.get_active_boosts_by_type(user_id, "luck_boost")

        if active_speed_boosts:
            for boost in active_speed_boosts:
                if boost['expiration_time'] > now_utc and boost['is_active']:
                    boost_name = p_settings.BOOST_OPTIONS.get(boost['boost_id_key'], {}).get('name', 'Ускоритель')
                    active_boost_info_list.append({
                        "type_key": boost['boost_id_key'],
                        "type_name": boost_name,
                        "expires_at_iso": boost['expiration_time'].isoformat() if boost['expiration_time'] else None,
                    })
        if active_luck_boosts:
            for boost in active_luck_boosts:
                if boost['expiration_time'] > now_utc and boost['is_active']:
                    boost_name = p_settings.BOOST_OPTIONS.get(boost['boost_id_key'], {}).get('name', 'Эликсир Удачи')
                    active_boost_info_list.append({
                        "type_key": boost['boost_id_key'],
                        "type_name": boost_name,
                        "expires_at_iso": boost['expiration_time'].isoformat() if boost['expiration_time'] else None,
                    })

        if not user_data:
            response_data = {
                'ok': True, 'balance': 0.0, 'freeSpin': True, 'cooldown': None,
                'total_referrals': 0, 'weekly_referrals': 0,
                'withdrawal_requirement': withdrawal_requirement,
                'withdrawal_history': [], 'user_id': user_id,
                'username': user_info.get('username', f"id_{user_id}"),
                'photo_url': user_photo_url, 'robbery_cooldown_left': 0,
                'active_boosts': active_boost_info_list
            }
        else:
            balance = user_data['stars']
            last_spin_time_db = user_data['last_free_spin_time']
            db_username = user_data['username']
            total_referrals = await database.get_referrals_count(user_id)
            weekly_referrals = await database.get_referrals_count_week(user_id)
            withdrawal_history_raw = await database.get_user_withdrawals(user_id, limit=5)
            last_robbery_time = await database.get_last_robbery_time(user_id)

            robbery_cooldown_left = 0
            if last_robbery_time:
                robbery_cooldown_delta = timedelta(hours=12)
                now_dt_aware = datetime.now(timezone.utc)
                if last_robbery_time.tzinfo is None:
                    last_robbery_time = last_robbery_time.replace(tzinfo=timezone.utc)
                time_since_last = now_dt_aware - last_robbery_time
                if time_since_last < robbery_cooldown_delta:
                    remaining = robbery_cooldown_delta - time_since_last
                    robbery_cooldown_left = int(remaining.total_seconds())

            is_free = False
            cooldown_ts = None
            if last_spin_time_db:
                cooldown_end_dt_utc = last_spin_time_db + timedelta(seconds=FREE_SPIN_COOLDOWN_SECONDS)
                now_utc_check = datetime.now(timezone.utc)
                if now_utc_check >= cooldown_end_dt_utc:
                    is_free = True
                else:
                    cooldown_ts = int(cooldown_end_dt_utc.timestamp())
            else:
                is_free = True

            withdrawal_history = []
            for item in withdrawal_history_raw:
                timestamp_sec = None
                request_time_db = item['request_time']
                if request_time_db:
                    timestamp_sec = int(request_time_db.timestamp())
                withdrawal_history.append({
                    "amount": item['amount'],
                    "status": item['status'],
                    "timestamp": timestamp_sec
                })

            response_data = {
                'ok': True, 'balance': balance, 'freeSpin': is_free, 'cooldown': cooldown_ts,
                'total_referrals': total_referrals, 'weekly_referrals': weekly_referrals,
                'withdrawal_requirement': withdrawal_requirement,
                'withdrawal_history': withdrawal_history, 'user_id': user_id,
                'username': db_username, 'photo_url': user_photo_url,
                'robbery_cooldown_left': robbery_cooldown_left,
                'active_boosts': active_boost_info_list
            }
        return web.json_response(response_data, headers=headers)

    except ValueError as ve:
        return web.json_response({'ok': False, 'error': str(ve)}, status=400, headers=headers)
    except asyncpg.PostgresError as db_err:
        return web.json_response({'ok': False, 'error': 'Ошибка базы данных'}, status=500, headers=headers)
    except Exception as e:
        return web.json_response({'ok': False, 'error': 'Внутренняя ошибка сервера'}, status=500, headers=headers)


async def handle_start_spin(request: web.Request):
    start_time = time.monotonic()
    bot: Bot = request.app['bot']
    user_id = None
    user_name = "unknown"
    headers = {'Access-Control-Allow-Origin': '*'}
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 0.05
    try:
        post_data = await request.json()
        init_data_str = post_data.get('initData')
        requested_cost_str = post_data.get('cost')

        if not init_data_str or not requested_cost_str:
            return web.json_response({'ok': False, 'error': 'Missing data', 'reason': 'bad_request'}, status=400,
                                     headers=headers)

        validated_data = validate_init_data(init_data_str, TOKEN)

        if not validated_data or 'user' not in validated_data:
            return web.json_response({'ok': False, 'error': 'Invalid initData', 'reason': 'invalid_initdata'},
                                     status=403, headers=headers)

        user_info = validated_data['user']
        user_id = user_info.get('id')
        user_name = user_info.get('username', f"id_{user_id}")
        if not user_id: raise ValueError("User ID missing")

        is_free = (requested_cost_str == 'free')
        spin_cost = 0
        probability_cost = FREE_SPIN_COST_EQUIVALENT

        if not is_free:
            try:
                spin_cost = int(requested_cost_str)
                probability_cost = spin_cost
                if spin_cost not in [25, 50, 100]: raise ValueError("Invalid cost value")
            except (ValueError, TypeError):
                return web.json_response({'ok': False, 'error': 'Неверная стоимость спина', 'reason': 'invalid_cost'},
                                         status=400, headers=headers)

        is_blocked = await database.is_user_blocked(user_id)
        if is_blocked:
            return web.json_response({'ok': False, 'error': 'Пользователь заблокирован', 'reason': 'user_blocked'},
                                     status=403, headers=headers)

        balance_after_cost = -1.0
        winning_prize_data = None
        winning_prize_index = -1
        spin_uuid = str(uuid.uuid4())
        last_exception = None

        for attempt in range(MAX_RETRIES):
            pool = database.db_pool
            if not pool: raise RuntimeError("DB pool not initialized")
            conn = None
            try:
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        user_state = await conn.fetchrow(
                            "SELECT stars, last_free_spin_time FROM users WHERE id = $1 FOR UPDATE", user_id)
                        if not user_state: raise ValueError("user_not_found")
                        current_balance = user_state['stars']

                        if is_free:
                            last_spin_time_db = user_state['last_free_spin_time']
                            if last_spin_time_db:
                                if datetime.now(timezone.utc) < (
                                        last_spin_time_db + timedelta(seconds=FREE_SPIN_COOLDOWN_SECONDS)):
                                    raise ValueError("cooldown")
                            now_utc = datetime.now(timezone.utc)
                            await conn.execute("UPDATE users SET last_free_spin_time = $1 WHERE id = $2", now_utc,
                                               user_id)
                            balance_after_cost = current_balance
                        else:
                            if current_balance < spin_cost: raise ValueError("low_balance")
                            balance_after_cost = current_balance - spin_cost
                            await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", balance_after_cost, user_id)

                        sectors = build_sectors_server(probability_cost)
                        total_weight = sum(s.get('weight', 0) for s in sectors)
                        if total_weight <= 0: raise RuntimeError(f"Zero weight config cost {probability_cost}")

                        winning_prize_index = weighted_random_server(sectors, total_weight)
                        if winning_prize_index < 0 or winning_prize_index >= len(items_config): raise RuntimeError(
                            f"Invalid prize index {winning_prize_index}")
                        winning_prize_data = items_config[winning_prize_index]

                if not is_free:
                    asyncio.create_task(
                        database.add_game_history_record(user_id, 'wheel', -spin_cost, "Ставка в Колесе"))

                active_spins[spin_uuid] = {"user_id": user_id, "prize": winning_prize_data, "cost": spin_cost,
                                           "is_free": is_free, "timestamp": time.time()}

                response_data = {
                    'ok': True, 'spin_id': spin_uuid,
                    'winning_prize': {'index': winning_prize_index, 'name': winning_prize_data['name'],
                                      'emoji': winning_prize_data['emoji'],
                                      'costNumber': winning_prize_data['costNumber'],
                                      'canSell': winning_prize_data['canSell']},
                    'new_balance': balance_after_cost
                }
                return web.json_response(response_data, headers=headers)

            except (asyncpg.exceptions.DeadlockDetectedError, asyncpg.exceptions.CannotConnectNowError,
                    asyncpg.exceptions.InterfaceError) as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(0, INITIAL_RETRY_DELAY * 0.5)
                    await asyncio.sleep(delay)
                    continue
                else:
                    return web.json_response(
                        {'ok': False, 'error': 'База данных временно недоступна, попробуйте еще раз.',
                         'reason': 'db_locked'}, status=503, headers=headers)
            except ValueError as ve:
                reason = str(ve)
                error_msg = "Бесплатный спин недоступен" if reason == "cooldown" else f"Недостаточно средств ({spin_cost:.0f}⭐)" if reason == "low_balance" else "Пользователь не найден" if reason == "user_not_found" else "Неизвестная ошибка значения"
                return web.json_response({'ok': False, 'error': error_msg, 'reason': reason}, status=400,
                                         headers=headers)
            except asyncpg.PostgresError as db_err:
                last_exception = db_err
                return web.json_response({'ok': False, 'error': 'Ошибка БД при старте спина', 'reason': 'db_error'},
                                         status=500, headers=headers)
            except Exception as game_err:
                last_exception = game_err
                return web.json_response({'ok': False, 'error': 'Ошибка логики старта спина', 'reason': 'game_error'},
                                         status=500, headers=headers)
            finally:
                pass

        return web.json_response({'ok': False, 'error': 'Не удалось начать спин после нескольких попыток.',
                                  'reason': 'max_retries_exceeded'}, status=500, headers=headers)

    except ValueError as ve:
        return web.json_response({'ok': False, 'error': str(ve), 'reason': 'bad_request'}, status=400, headers=headers)
    except Exception as e:
        return web.json_response({'ok': False, 'error': 'Внутренняя ошибка сервера', 'reason': 'server_error'},
                                 status=500, headers=headers)


async def handle_confirm_spin_action(request: web.Request):
    start_time = time.monotonic()
    bot: Bot = request.app['bot']
    user_id = None
    user_name = "unknown"
    headers = {'Access-Control-Allow-Origin': '*'}
    spin_id = None
    is_free = False
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 0.05
    try:
        post_data = await request.json()
        init_data_str = post_data.get('initData')
        spin_id = post_data.get('spin_id')
        action = post_data.get('action')

        if not init_data_str or not spin_id or action not in ["spin_result", "spin_result_sell"]:
            return web.json_response({'ok': False, 'error': 'Missing/invalid data'}, status=400, headers=headers)

        validated_data = validate_init_data(init_data_str, TOKEN)

        if not validated_data or 'user' not in validated_data:
            return web.json_response({'ok': False, 'error': 'Invalid initData'}, status=403, headers=headers)

        user_info = validated_data['user']
        user_id = user_info.get('id')
        user_name = user_info.get('username', f"id_{user_id}")
        if not user_id: raise ValueError("User ID missing")

        spin_data = active_spins.get(spin_id)
        if not spin_data or time.time() - spin_data.get("timestamp", 0) > SPIN_TIMEOUT_SECONDS:
            if spin_id in active_spins: del active_spins[spin_id]
            return web.json_response({'ok': False, 'error': 'Спин не найден/истек', 'reason': 'spin_expired'},
                                     status=400, headers=headers)

        if spin_data.get("user_id") != user_id:
            return web.json_response({'ok': False, 'error': 'Ошибка ID пользователя', 'reason': 'user_mismatch'},
                                     status=403, headers=headers)

        prize_data = spin_data.get("prize")
        if not prize_data:
            if spin_id in active_spins: del active_spins[spin_id]
            return web.json_response({'ok': False, 'error': 'Ошибка данных спина', 'reason': 'internal_error'},
                                     status=500, headers=headers)

        prize_emoji = prize_data.get("emoji");
        prize_name = prize_data.get("name")
        prize_cost = float(prize_data.get("costNumber", 0));
        can_sell = prize_data.get("canSell", False)
        is_free = spin_data.get("is_free", False)

        request_id_local = None;
        final_user_message_for_bot = "";
        processed_action = action
        balance_after_prize = None;
        history_amount = 0.0;
        history_description = ""
        last_exception = None

        for attempt in range(MAX_RETRIES):
            pool = database.db_pool
            if not pool: raise RuntimeError("DB pool not initialized")
            conn = None
            try:
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        balance_row = await conn.fetchrow("SELECT stars FROM users WHERE id = $1 FOR UPDATE", user_id)
                        if not balance_row: raise ValueError("User not found in DB during confirmation")
                        current_balance = balance_row['stars']
                        balance_after_prize = current_balance

                        is_gift_prize = (prize_emoji in WHEEL_GIFT_MAP and WHEEL_GIFT_MAP.get(prize_emoji) is not None)
                        is_direct_add = prize_emoji in WHEEL_DIRECT_ADD_COST

                        if processed_action == "spin_result" and is_gift_prize:
                            withdrawals_ok = await are_withdrawals_enabled()
                            if not withdrawals_ok:
                                if can_sell and prize_cost > 0:
                                    processed_action = "spin_result_sell"
                                    final_user_message_for_bot = t(user_id,
                                                                   'wheel_prize_autosold_withdrawals_disabled').format(
                                        prize_name=escape(prize_name), emoji=prize_emoji, cost=f"{prize_cost:.0f}")
                                else:
                                    processed_action = "spin_result_forfeit"
                                    final_user_message_for_bot = t(user_id,
                                                                   'wheel_prize_forfeited_withdrawals_disabled').format(
                                        prize_name=escape(prize_name), emoji=prize_emoji)
                            else:
                                wheel_limit = await get_wheel_daily_limit()
                                wheel_count_today = await get_daily_withdrawal_count(user_id, 'wheel')
                                required_refs = await get_wheel_referral_req()
                                current_refs_week = await get_referrals_count_week(user_id)

                                if wheel_count_today >= wheel_limit:
                                    raise ValueError("limit_reached")
                                elif current_refs_week < required_refs:
                                    if can_sell and prize_cost > 0:
                                        processed_action = "spin_result_sell"
                                        final_user_message_for_bot = t(user_id, 'wheel_prize_auto_sold').format(
                                            current=current_refs_week, required=required_refs, cost=f"{prize_cost:.0f}")
                                    else:
                                        processed_action = "spin_result_forfeit"
                                        final_user_message_for_bot = t(user_id,
                                                                       'wheel_prize_cannot_receive_or_sell').format(
                                            current=current_refs_week, required=required_refs)

                        if processed_action == "spin_result_sell":
                            if can_sell and prize_cost > 0:
                                balance_after_prize = current_balance + prize_cost
                                await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", balance_after_prize,
                                                   user_id)
                                history_amount = prize_cost
                                history_description = f"Продажа: {escape(prize_name)} {prize_emoji}"
                                if not final_user_message_for_bot: final_user_message_for_bot = f"💰 Приз {escape(prize_name)}{prize_emoji} продан! +{prize_cost:.0f} ⭐. Баланс: {balance_after_prize:.2f} ⭐."
                            else:
                                processed_action = "spin_result_forfeit";
                                final_user_message_for_bot = f"🚫 Приз {escape(prize_name)}{prize_emoji} нельзя продать, он аннулирован.";
                                balance_after_prize = current_balance
                        elif processed_action == "spin_result":
                            if is_direct_add:
                                add_amount = WHEEL_DIRECT_ADD_COST[prize_emoji]
                                balance_after_prize = current_balance + add_amount
                                await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", balance_after_prize,
                                                   user_id)
                                history_amount = add_amount
                                history_description = f"Выигрыш: {escape(prize_name)} {prize_emoji}"
                                final_user_message_for_bot = f"🎉 Выиграли {escape(prize_name)}{prize_emoji}! +{add_amount:.0f} ⭐. Баланс: {balance_after_prize:.2f} ⭐."
                            elif is_gift_prize:
                                gift_id = WHEEL_GIFT_MAP.get(prize_emoji)
                                if gift_id:
                                    request_id = await create_wheel_win_request(conn, user_id, prize_cost, prize_emoji,
                                                                                gift_id, prize_name)
                                    if request_id:
                                        request_id_local = request_id
                                        if not await database.increment_daily_withdrawal_count(conn, user_id,
                                                                                               'wheel'):
                                            raise Exception("Failed increment daily wheel count.")
                                        balance_after_prize = current_balance
                                        history_amount = 0;
                                        history_description = f"Выигран подарок: {escape(prize_name)} {prize_emoji}"
                                        final_user_message_for_bot = f"🎁 Выиграли {escape(prize_name)}{prize_emoji}! Заявка №{request_id} создана."
                                    else:
                                        raise Exception("Failed create withdrawal request.")
                                else:
                                    processed_action = "spin_result_forfeit";
                                    final_user_message_for_bot = f"🚫 Ошибка конф. приза {escape(prize_name)}{prize_emoji}, он аннулирован.";
                                    balance_after_prize = current_balance
                            else:
                                processed_action = "spin_result_forfeit";
                                final_user_message_for_bot = f"🚫 Приз {escape(prize_name)}{prize_emoji} аннулирован.";
                                balance_after_prize = current_balance
                        elif processed_action == "spin_result_forfeit":
                            if not final_user_message_for_bot: final_user_message_for_bot = f"🚫 Приз {escape(prize_name)}{prize_emoji} аннулирован."
                            balance_after_prize = current_balance;
                            history_description = f"Приз аннулирован: {escape(prize_name)} {prize_emoji}";
                            history_amount = 0

                if history_description:
                    asyncio.create_task(
                        database.add_game_history_record(user_id, 'wheel', history_amount, history_description))

                if spin_id in active_spins: del active_spins[spin_id];

                if final_user_message_for_bot: asyncio.create_task(
                    bot.send_message(user_id, final_user_message_for_bot, parse_mode="HTML"))
                if request_id_local: asyncio.create_task(
                    send_wheel_win_to_admins(bot=bot, request_id=request_id_local, user_id=user_id, user_name=user_name,
                                             prize_name=prize_name, amount=prize_cost, emoji=prize_emoji))

                final_balance = await database.get_users_balance(user_id)

                response_payload = {'ok': True, 'new_balance': final_balance, 'was_free': is_free}
                return web.json_response(response_payload, headers=headers)

            except (asyncpg.exceptions.DeadlockDetectedError, asyncpg.exceptions.CannotConnectNowError,
                    asyncpg.exceptions.InterfaceError) as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(0, INITIAL_RETRY_DELAY * 0.5)
                    await asyncio.sleep(delay);
                    continue
                else:
                    if spin_id in active_spins: del active_spins[spin_id]
                    return web.json_response(
                        {'ok': False, 'error': 'База данных временно недоступна, попробуйте еще раз.',
                         'reason': 'db_locked', 'was_free': is_free}, status=503, headers=headers)
            except ValueError as ve:
                reason = str(ve);
                error_msg_map = {"limit_reached": "Достигнут дневной лимит вывода с Колеса.",
                                 "ref_req_not_met": "Не выполнены условия по рефералам.",
                                 "User not found in DB during confirmation": "Ошибка: пользователь не найден."}
                error_msg = error_msg_map.get(reason, "Ошибка проверки данных.")
                if spin_id in active_spins: del active_spins[spin_id]
                return web.json_response({'ok': False, 'error': error_msg, 'reason': reason, 'was_free': is_free},
                                         status=400, headers=headers)
            except asyncpg.PostgresError as db_err:
                last_exception = db_err
                return web.json_response(
                    {'ok': False, 'error': 'Ошибка БД при обработке приза', 'reason': 'db_error', 'was_free': is_free},
                    status=500, headers=headers)
            except Exception as confirm_err:
                last_exception = confirm_err
                return web.json_response(
                    {'ok': False, 'error': 'Внутренняя ошибка при обработке приза', 'reason': 'server_error',
                     'was_free': is_free}, status=500, headers=headers)
            finally:
                pass

        if spin_id in active_spins: del active_spins[spin_id]
        return web.json_response({'ok': False, 'error': 'Не удалось подтвердить операцию после нескольких попыток.',
                                  'reason': 'max_retries_exceeded', 'was_free': is_free}, status=500, headers=headers)

    except ValueError as ve:
        if spin_id and spin_id in active_spins: del active_spins[spin_id]
        return web.json_response({'ok': False, 'error': str(ve)}, status=400, headers=headers)
    except Exception as e:
        return web.json_response({'ok': False, 'error': 'Внутренняя ошибка сервера'}, status=500, headers=headers)


async def handle_options(request: web.Request):
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Max-Age': '86400'
    }
    return web.Response(headers=headers, status=204)


async def handle_get_game_history(request: web.Request):
    start_time = time.monotonic()
    user_id = None
    headers = {'Access-Control-Allow-Origin': '*'}
    try:
        post_data = await request.json()
        init_data_str = post_data.get('initData')
        limit = int(post_data.get('limit', 20))

        if not init_data_str:
            return web.json_response({'ok': False, 'error': 'Missing initData'}, status=400, headers=headers)

        validated_data = validate_init_data(init_data_str, TOKEN)

        if not validated_data or 'user' not in validated_data:
            return web.json_response({'ok': False, 'error': 'Invalid initData'}, status=403, headers=headers)

        user_info = validated_data['user']
        user_id = user_info.get('id')
        if not user_id: raise ValueError("User ID missing")

        history_raw = await database.get_game_history(user_id, limit=limit)

        history_processed = []
        for item in history_raw:
            timestamp_sec = None
            timestamp_db = item.get('timestamp')
            if timestamp_db:
                timestamp_sec = int(timestamp_db.timestamp())
            history_processed.append(
                {"game_type": item['game_type'], "amount": item['amount'], "description": item['description'],
                 "timestamp": timestamp_sec})

        response_data = {'ok': True, 'history': history_processed}
        return web.json_response(response_data, headers=headers)

    except ValueError as ve:
        return web.json_response({'ok': False, 'error': str(ve)}, status=400, headers=headers)
    except asyncpg.PostgresError as db_err:
        return web.json_response({'ok': False, 'error': 'Ошибка базы данных'}, status=500, headers=headers)
    except Exception as e:
        return web.json_response({'ok': False, 'error': 'Внутренняя ошибка сервера'}, status=500, headers=headers)


async def handle_play_luck_game(request: web.Request):
    start_time = time.monotonic()
    user_id = None
    headers = {'Access-Control-Allow-Origin': '*'}
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 0.05
    try:
        post_data = await request.json()
        init_data_str = post_data.get('initData')
        bet_amount_str = post_data.get('bet')

        if not init_data_str or not bet_amount_str:
            return web.json_response({'ok': False, 'error': 'Missing data'}, status=400, headers=headers)

        validated_data = validate_init_data(init_data_str, TOKEN)

        if not validated_data or 'user' not in validated_data:
            return web.json_response({'ok': False, 'error': 'Invalid initData'}, status=403, headers=headers)

        user_info = validated_data['user']
        user_id = user_info.get('id')
        if not user_id: raise ValueError("User ID missing")

        try:
            bet_amount = float(bet_amount_str)
            if bet_amount <= 0: raise ValueError("Invalid bet amount")
        except (ValueError, TypeError):
            return web.json_response({'ok': False, 'error': 'Неверная сумма ставки'}, status=400, headers=headers)

        is_blocked = await database.is_user_blocked(user_id)
        if is_blocked:
            return web.json_response({'ok': False, 'error': 'Пользователь заблокирован'}, status=403, headers=headers)

        last_exception = None
        for attempt in range(MAX_RETRIES):
            pool = database.db_pool
            if not pool: raise RuntimeError("DB pool not initialized")
            conn = None
            try:
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        balance_row = await conn.fetchrow("SELECT stars FROM users WHERE id = $1 FOR UPDATE", user_id)
                        if not balance_row: raise ValueError("User not found")
                        current_balance = balance_row['stars']

                        if current_balance < bet_amount:
                            raise ValueError("low_balance")

                        # <<<< ИЗМЕНЕНИЕ ДЛЯ БУСТА УДАЧИ >>>>
                        base_win_chance = WIN_CHANCE  # Базовый шанс из settings.py
                        luck_boost_percentage = await get_active_luck_boost_percentage(user_id)
                        actual_win_chance = base_win_chance
                        boost_active_message_part = ""
                        if luck_boost_percentage > 0:
                            actual_win_chance += luck_boost_percentage
                            actual_win_chance = min(actual_win_chance, 90.0)  # Ограничение максимального шанса
                            boost_active_message_part = " (с бустом удачи!)"
                        # <<<< КОНЕЦ ИЗМЕНЕНИЯ >>>>

                        win_coefficient = round(random.uniform(1.8, 2.5), 2);
                        is_win = random.randint(1, 100) <= actual_win_chance  # Используем actual_win_chance
                        new_balance = current_balance;
                        win_amount = 0.0;
                        history_amount = 0.0;
                        history_description = ""

                        if is_win:
                            win_amount = round(bet_amount * win_coefficient - bet_amount, 2)
                            new_balance = current_balance + win_amount
                            history_amount = win_amount;
                            history_description = f"Выигрыш 'Все или ничего' (x{win_coefficient:.2f}){boost_active_message_part}"
                            await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_balance, user_id)
                        else:
                            new_balance = current_balance - bet_amount
                            history_amount = -bet_amount;
                            history_description = f"Проигрыш 'Все или ничего'{boost_active_message_part}"
                            await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_balance, user_id)

                asyncio.create_task(
                    database.add_game_history_record(user_id, 'luck', history_amount, history_description))

                response_data = {'ok': True, 'win': is_win, 'bet': bet_amount, 'win_amount': win_amount,
                                 'coefficient': win_coefficient if is_win else 0, 'new_balance': new_balance}
                return web.json_response(response_data, headers=headers)

            except (asyncpg.exceptions.DeadlockDetectedError, asyncpg.exceptions.CannotConnectNowError,
                    asyncpg.exceptions.InterfaceError) as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(0, INITIAL_RETRY_DELAY * 0.5)
                    await asyncio.sleep(delay);
                    continue
                else:
                    return web.json_response(
                        {'ok': False, 'error': 'База данных временно недоступна, попробуйте еще раз.',
                         'reason': 'db_locked'}, status=503, headers=headers)
            except ValueError as ve:
                reason = str(ve)
                error_msg = 'Недостаточно средств' if reason == "low_balance" else "Пользователь не найден" if reason == "user_not_found" else "Неизвестная ошибка значения"
                return web.json_response({'ok': False, 'error': error_msg, 'reason': reason}, status=400,
                                         headers=headers)
            except asyncpg.PostgresError as db_err:
                last_exception = db_err
                return web.json_response({'ok': False, 'error': 'Ошибка БД во время игры', 'reason': 'db_error'},
                                         status=500, headers=headers)
            except Exception as game_err:
                last_exception = game_err
                return web.json_response({'ok': False, 'error': 'Ошибка логики игры', 'reason': 'game_error'},
                                         status=500, headers=headers)
            finally:
                pass
        return web.json_response({'ok': False, 'error': 'Не удалось выполнить операцию после нескольких попыток.',
                                  'reason': 'max_retries_exceeded'}, status=500, headers=headers)

    except ValueError as ve:
        return web.json_response({'ok': False, 'error': str(ve)}, status=400, headers=headers)
    except Exception as e:
        return web.json_response({'ok': False, 'error': 'Внутренняя ошибка сервера'}, status=500, headers=headers)


async def handle_attempt_robbery(request: web.Request):
    start_time = time.monotonic()
    user_id = None
    user_name = "unknown"
    headers = {'Access-Control-Allow-Origin': '*'}
    MIN_BALANCE_FOR_ROBBERY = 5.0
    ROBBERY_COOLDOWN_HOURS = 12
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 0.05
    try:
        post_data = await request.json()
        init_data_str = post_data.get('initData')
        if not init_data_str:
            return web.json_response({'ok': False, 'error': 'Missing initData'}, status=400, headers=headers)

        validated_data = validate_init_data(init_data_str, TOKEN)

        if not validated_data or 'user' not in validated_data:
            return web.json_response({'ok': False, 'error': 'Invalid initData'}, status=403, headers=headers)

        user_info = validated_data['user']
        user_id = user_info.get('id');
        user_name = user_info.get('username', f"id_{user_id}")
        if not user_id: raise ValueError("User ID missing")

        is_blocked = await database.is_user_blocked(user_id)
        last_robbery_time = await database.get_last_robbery_time(user_id)
        robber_balance = await database.get_users_balance(user_id)

        if is_blocked:
            return web.json_response({'ok': False, 'error': 'Пользователь заблокирован', 'reason': 'user_blocked'},
                                     status=403, headers=headers)

        robbery_cooldown_delta = timedelta(hours=ROBBERY_COOLDOWN_HOURS)
        cooldown_remaining_seconds = 0
        if last_robbery_time:
            now_dt_aware = datetime.now(timezone.utc);
            time_since_last = now_dt_aware - last_robbery_time
            if time_since_last < robbery_cooldown_delta:
                remaining = robbery_cooldown_delta - time_since_last;
                cooldown_remaining_seconds = int(remaining.total_seconds())
                rem_hours = cooldown_remaining_seconds // 3600;
                rem_minutes = (cooldown_remaining_seconds % 3600) // 60
                error_msg = f'Ограбление доступно через ~{rem_hours} ч {rem_minutes} мин'
                return web.json_response({'ok': False, 'error': error_msg, 'reason': 'cooldown',
                                          'cooldown_left': cooldown_remaining_seconds}, status=400, headers=headers)

        if robber_balance < MIN_BALANCE_FOR_ROBBERY:
            return web.json_response(
                {'ok': False, 'error': f'Недостаточно средств (нужно {MIN_BALANCE_FOR_ROBBERY:.1f}⭐)',
                 'reason': 'low_balance'}, status=400, headers=headers)

        victim_data = await database.get_random_user(exclude_id=user_id)
        if victim_data is None:
            await database.update_last_robbery_time(user_id, 0)
            return web.json_response(
                {'ok': True, 'success': False, 'message': 'Не удалось найти жертву', 'stolen_amount': 0,
                 'new_balance': robber_balance, 'cooldown_applied': ROBBERY_COOLDOWN_HOURS * 3600}, status=200,
                headers=headers)

        victim_id, victim_stars = victim_data['id'], victim_data['stars']
        stolen_amount = round(victim_stars * 0.02, 2)

        if stolen_amount < 0.01:
            await database.update_last_robbery_time(user_id, victim_id)
            return web.json_response(
                {'ok': True, 'success': False, 'message': f'Не удалось ничего украсть у {mask_id(victim_id)}',
                 'stolen_amount': 0, 'new_balance': robber_balance, 'cooldown_applied': ROBBERY_COOLDOWN_HOURS * 3600},
                status=200, headers=headers)

        new_robber_balance = robber_balance + stolen_amount
        new_victim_balance = max(0, victim_stars - stolen_amount)
        robber_history_desc = "";
        victim_history_desc = ""
        last_exception = None

        for attempt in range(MAX_RETRIES):
            pool = database.db_pool
            if not pool: raise RuntimeError("DB pool not initialized")
            conn = None
            try:
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        robber_balance_tx = await conn.fetchval("SELECT stars FROM users WHERE id = $1 FOR UPDATE",
                                                                user_id)
                        if robber_balance_tx is None or robber_balance_tx < MIN_BALANCE_FOR_ROBBERY: raise ValueError(
                            "Robber balance check failed inside TX")
                        victim_stars_tx = await conn.fetchval("SELECT stars FROM users WHERE id = $1 FOR UPDATE",
                                                              victim_id)
                        if victim_stars_tx is None: raise ValueError("Victim not found inside TX")

                        stolen_tx = round(victim_stars_tx * 0.02, 2)
                        if stolen_tx < 0.01: raise ValueError("Stolen amount too small inside TX")

                        new_robber_balance_tx = robber_balance_tx + stolen_tx
                        new_victim_balance_tx = max(0, victim_stars_tx - stolen_tx)

                        await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_robber_balance_tx, user_id)
                        await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_victim_balance_tx,
                                           victim_id)
                        current_time_utc = datetime.now(timezone.utc)
                        await conn.execute(
                            '''INSERT INTO robberies (user_id, target_user_id, robbery_time) VALUES ($1, $2, $3) ON CONFLICT (user_id, target_user_id) DO UPDATE SET robbery_time = excluded.robbery_time''',
                            user_id, victim_id, current_time_utc)

                        stolen_amount = stolen_tx;
                        new_robber_balance = new_robber_balance_tx;
                        new_victim_balance = new_victim_balance_tx

                victim_username_db = await database.get_user_username(victim_id)
                robber_history_desc = f"Ограбление {victim_username_db or mask_id(victim_id)}"
                victim_history_desc = f"Ограблен {user_name or mask_id(user_id)}"
                asyncio.create_task(
                    database.add_game_history_record(user_id, 'robbery', stolen_amount, robber_history_desc))
                asyncio.create_task(
                    database.add_game_history_record(victim_id, 'robbery', -stolen_amount, victim_history_desc))

                try:
                    bot: Bot = request.app['bot']
                    asyncio.create_task(bot.send_message(victim_id,
                                                         f"🥷 <b>Вас ограбили!</b> У вас украли {stolen_amount:.2f}⭐️.\nБаланс: {new_victim_balance:.2f}⭐️.",
                                                         parse_mode='HTML'))
                except Exception as notify_err:
                    pass

                response_data = {'ok': True, 'success': True,
                                 'message': f'Украдено {stolen_amount:.2f}⭐ у {mask_id(victim_id)}!',
                                 'stolen_amount': stolen_amount, 'new_balance': new_robber_balance,
                                 'cooldown_applied': ROBBERY_COOLDOWN_HOURS * 3600}
                return web.json_response(response_data, headers=headers)

            except (asyncpg.exceptions.DeadlockDetectedError, asyncpg.exceptions.CannotConnectNowError,
                    asyncpg.exceptions.InterfaceError) as e:
                last_exception = e;
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(0, INITIAL_RETRY_DELAY * 0.5);
                    await asyncio.sleep(delay);
                    continue
                else:
                    return web.json_response(
                        {'ok': False, 'error': 'База данных временно недоступна, попробуйте еще раз.',
                         'reason': 'db_locked'}, status=503, headers=headers)
            except ValueError as ve:
                await database.update_last_robbery_time(user_id, 0)
                return web.json_response({'ok': False, 'error': f"Не удалось: {ve}", 'reason': 'validation_failed'},
                                         status=400, headers=headers)
            except asyncpg.PostgresError as db_err:
                last_exception = db_err;
                return web.json_response({'ok': False, 'error': 'Ошибка БД во время ограбления', 'reason': 'db_error'},
                                         status=500, headers=headers)
            except Exception as game_err:
                last_exception = game_err;
                return web.json_response({'ok': False, 'error': 'Ошибка логики ограбления', 'reason': 'game_error'},
                                         status=500, headers=headers)
            finally:
                pass

        return web.json_response({'ok': False, 'error': 'Не удалось выполнить ограбление после нескольких попыток.',
                                  'reason': 'max_retries_exceeded'}, status=500, headers=headers)

    except ValueError as ve:
        return web.json_response({'ok': False, 'error': str(ve)}, status=400, headers=headers)
    except Exception as e:
        return web.json_response({'ok': False, 'error': 'Внутренняя ошибка сервера'}, status=500, headers=headers)


async def handle_play_slots(request: web.Request):
    start_time = time.monotonic()
    user_id = None
    headers = {'Access-Control-Allow-Origin': '*'}
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 0.05
    SLOT_WIN_MAP = {
        1: (2.0, 3.0),
        22: (1.2, 1.8),
        43: (1.2, 1.8),
        64: (3.0, 5.0)
    }
    SLOT_EMOJI_MAP = {
        1: ["BAR", "BAR", "BAR"],
        22: ["🍇", "🍇", "🍇"],
        43: ["🍋", "🍋", "🍋"],
        64: ["7️⃣", "7️⃣", "7️⃣"],
    }
    SLOT_LOSE_EMOJIS = ['🍒', '💰', '💎', '🎁', '⭐', '💔', '🍀', '🎰']

    try:
        post_data = await request.json()
        init_data_str = post_data.get('initData')
        bet_amount_str = post_data.get('bet')

        if not init_data_str or not bet_amount_str:
            return web.json_response({'ok': False, 'error': 'Missing data'}, status=400, headers=headers)

        validated_data = validate_init_data(init_data_str, TOKEN)

        if not validated_data or 'user' not in validated_data:
            return web.json_response({'ok': False, 'error': 'Invalid initData'}, status=403, headers=headers)

        user_info = validated_data['user']
        user_id = user_info.get('id')
        if not user_id: raise ValueError("User ID missing")

        try:
            bet_amount = float(bet_amount_str)
            if bet_amount <= 0: raise ValueError("Invalid bet amount")
        except (ValueError, TypeError):
            return web.json_response({'ok': False, 'error': 'Неверная сумма ставки'}, status=400, headers=headers)

        is_blocked = await database.is_user_blocked(user_id)
        if is_blocked:
            return web.json_response({'ok': False, 'error': 'Пользователь заблокирован'}, status=403, headers=headers)

        last_exception = None
        for attempt in range(MAX_RETRIES):
            pool = database.db_pool
            if not pool: raise RuntimeError("DB pool not initialized")
            conn = None
            try:
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        balance_row = await conn.fetchrow("SELECT stars FROM users WHERE id = $1 FOR UPDATE", user_id)
                        if not balance_row: raise ValueError("User not found")
                        current_balance = balance_row['stars']

                        if current_balance < bet_amount:
                            raise ValueError("low_balance")

                        simulated_dice_value = random.randint(1, 64)
                        is_win = simulated_dice_value in SLOT_WIN_MAP

                        # <<<< ИЗМЕНЕНИЕ ДЛЯ БУСТА УДАЧИ >>>>
                        luck_boost_percentage = await get_active_luck_boost_percentage(user_id)
                        boost_active_message_part = ""
                        if luck_boost_percentage > 0:
                            boost_active_message_part = " (с бустом удачи!)"
                            # Увеличиваем шанс на выигрышную комбинацию
                            # Базовый шанс на выигрышную комбинацию = 4/64 (6.25%)
                            # Если буст +10%, то шанс становится ~16.25%
                            # Это упрощенная симуляция. Более точная потребует перебора dice_value
                            # или изменения логики определения is_win.
                            # Здесь мы просто "перебрасываем" дайс с учетом буста, если первая попытка была неудачной.
                            if not is_win and random.randint(1, 100) <= luck_boost_percentage:
                                # Попытка "вытянуть" выигрышный дайс
                                possible_win_values = list(SLOT_WIN_MAP.keys())
                                if possible_win_values:
                                    simulated_dice_value = random.choice(possible_win_values)
                                    is_win = True
                        # <<<< КОНЕЦ ИЗМЕНЕНИЯ >>>>

                        win_coefficient = 0.0
                        win_amount = 0.0
                        payout_amount = 0.0
                        new_balance = current_balance
                        history_amount = 0.0
                        history_description = ""
                        result_emojis = []

                        if is_win:
                            result_emojis = SLOT_EMOJI_MAP.get(simulated_dice_value, ['?', '?', '?'])
                        else:
                            result_emojis = random.choices(SLOT_LOSE_EMOJIS, k=3)
                            while tuple(result_emojis) in [tuple(v) for v in SLOT_EMOJI_MAP.values()]:
                                result_emojis = random.choices(SLOT_LOSE_EMOJIS, k=3)

                        new_balance = current_balance - bet_amount
                        await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_balance, user_id)

                        if is_win:
                            min_c, max_c = SLOT_WIN_MAP[simulated_dice_value]
                            win_coefficient = round(random.uniform(min_c, max_c), 2)
                            payout_amount = round(bet_amount * win_coefficient, 2)
                            win_amount = round(payout_amount - bet_amount, 2)
                            new_balance += payout_amount
                            await conn.execute("UPDATE users SET stars = $1 WHERE id = $2", new_balance, user_id)
                            history_amount = win_amount
                            history_description = f"Выигрыш в Слотах (x{win_coefficient:.2f}){boost_active_message_part}"
                        else:
                            history_amount = -bet_amount
                            history_description = f"Проигрыш в Слотах{boost_active_message_part}"

                asyncio.create_task(
                    database.add_game_history_record(user_id, 'slots', history_amount, history_description))

                if is_win and WIN_CHANEL_ID and win_amount > 0:
                    try:
                        bot_instance: Bot = request.app['bot']
                        user_name_for_notify = user_info.get('first_name', f"ID:{user_id}")
                        win_emoji_combo_str = "".join(result_emojis)
                        win_channel_message = (
                            f"🎰 <b>Выигрыш в слотах!</b> <a href='tg://user?id={user_id}'>{escape(user_name_for_notify)}</a>\n"
                            f"(<code>{user_id}</code>)\n\n"
                            f"выиграл(а) <b>{win_amount:.2f}</b> ⭐️ (чистыми)\n"
                            f"Ставка: <b>{bet_amount:.1f}</b> ⭐️\n"
                            f"Комбинация: {win_emoji_combo_str} (Value: {simulated_dice_value})\n"
                            f"Коэффициент: <b>{win_coefficient:.2f}</b> ✨\n\n"
                            f"🎉 Поздравляем! 🎉"
                        )
                        asyncio.create_task(
                            bot_instance.send_message(WIN_CHANEL_ID, win_channel_message, parse_mode="HTML",
                                                      disable_web_page_preview=True))
                    except Exception as e:
                        pass

                response_data = {
                    'ok': True, 'win': is_win, 'bet': bet_amount,
                    'win_amount': win_amount, 'coefficient': win_coefficient if is_win else 0,
                    'new_balance': new_balance, 'dice_value': simulated_dice_value,
                    'result_emojis': result_emojis
                }
                return web.json_response(response_data, headers=headers)

            except (asyncpg.exceptions.DeadlockDetectedError, asyncpg.exceptions.CannotConnectNowError,
                    asyncpg.exceptions.InterfaceError) as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(0, INITIAL_RETRY_DELAY * 0.5)
                    await asyncio.sleep(delay)
                    continue
                else:
                    return web.json_response(
                        {'ok': False, 'error': 'База данных временно недоступна, попробуйте еще раз.',
                         'reason': 'db_locked'}, status=503, headers=headers)
            except ValueError as ve:
                reason = str(ve)
                error_msg = 'Недостаточно средств' if reason == "low_balance" else "Пользователь не найден" if reason == "user_not_found" else "Неизвестная ошибка значения"
                return web.json_response({'ok': False, 'error': error_msg, 'reason': reason}, status=400,
                                         headers=headers)
            except asyncpg.PostgresError as db_err:
                last_exception = db_err
                return web.json_response({'ok': False, 'error': 'Ошибка БД во время игры', 'reason': 'db_error'},
                                         status=500, headers=headers)
            except Exception as game_err:
                last_exception = game_err
                return web.json_response({'ok': False, 'error': 'Ошибка логики игры', 'reason': 'game_error'},
                                         status=500, headers=headers)
            finally:
                pass
        return web.json_response({'ok': False, 'error': 'Не удалось выполнить операцию после нескольких попыток.',
                                  'reason': 'max_retries_exceeded'}, status=500, headers=headers)

    except ValueError as ve:
        return web.json_response({'ok': False, 'error': str(ve)}, status=400, headers=headers)
    except Exception as e:
        return web.json_response({'ok': False, 'error': 'Внутренняя ошибка сервера'}, status=500, headers=headers)


async def handle_maintenance_status(request):
    from aiohttp import web
    import database
    try:
        is_maint = await database.is_maintenance_mode()
        msg = await database.get_maintenance_message() if is_maint else ""
        return web.json_response({"maintenance": is_maint, "message": msg})
    except Exception as e:
        return web.json_response({"maintenance": False, "message": ""})
