import asyncpg
import asyncio
import logging
import time
import random
from datetime import datetime, timedelta, date, timezone
from html import escape
import os
import json

from settings import (
    WIN_CHANCE, MAX_REF_REWARD, MIN_REF_REWARD,
    CLICK_MAX_REWARD, CLICK_MIN_REWARD, ADMIN_IDS,
    CLICK_MIN_REWARD_X2, CLICK_MAX_REWARD_X2,
    AVAILABLE_DAILY_GIFTS, DEFAULT_DAILY_GIFT_KEY, TOKEN,
    PG_DBNAME, PG_USER, PG_PASSWORD, PG_HOST, PG_PORT, PG_POOL_MIN_SIZE, PG_POOL_MAX_SIZE
)

log = logging.getLogger('database')

db_pool: asyncpg.Pool | None = None

DEFAULT_EXCHANGE_REFERRAL_REQ = 5
DEFAULT_WHEEL_REFERRAL_REQ = 5
DEFAULT_WHEEL_DAILY_LIMIT = 10
DEFAULT_EXCHANGE_DAILY_LIMIT = 10


async def set_jsonb_codec(conn):
    await conn.set_type_codec(
        'jsonb',
        encoder=json.dumps,
        decoder=json.loads,
        schema='pg_catalog'
    )


async def init_db_pool():
    global db_pool
    if db_pool is not None:
        log.warning("Пул соединений DB уже инициализирован.")
        return
    try:
        start_time = time.monotonic()
        db_pool = await asyncpg.create_pool(
            database=PG_DBNAME,
            user=PG_USER,
            password=PG_PASSWORD,
            host=PG_HOST,
            port=PG_PORT,
            min_size=PG_POOL_MIN_SIZE,
            max_size=PG_POOL_MAX_SIZE,
            init=set_jsonb_codec
        )
        duration = time.monotonic() - start_time
        log.info(
            f"Пул соединений asyncpg инициализирован ({PG_POOL_MIN_SIZE}-{PG_POOL_MAX_SIZE} соединений). Duration: {duration:.4f}s")
        await check_and_create_tables()
    except Exception as e:
        log.exception(f"!!! КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать пул соединений PostgreSQL: {e}")
        db_pool = None
        raise


async def close_db_pool():
    global db_pool
    if db_pool:
        log.info("Закрытие пула соединений asyncpg...")
        await db_pool.close()
        db_pool = None
        log.info("Пул соединений asyncpg закрыт.")


async def check_and_create_tables():
    if not db_pool:
        log.error("Пул DB не инициализирован, невозможно создать таблицы.")
        return

    start_time = time.monotonic()
    log.info("Проверка/создание таблиц и индексов PostgreSQL...")
    async with db_pool.acquire() as conn:
        tables_to_create = {
            'users': '''
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    stars DOUBLE PRECISION DEFAULT 0.0,
                    count_refs INTEGER DEFAULT 0,
                    referral_id BIGINT DEFAULT NULL,
                    withdrawn DOUBLE PRECISION DEFAULT 0.0,
                    lang TEXT NOT NULL DEFAULT 'ru',
                    ref_rewarded INTEGER DEFAULT 0,
                    second_level_rewards DOUBLE PRECISION DEFAULT 0.0,
                    last_gift_time TIMESTAMPTZ DEFAULT NULL,
                    click_count INTEGER DEFAULT 0,
                    gift_count INTEGER DEFAULT 0,
                    registration_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    special_ref TEXT DEFAULT NULL,
                    completed_onboarding INTEGER DEFAULT 0,
                    last_click_time TIMESTAMPTZ DEFAULT NULL,
                    last_free_spin_time TIMESTAMPTZ DEFAULT NULL
                )
            ''',
            'robberies': '''
                CREATE TABLE IF NOT EXISTS robberies (
                    user_id BIGINT NOT NULL,
                    target_user_id BIGINT NOT NULL,
                    robbery_time TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (user_id, target_user_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'custom_rewards': '''
                CREATE TABLE IF NOT EXISTS custom_rewards (
                    user_id BIGINT PRIMARY KEY,
                    min_reward DOUBLE PRECISION,
                    max_reward DOUBLE PRECISION,
                    min_f_reward DOUBLE PRECISION,
                    max_f_reward DOUBLE PRECISION,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'tasks': '''
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    reward DOUBLE PRECISION NOT NULL,
                    completed_count INTEGER DEFAULT 0,
                    max_completions INTEGER NOT NULL,
                    active INTEGER DEFAULT 1,
                    requires_subscription INTEGER DEFAULT 1,
                    task_type TEXT DEFAULT 'sub'
                )
            ''',
            'promocodes': '''
                CREATE TABLE IF NOT EXISTS promocodes (
                    promocode TEXT PRIMARY KEY,
                    reward DOUBLE PRECISION NOT NULL,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    min_referrals INTEGER NOT NULL DEFAULT 0
                )
            ''',
            'channels': '''
                CREATE TABLE IF NOT EXISTS channels (
                    id SERIAL PRIMARY KEY,
                    channel_id BIGINT UNIQUE NOT NULL,
                    delete_time TIMESTAMPTZ
                )
            ''',
            'special_links': '''
                CREATE TABLE IF NOT EXISTS special_links (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    special_code TEXT UNIQUE NOT NULL,
                    unique_visits INTEGER DEFAULT 0,
                    total_visits INTEGER DEFAULT 0,
                    verified_signups INTEGER DEFAULT 0,
                    completed_onboarding INTEGER DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'sponsor_buttons': '''
                CREATE TABLE IF NOT EXISTS sponsor_buttons (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL
                )
            ''',
            'spent_stars': '''
                CREATE TABLE IF NOT EXISTS spent_stars (
                    date DATE PRIMARY KEY,
                    amount DOUBLE PRECISION NOT NULL DEFAULT 0.0
                )
            ''',
            'special_link_visits': '''
                 CREATE TABLE IF NOT EXISTS special_link_visits (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    special_code TEXT NOT NULL,
                    visit_time TIMESTAMPTZ NOT NULL,
                    UNIQUE(user_id, special_code),
                    FOREIGN KEY(special_code) REFERENCES special_links(special_code) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'block_status': '''
                CREATE TABLE IF NOT EXISTS block_status (
                    user_id BIGINT PRIMARY KEY,
                    is_blocked INTEGER DEFAULT 0,
                    blocked_at TIMESTAMPTZ,
                    unblocked_at TIMESTAMPTZ,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'completed_tasks': '''
                CREATE TABLE IF NOT EXISTS completed_tasks (
                    user_id BIGINT NOT NULL,
                    task_id INTEGER NOT NULL,
                    completed_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (user_id, task_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            ''',
            'used_promocodes': '''
                CREATE TABLE IF NOT EXISTS used_promocodes (
                    user_id BIGINT NOT NULL,
                    promocode TEXT NOT NULL,
                    used_at TIMESTAMPTZ NOT NULL,
                    PRIMARY KEY (user_id, promocode),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(promocode) REFERENCES promocodes(promocode) ON DELETE CASCADE
                )
            ''',
            'config': '''
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''',
            'withdraw_requests': '''
                CREATE TABLE IF NOT EXISTS withdraw_requests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount DOUBLE PRECISION NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    request_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    processed_time TIMESTAMPTZ,
                    gift_id BIGINT,
                    emoji TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'daily_withdrawals': '''
                CREATE TABLE IF NOT EXISTS daily_withdrawals (
                    user_id BIGINT NOT NULL,
                    withdrawal_date DATE NOT NULL,
                    withdrawal_type TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, withdrawal_date, withdrawal_type),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'game_history': '''
                CREATE TABLE IF NOT EXISTS game_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    game_type TEXT NOT NULL,
                    amount DOUBLE PRECISION NOT NULL,
                    description TEXT,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'user_active_boosts': '''
                CREATE TABLE IF NOT EXISTS user_active_boosts (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    boost_id_key TEXT NOT NULL,
                    activation_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expiration_time TIMESTAMPTZ NOT NULL,
                    boost_params JSONB DEFAULT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'proxies': '''
                CREATE TABLE IF NOT EXISTS proxies (
                    id SERIAL PRIMARY KEY,
                    proxy_type TEXT NOT NULL,
                    address TEXT NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    is_sold BOOLEAN DEFAULT FALSE,
                    added_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    sold_to BIGINT DEFAULT NULL,
                    sold_at TIMESTAMPTZ DEFAULT NULL,
                    FOREIGN KEY(sold_to) REFERENCES users(id) ON DELETE SET NULL
                )
            ''',
            'proxy_purchases': '''
                CREATE TABLE IF NOT EXISTS proxy_purchases (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    proxy_id INTEGER NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    purchased_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(proxy_id) REFERENCES proxies(id) ON DELETE CASCADE
                )
            '''
        }

        indexes_to_create = {
            'idx_user_active_boosts_user_id_expiration': '''
                CREATE INDEX IF NOT EXISTS idx_user_active_boosts_user_id_expiration
                ON user_active_boosts (user_id, expiration_time DESC);
            ''',
            'idx_user_active_boosts_user_id_boost_key_active': '''
                CREATE INDEX IF NOT EXISTS idx_user_active_boosts_user_id_boost_key_active
                ON user_active_boosts (user_id, boost_id_key, is_active);
            '''
        }

        for table_name, create_query in tables_to_create.items():
            try:
                t_start = time.monotonic()
                await conn.execute(create_query)
                t_duration = time.monotonic() - t_start
                log.debug(f"Table '{table_name}' checked/created. Duration: {t_duration:.4f}s")
            except Exception as e:
                log.error(f"Ошибка создания таблицы {table_name}: {e}")
                if "syntax error" in str(e).lower():
                    raise

        for index_name, create_index_query in indexes_to_create.items():
            try:
                t_start_idx = time.monotonic()
                await conn.execute(create_index_query)
                t_duration_idx = time.monotonic() - t_start_idx
                log.debug(f"Index '{index_name}' checked/created. Duration: {t_duration_idx:.4f}s")
            except Exception as e:
                log.error(f"Ошибка создания индекса {index_name}: {e}")

        # --- Добавление недостающих колонок (миграции) ---
        columns_to_add = [
            ('users', 'login_streak', 'INTEGER DEFAULT 0'),
            ('users', 'last_login_date', 'DATE DEFAULT NULL'),
            ('users', 'clicks_since_captcha', 'INTEGER DEFAULT 0'),
            ('users', 'captcha_answer', 'TEXT DEFAULT NULL'),
            ('users', 'captcha_expires', 'TIMESTAMPTZ DEFAULT NULL'),
        ]
        for table, col, col_def in columns_to_add:
            try:
                await conn.execute(f'''
                    DO $$ BEGIN
                        ALTER TABLE {table} ADD COLUMN {col} {col_def};
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
                ''')
            except Exception as e:
                log.debug(f"Column {table}.{col} migration: {e}")

    duration = time.monotonic() - start_time
    log.info(f"Проверка таблиц и индексов PostgreSQL завершена. Duration: {duration:.4f}s")


async def _log_pool_stats(func_name: str):
    if db_pool:
        try:
            current_size = db_pool.get_size()
            idle_size = db_pool.get_idle_size()
            max_size = db_pool.get_max_size()
            log.debug(f"DB POOL STATS ({func_name}): Size={current_size}, Idle={idle_size}, Max={max_size}")
        except Exception as e:
            log.warning(f"Failed to get DB pool stats ({func_name}): {e}")
    else:
        log.warning(f"DB Pool not available for stats logging ({func_name})")


async def user_exists(user_id: int) -> bool:
    if not db_pool: return False
    await _log_pool_stats("user_exists")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for user_exists ({user_id})...")
        result = await conn.fetchval('SELECT 1 FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (user_exists): {duration:.4f}s")
        log.debug(f"Releasing connection for user_exists ({user_id})...")
        return bool(result)


async def get_user_id_by_username(username: str) -> int | None:
    if not db_pool:
        log.error("get_user_id_by_username: DB pool not initialized!")
        return None

    clean_username = username.lstrip('@').lower()

    await _log_pool_stats("get_user_id_by_username")
    async with db_pool.acquire() as conn:
        log.debug(f"Attempting to find user ID for username: {clean_username}")
        user_record = await conn.fetchrow(
            'SELECT id FROM users WHERE LOWER(username) = LOWER($1)',
            clean_username
        )
        if user_record:
            log.info(f"Found user ID {user_record['id']} for username {clean_username}")
            return user_record['id']

        if clean_username.isdigit():
            try:
                user_id_candidate = int(clean_username)
                user_record_by_id = await conn.fetchrow('SELECT id FROM users WHERE id = $1', user_id_candidate)
                if user_record_by_id:
                    log.info(f"Username search for '{clean_username}' found user by ID {user_id_candidate} instead.")
                    return user_record_by_id['id']
            except ValueError:
                pass

        log.warning(f"User ID not found for username: {clean_username}")
        return None


async def add_user(user_id: int, username: str, referral_id: int | None = None, lang: str = 'ru',
                   special_ref: str | None = None):
    if not db_pool: return False
    await _log_pool_stats("add_user")
    registration_time = datetime.now(timezone.utc)
    username_to_db = username or f"id_{user_id}"
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for add_user ({user_id})...")
        try:
            await conn.execute('''
                INSERT INTO users (id, username, stars, count_refs, referral_id, lang, click_count, gift_count, registration_time, special_ref, ref_rewarded, completed_onboarding, last_click_time, last_gift_time, last_free_spin_time)
                VALUES ($1, $2, 0.0, 0, $3, $4, 0, 0, $5, $6, 0, 0, NULL, NULL, NULL)
            ''', user_id, username_to_db, referral_id, lang, registration_time, special_ref)
            duration = time.monotonic() - start_time
            log.info(f"Пользователь {user_id} успешно добавлен. Duration: {duration:.4f}s")
            log.debug(f"Releasing connection for add_user ({user_id})...")
            return True
        except asyncpg.UniqueViolationError:
            log.warning(f"Пользователь {user_id} уже существует. Проверка username...")
            start_time_check = time.monotonic()
            existing_username = await conn.fetchval("SELECT username FROM users WHERE id = $1", user_id)
            duration_check = time.monotonic() - start_time_check
            log.debug(f"DB Query duration (add_user username check): {duration_check:.4f}s")
            if existing_username != username_to_db:
                await update_user_username(user_id, username_to_db)
            log.debug(f"Releasing connection for add_user ({user_id}) after check...")
            return False
        except Exception as e:
            duration = time.monotonic() - start_time
            log.error(f"Ошибка добавления пользователя {user_id}. Duration: {duration:.4f}s Error: {e}")
            log.debug(f"Releasing connection for add_user ({user_id}) after error...")
            return False


async def get_user(user_id: int) -> asyncpg.Record | None:
    if not db_pool: return None
    await _log_pool_stats("get_user")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_user ({user_id})...")
        result = await conn.fetchrow('SELECT * FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_user): {duration:.4f}s")
        log.debug(f"Releasing connection for get_user ({user_id})...")
        return result


async def get_users() -> list[int]:
    if not db_pool: return []
    await _log_pool_stats("get_users")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_users...")
        rows = await conn.fetch('SELECT id FROM users')
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_users): {duration:.4f}s")
        log.debug("Releasing connection for get_users...")
        return [row['id'] for row in rows]


async def delete_user(user_id: int) -> bool:
    if not db_pool: return False
    await _log_pool_stats("delete_user")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for delete_user ({user_id})...")
        async with conn.transaction():
            try:
                result = await conn.execute("DELETE FROM users WHERE id = $1", user_id)
                deleted_count = int(result.split()[-1]) if result else 0
                if deleted_count > 0:
                    log.warning(f"Пользователь {user_id} и связанные данные удалены (CASCADE).")
                duration = time.monotonic() - start_time
                log.debug(f"DB Transaction duration (delete_user): {duration:.4f}s")
                log.debug(f"Releasing connection for delete_user ({user_id})...")
                return deleted_count > 0
            except Exception as e:
                duration = time.monotonic() - start_time
                log.error(f"Ошибка удаления пользователя {user_id}. Duration: {duration:.4f}s Error: {e}")
                log.debug(f"Releasing connection for delete_user ({user_id}) after error...")
                return False


async def update_user_username(user_id: int, new_username: str):
    if not db_pool: return
    await _log_pool_stats("update_user_username")
    username_to_update = new_username or f"id_{user_id}"
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for update_user_username ({user_id})...")
        result = await conn.execute('UPDATE users SET username = $1 WHERE id = $2', username_to_update, user_id)
        duration = time.monotonic() - start_time
        updated_count = int(result.split()[-1]) if result else 0
        if updated_count > 0:
            log.info(
                f"Обновлен username для пользователя {user_id} на '{username_to_update}'. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for update_user_username ({user_id})...")


async def update_user_lang(user_id: int, lang: str):
    if not db_pool: return
    await _log_pool_stats("update_user_lang")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for update_user_lang ({user_id})...")
        await conn.execute('UPDATE users SET lang = $1 WHERE id = $2', lang, user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (update_user_lang): {duration:.4f}s")
        log.debug(f"Releasing connection for update_user_lang ({user_id})...")


async def get_user_lang(user_id: int) -> str:
    if not db_pool: return 'ru'
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        lang = await conn.fetchval('SELECT lang FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        if duration > 0.05:
            log.debug(f"DB Query duration (get_user_lang for {user_id}): {duration:.4f}s")
        return lang or 'ru'


async def get_user_registration_time(user_id: int) -> datetime | None:
    if not db_pool: return None
    await _log_pool_stats("get_user_registration_time")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_user_registration_time ({user_id})...")
        reg_time = await conn.fetchval('SELECT registration_time FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_user_registration_time): {duration:.4f}s")
        log.debug(f"Releasing connection for get_user_registration_time ({user_id})...")
        return reg_time


async def get_user_counts() -> dict:
    if not db_pool: return {"total": 0, "daily": 0, "monthly": 0}
    await _log_pool_stats("get_user_counts")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_user_counts...")
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users;") or 0
        day_ago_dt = datetime.now(timezone.utc) - timedelta(days=1)
        daily_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE registration_time >= $1", day_ago_dt) or 0
        month_ago_dt = datetime.now(timezone.utc) - timedelta(days=30)
        monthly_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE registration_time >= $1",
                                            month_ago_dt) or 0
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_user_counts): {duration:.4f}s")
        log.debug("Releasing connection for get_user_counts...")
        return {"total": total_users, "daily": daily_users, "monthly": monthly_users}


async def add_stars(user_id: int, amount: float):
    if not db_pool: return
    await _log_pool_stats("add_stars")
    if not isinstance(amount, (int, float)) or amount == 0:
        if amount < 0:
            log.warning(f"Попытка добавить отрицательную сумму {amount} для пользователя {user_id}")
        return
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for add_stars ({user_id}, {amount})...")
        await conn.execute('UPDATE users SET stars = stars + $1 WHERE id = $2', amount, user_id)
        duration = time.monotonic() - start_time
        log.debug(f"Добавлено {amount} звезд пользователю {user_id}. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for add_stars ({user_id})...")


async def subtract_stars(user_id: int, amount: float):
    if not db_pool: return
    await _log_pool_stats("subtract_stars")
    if not isinstance(amount, (int, float)) or amount <= 0:
        log.warning(f"Попытка списать неверную сумму {amount} для пользователя {user_id}")
        return
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for subtract_stars ({user_id}, {amount})...")
        await conn.execute('UPDATE users SET stars = GREATEST(0, stars - $1) WHERE id = $2', amount, user_id)
        duration = time.monotonic() - start_time
        log.debug(f"Списано {amount} звезд у пользователя {user_id}. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for subtract_stars ({user_id})...")


async def get_users_balance(user_id: int) -> float:
    if not db_pool: return 0.0
    await _log_pool_stats("get_users_balance")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_users_balance ({user_id})...")
        balance = await conn.fetchval('SELECT stars FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_users_balance): {duration:.4f}s")
        log.debug(f"Releasing connection for get_users_balance ({user_id})...")
        return float(balance) if balance is not None else 0.0


async def reset_user_balances() -> int:
    if not db_pool: return 0
    await _log_pool_stats("reset_user_balances")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for reset_user_balances...")
        result = await conn.execute("UPDATE users SET stars = 0.0")
        duration = time.monotonic() - start_time
        count = int(result.split()[-1]) if result else 0
        log.warning(f"Балансы всех ({count}) пользователей обнулены. Duration: {duration:.4f}s")
        log.debug("Releasing connection for reset_user_balances...")
        return count


async def give_stars_to_all(amount: float) -> int:
    if not db_pool: return 0
    await _log_pool_stats("give_stars_to_all")
    if not isinstance(amount, (int, float)) or amount <= 0:
        log.warning("Попытка выдать неверную сумму звезд всем пользователям.")
        return 0
    log.info(f"Добавление {amount} звезд всем пользователям...")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for give_stars_to_all...")
        result = await conn.execute("UPDATE users SET stars = stars + $1", amount)
        duration = time.monotonic() - start_time
        count = int(result.split()[-1]) if result else 0
        log.info(f"Добавлено {amount} звезд {count} пользователям. Duration: {duration:.4f}s")
        log.debug("Releasing connection for give_stars_to_all...")
        return count


async def withdraw_stars(conn: asyncpg.Connection, user_id: int, amount: float) -> bool:
    if not isinstance(amount, (int, float)) or amount <= 0:
        log.warning(f"Попытка списания неверной суммы {amount} для пользователя {user_id}")
        return False
    try:
        start_time = time.monotonic()
        result = await conn.execute('''
            UPDATE users
            SET stars = stars - $1, withdrawn = withdrawn + $1
            WHERE id = $2 AND stars >= $1
        ''', amount, user_id)
        duration = time.monotonic() - start_time

        updated_count = int(result.split()[-1]) if result else 0

        if updated_count > 0:
            log.info(
                f"Списано {amount} звезд у пользователя {user_id} и обновлен withdrawn (в рамках транзакции). Duration: {duration:.4f}s")
            return True
        else:
            log.warning(
                f"Withdraw failed for user {user_id}: insufficient balance or user not found for amount {amount}. Duration: {duration:.4f}s")
            return False
    except Exception as e:
        log.error(f"Ошибка БД во время withdraw_stars для пользователя {user_id}: {e}")
        return False


async def record_spent_stars(amount: float):
    if not db_pool: return
    await _log_pool_stats("record_spent_stars")
    if not isinstance(amount, (int, float)) or amount <= 0: return
    today_date = date.today()
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for record_spent_stars ({amount})...")
        try:
            await conn.execute('''
                INSERT INTO spent_stars (date, amount)
                VALUES ($1, $2)
                ON CONFLICT(date) DO UPDATE SET amount = spent_stars.amount + excluded.amount;
            ''', today_date, amount)
            duration = time.monotonic() - start_time
            log.debug(f"DB Query duration (record_spent_stars): {duration:.4f}s")
        except Exception as e:
            log.error(f"Failed to record spent stars ({amount}): {e}")
        finally:
            log.debug(f"Releasing connection for record_spent_stars ({amount})...")


async def increment_referrals(user_id: int):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        await conn.execute('UPDATE users SET count_refs = count_refs + 1 WHERE id = $1', user_id)


async def update_user_ref_rewarded(user_id: int, rewarded: bool):
    if not db_pool: return
    await _log_pool_stats("update_user_ref_rewarded")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for update_user_ref_rewarded ({user_id})...")
        await conn.execute("UPDATE users SET ref_rewarded = $1 WHERE id = $2", int(rewarded), user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (update_user_ref_rewarded): {duration:.4f}s")
        log.debug(f"Releasing connection for update_user_ref_rewarded ({user_id})...")


async def get_referral_id(user_id: int) -> int | None:
    if not db_pool: return None
    await _log_pool_stats("get_referral_id")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_referral_id ({user_id})...")
        result = await conn.fetchval('SELECT referral_id FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_referral_id): {duration:.4f}s")
        log.debug(f"Releasing connection for get_referral_id ({user_id})...")
        return result


async def get_referrals(user_id: int) -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats("get_referrals")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_referrals ({user_id})...")
        result = await conn.fetch(
            "SELECT id, username, stars, registration_time FROM users WHERE referral_id = $1 ORDER BY registration_time DESC",
            user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_referrals): {duration:.4f}s")
        log.debug(f"Releasing connection for get_referrals ({user_id})...")
        return result


async def get_referrals_count(user_id: int) -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_referrals_count")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_referrals_count ({user_id})...")
        count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referral_id=$1", user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_referrals_count): {duration:.4f}s")
        log.debug(f"Releasing connection for get_referrals_count ({user_id})...")
        return count or 0


async def get_referrals_count_week(user_id: int) -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_referrals_count_week")
    start_of_week_utc = datetime.now(timezone.utc).date() - timedelta(days=datetime.now(timezone.utc).weekday())
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_referrals_count_week ({user_id})...")
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referral_id = $1 AND registration_time >= $2::date", user_id,
            start_of_week_utc)
        duration = time.monotonic() - start_time
        if duration > 0.05:
            log.debug(f"DB Query duration (get_referrals_count_week): {duration:.4f}s")
        log.debug(f"Weekly referrals for {user_id} (since {start_of_week_utc} UTC): {count or 0}")
        log.debug(f"Releasing connection for get_referrals_count_week ({user_id})...")
        return count or 0


async def get_referral_top() -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats("get_referral_top")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_referral_top...")
        result = await conn.fetch(
            "SELECT id, username, count_refs FROM users WHERE count_refs > 0 ORDER BY count_refs DESC LIMIT 10"
        )
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_referral_top): {duration:.4f}s")
        log.debug("Releasing connection for get_referral_top...")
        return result


async def get_referral_top_by_period(period: str) -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats(f"get_referral_top_by_period ({period})")
    now_utc = datetime.now(timezone.utc)
    if period == 'day':
        time_threshold = now_utc - timedelta(days=1)
    elif period == 'week':
        time_threshold = now_utc - timedelta(days=7)
    elif period == 'month':
        time_threshold = now_utc - timedelta(days=30)
    else:
        raise ValueError("Неверный период для топа рефералов.")

    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_referral_top_by_period ({period})...")
        query = '''
            SELECT referral_id, COUNT(*) as ref_count FROM users
            WHERE referral_id IS NOT NULL AND registration_time >= $1
            GROUP BY referral_id HAVING COUNT(*) > 0
            ORDER BY ref_count DESC LIMIT 10
        '''
        result = await conn.fetch(query, time_threshold)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_referral_top_by_period): {duration:.4f}s")
        log.debug(f"Releasing connection for get_referral_top_by_period ({period})...")
        return result


async def add_promocode(promocode: str, reward: float, max_uses: int, min_referrals: int):
    if not db_pool: return
    await _log_pool_stats("add_promocode")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for add_promocode ('{promocode}')...")
        await conn.execute('''
            INSERT INTO promocodes (promocode, reward, max_uses, min_referrals)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (promocode) DO UPDATE SET
                reward = excluded.reward,
                max_uses = excluded.max_uses,
                min_referrals = excluded.min_referrals
        ''', promocode, reward, max_uses, min_referrals)
        duration = time.monotonic() - start_time
        log.info(f"DB Query duration (add_promocode): {duration:.4f}s")
        log.debug(f"Releasing connection for add_promocode ('{promocode}')...")


async def use_promocode(user_id: int, promocode: str) -> tuple[bool, str]:
    if not db_pool: return False, "Ошибка: Нет соединения с БД."
    await _log_pool_stats("use_promocode")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for use_promocode ({user_id}, '{promocode}')...")
        async with conn.transaction():
            tx_start_time = time.monotonic()
            log.debug(f"Starting transaction for use_promocode ({user_id}, '{promocode}')...")
            try:
                used = await conn.fetchval("SELECT 1 FROM used_promocodes WHERE user_id = $1 AND promocode = $2",
                                           user_id, promocode)
                if used:
                    tx_duration = time.monotonic() - tx_start_time
                    log.debug(f"Transaction duration (use_promocode - already used): {tx_duration:.4f}s")
                    return False, "❌ Вы уже использовали этот промокод."

                promo_data = await conn.fetchrow(
                    "SELECT reward, max_uses, min_referrals FROM promocodes WHERE promocode = $1 FOR UPDATE",
                    promocode)
                if not promo_data:
                    tx_duration = time.monotonic() - tx_start_time
                    log.debug(f"Transaction duration (use_promocode - not found): {tx_duration:.4f}s")
                    return False, "❌ Промокод не найден."
                if promo_data['max_uses'] <= 0:
                    tx_duration = time.monotonic() - tx_start_time
                    log.debug(f"Transaction duration (use_promocode - limit reached): {tx_duration:.4f}s")
                    return False, "❌ Этот промокод уже исчерпал лимит использований."

                user_referral_count = await get_referrals_count(user_id)
                if user_referral_count < promo_data['min_referrals']:
                    tx_duration = time.monotonic() - tx_start_time
                    log.debug(f"Transaction duration (use_promocode - refs not met): {tx_duration:.4f}s")
                    return False, f"❌ Вам нужно хотя бы {promo_data['min_referrals']} рефералов (у вас {user_referral_count})."

                await conn.execute("UPDATE promocodes SET max_uses = max_uses - 1 WHERE promocode = $1", promocode)
                used_at = datetime.now(timezone.utc)
                await conn.execute("INSERT INTO used_promocodes (user_id, promocode, used_at) VALUES ($1, $2, $3)",
                                   user_id, promocode, used_at)
                await conn.execute("UPDATE users SET stars = stars + $1 WHERE id = $2", promo_data['reward'], user_id)

                log.info(
                    f"Пользователь {user_id} активировал промокод '{promocode}'. Начислено {promo_data['reward']} звезд.")

                updated_uses = await conn.fetchval("SELECT max_uses FROM promocodes WHERE promocode = $1", promocode)
                if updated_uses is not None and updated_uses <= 0:
                    await delete_promo(promocode)

                tx_duration = time.monotonic() - tx_start_time
                log.debug(f"Transaction duration (use_promocode - success): {tx_duration:.4f}s")
                return True, f"✅ Промокод <code>{escape(promocode)}</code> активирован! Вы получили {promo_data['reward']:.2f}⭐️."
            except Exception as e:
                tx_duration = time.monotonic() - tx_start_time
                log.exception(
                    f"Ошибка активации промокода {promocode} для пользователя {user_id}. Duration: {tx_duration:.4f}s Error: {e}")
                return False, "❌ Ошибка при активации промокода."
        duration = time.monotonic() - start_time
        log.debug(f"Total duration (use_promocode connection acquire + tx): {duration:.4f}s")
        log.debug(f"Releasing connection for use_promocode ({user_id}, '{promocode}')...")


async def check_promocode_usage(user_id: int, promocode: str) -> bool:
    if not db_pool: return False
    await _log_pool_stats("check_promocode_usage")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for check_promocode_usage ({user_id}, '{promocode}')...")
        used = await conn.fetchval("SELECT 1 FROM used_promocodes WHERE user_id = $1 AND promocode = $2", user_id,
                                   promocode)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (check_promocode_usage): {duration:.4f}s")
        log.debug(f"Releasing connection for check_promocode_usage ({user_id}, '{promocode}')...")
        return bool(used)


async def delete_promo(promocode: str) -> bool:
    if not db_pool: return False
    await _log_pool_stats("delete_promo")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for delete_promo ('{promocode}')...")
        await conn.execute("DELETE FROM used_promocodes WHERE promocode = $1", promocode)
        result = await conn.execute("DELETE FROM promocodes WHERE promocode = $1", promocode)
        duration = time.monotonic() - start_time
        deleted_main = int(result.split()[-1]) if result else 0
        if deleted_main > 0:
            log.info(f"Промокод '{promocode}' и история его использования удалены. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for delete_promo ('{promocode}')...")
        return deleted_main > 0


async def get_user_withdrawals(user_id: int, limit: int = 5) -> list[dict]:
    if not db_pool: return []
    await _log_pool_stats("get_user_withdrawals")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_user_withdrawals ({user_id}, limit={limit})...")
        rows = await conn.fetch('''
            SELECT amount, status, request_time
            FROM withdraw_requests
            WHERE user_id = $1
            ORDER BY request_time DESC
            LIMIT $2
        ''', user_id, limit)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_user_withdrawals): {duration:.4f}s")
        log.debug(f"Releasing connection for get_user_withdrawals ({user_id})...")
        return [dict(row) for row in rows]


async def get_all_promocodes() -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats("get_all_promocodes")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_all_promocodes...")
        result = await conn.fetch(
            'SELECT promocode, reward, max_uses, min_referrals FROM promocodes ORDER BY promocode')
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_all_promocodes): {duration:.4f}s")
        log.debug("Releasing connection for get_all_promocodes...")
        return result


async def get_promocode_reward(promocode: str) -> float | None:
    if not db_pool: return None
    await _log_pool_stats("get_promocode_reward")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_promocode_reward ('{promocode}')...")
        reward = await conn.fetchval("SELECT reward FROM promocodes WHERE promocode = $1", promocode)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_promocode_reward): {duration:.4f}s")
        log.debug(f"Releasing connection for get_promocode_reward ('{promocode}')...")
        return float(reward) if reward is not None else None


async def get_total_promocodes() -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_total_promocodes")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_total_promocodes...")
        count = await conn.fetchval("SELECT COUNT(*) FROM promocodes")
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_total_promocodes): {duration:.4f}s")
        log.debug("Releasing connection for get_total_promocodes...")
        return count or 0


async def get_active_promocodes() -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_active_promocodes")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_active_promocodes...")
        count = await conn.fetchval("SELECT COUNT(*) FROM promocodes WHERE max_uses > 0")
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_active_promocodes): {duration:.4f}s")
        log.debug("Releasing connection for get_active_promocodes...")
        return count or 0


async def add_task(channel_id_or_link: str, reward: float, max_completions: int, requires_subscription: bool = True):
    if not db_pool: return
    await _log_pool_stats("add_task")
    if max_completions <= 0: raise ValueError("max_completions должен быть положительным")
    task_type = "sub" if requires_subscription else "nosub"
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for add_task ('{channel_id_or_link}')...")
        await conn.execute(
            '''INSERT INTO tasks (channel_id, reward, max_completions, active, requires_subscription, task_type, completed_count)
               VALUES ($1, $2, $3, 1, $4, $5, 0)''',
            str(channel_id_or_link), reward, max_completions, int(requires_subscription), task_type
        )
        duration = time.monotonic() - start_time
        log.info(
            f"Задача добавлена: type={task_type}, target='{channel_id_or_link}', reward={reward}, limit={max_completions}. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for add_task ('{channel_id_or_link}')...")


async def remove_task(channel_id_or_link: str) -> bool:
    if not db_pool: return False
    await _log_pool_stats("remove_task")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for remove_task ('{channel_id_or_link}')...")
        task_ids = await conn.fetchvals('SELECT id FROM tasks WHERE channel_id = $1', str(channel_id_or_link))
        if task_ids:
            await conn.execute('DELETE FROM completed_tasks WHERE task_id = ANY($1::int[])', task_ids)
        result = await conn.execute('DELETE FROM tasks WHERE channel_id = $1', str(channel_id_or_link))
        duration = time.monotonic() - start_time
        deleted_count = int(result.split()[-1]) if result else 0
        if deleted_count > 0:
            log.info(f"Задание(я) для '{channel_id_or_link}' удалены. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for remove_task ('{channel_id_or_link}')...")
        return deleted_count > 0


async def get_tasks() -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats("get_tasks")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_tasks...")
        result = await conn.fetch('''
            SELECT id, channel_id, reward, completed_count, max_completions, requires_subscription, task_type, active
            FROM tasks WHERE active=1
        ''')
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_tasks): {duration:.4f}s")
        log.debug("Releasing connection for get_tasks...")
        return result


async def mark_task_completed(user_id: int, task_id: int):
    if not db_pool: return
    await _log_pool_stats("mark_task_completed")
    completed_at = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for mark_task_completed ({user_id}, {task_id})...")
        async with conn.transaction():
            tx_start_time = time.monotonic()
            try:
                inserted = await conn.execute('''
                    INSERT INTO completed_tasks (user_id, task_id, completed_at)
                    VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
                ''', user_id, task_id, completed_at)

                if inserted and int(inserted.split()[-1]) > 0:
                    await conn.execute('UPDATE tasks SET completed_count = completed_count + 1 WHERE id = $1', task_id)
                    log.debug(f"Отмечено выполнение задания {task_id} пользователем {user_id}.")
                else:
                    log.debug(f"Пользователь {user_id} уже выполнял задание {task_id} (ON CONFLICT).")
                tx_duration = time.monotonic() - tx_start_time
                log.debug(f"Transaction duration (mark_task_completed): {tx_duration:.4f}s")
            except Exception as e:
                tx_duration = time.monotonic() - tx_start_time
                log.error(
                    f"Ошибка отметки выполнения задания {task_id} для пользователя {user_id}. Duration: {tx_duration:.4f}s Error: {e}")
        duration = time.monotonic() - start_time
        log.debug(
            f"Releasing connection for mark_task_completed ({user_id}, {task_id}). Total duration: {duration:.4f}s")


async def user_completed_task(user_id: int, task_id: int) -> bool:
    if not db_pool: return False
    await _log_pool_stats("user_completed_task")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for user_completed_task ({user_id}, {task_id})...")
        completed = await conn.fetchval('SELECT 1 FROM completed_tasks WHERE user_id=$1 AND task_id=$2', user_id,
                                        task_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (user_completed_task): {duration:.4f}s")
        log.debug(f"Releasing connection for user_completed_task ({user_id}, {task_id})...")
        return bool(completed)


async def get_total_tasks() -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_total_tasks")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_total_tasks...")
        count = await conn.fetchval("SELECT COUNT(*) FROM tasks")
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_total_tasks): {duration:.4f}s")
        log.debug("Releasing connection for get_total_tasks...")
        return count or 0


async def get_active_tasks() -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_active_tasks")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_active_tasks...")
        count = await conn.fetchval("SELECT COUNT(*) FROM tasks WHERE active = 1")
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_active_tasks): {duration:.4f}s")
        log.debug("Releasing connection for get_active_tasks...")
        return count or 0


async def get_completed_tasks() -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_completed_tasks")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_completed_tasks...")
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM tasks WHERE completed_count >= max_completions AND active = 1")
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_completed_tasks): {duration:.4f}s")
        log.debug("Releasing connection for get_completed_tasks...")
        return count or 0


async def add_channel_db(channel_id: int, delete_timestamp_dt: datetime | None):
    if not db_pool: return
    await _log_pool_stats("add_channel_db")
    delete_ts_pg = delete_timestamp_dt.astimezone(timezone.utc) if delete_timestamp_dt else None
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for add_channel_db ({channel_id})...")
        try:
            await conn.execute('''
                INSERT INTO channels (channel_id, delete_time) VALUES ($1, $2)
                ON CONFLICT (channel_id) DO UPDATE SET delete_time = excluded.delete_time
            ''', channel_id, delete_ts_pg)
            duration = time.monotonic() - start_time
            log.info(f"Канал {channel_id} добавлен/обновлен. Время удаления: {delete_ts_pg}. Duration: {duration:.4f}s")
        except Exception as e:
            duration = time.monotonic() - start_time
            log.error(f"Ошибка добавления/обновления канала {channel_id}. Duration: {duration:.4f}s Error: {e}")
        finally:
            log.debug(f"Releasing connection for add_channel_db ({channel_id})...")


async def delete_channel_db(channel_id: int) -> bool:
    if not db_pool: return False
    await _log_pool_stats("delete_channel_db")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for delete_channel_db ({channel_id})...")
        result = await conn.execute('DELETE FROM channels WHERE channel_id = $1', channel_id)
        duration = time.monotonic() - start_time
        deleted_count = int(result.split()[-1]) if result else 0
        if deleted_count > 0:
            log.info(f"Канал {channel_id} удален из списка ОП. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for delete_channel_db ({channel_id})...")
        return deleted_count > 0


async def get_channels_db(get_delete_time=False) -> list[asyncpg.Record] | list[int]:
    if not db_pool: return []
    await _log_pool_stats("get_channels_db")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_channels_db...")
        if get_delete_time:
            result = await conn.fetch('SELECT channel_id, delete_time FROM channels ORDER BY id')
        else:
            rows = await conn.fetch('SELECT channel_id FROM channels ORDER BY id')
            result = [row['channel_id'] for row in rows]
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_channels_db, get_delete_time={get_delete_time}): {duration:.4f}s")
        log.debug("Releasing connection for get_channels_db...")
        return result


async def get_total_channels() -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_total_channels")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_total_channels...")
        count = await conn.fetchval("SELECT COUNT(*) FROM channels")
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_total_channels): {duration:.4f}s")
        log.debug("Releasing connection for get_total_channels...")
        return count or 0


async def get_active_channels() -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_active_channels")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_active_channels...")
        now_utc = datetime.now(timezone.utc)
        count = await conn.fetchval("SELECT COUNT(*) FROM channels WHERE delete_time IS NULL OR delete_time > $1",
                                    now_utc)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_active_channels): {duration:.4f}s")
        log.debug("Releasing connection for get_active_channels...")
        return count or 0


async def set_lucky_time(start_utc: datetime, duration_minutes: int = 60):
    end_utc = start_utc + timedelta(minutes=duration_minutes)
    await set_config_value('lucky_start', start_utc.isoformat())
    await set_config_value('lucky_end', end_utc.isoformat())
    log.info(f"Lucky time set: {start_utc.isoformat()} to {end_utc.isoformat()}")


async def is_lucky_time_now() -> bool:
    start_str = await get_config_value('lucky_start')
    end_str = await get_config_value('lucky_end')
    if start_str and end_str:
        try:
            start_utc = datetime.fromisoformat(start_str)
            end_utc = datetime.fromisoformat(end_str)
            now_utc = datetime.now(timezone.utc)
            return start_utc <= now_utc <= end_utc
        except ValueError as e:
            log.error(f"Could not parse lucky time from config: start='{start_str}', end='{end_str}'. Error: {e}")
            return False
    return False


async def are_withdrawals_enabled() -> bool:
    value = await get_config_value('withdrawals_enabled', default_value='1')
    return value == '1'


async def set_withdrawals_enabled(enabled: bool):
    value = '1' if enabled else '0'
    await set_config_value('withdrawals_enabled', value)
    log.info(f"Статус вывода средств изменен на: {'ВКЛЮЧЕН' if enabled else 'ВЫКЛЮЧЕН'}")


async def are_referrals_enabled() -> bool:
    value = await get_config_value('referrals_enabled', default_value='1')
    return value == '1'


async def set_referrals_enabled(enabled: bool):
    value = '1' if enabled else '0'
    await set_config_value('referrals_enabled', value)
    log.info(f"Статус реферальной программы изменен на: {'ВКЛЮЧЕНА' if enabled else 'ВЫКЛЮЧЕНА'}")


async def set_config_value(key: str, value: str | int | float | None):
    if not db_pool: return
    await _log_pool_stats(f"set_config_value ({key})")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for set_config_value ({key})...")
        await conn.execute('''
            INSERT INTO config (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = excluded.value
        ''', key, str(value) if value is not None else None)
        duration = time.monotonic() - start_time
        log.info(f"Config key '{key}' set to '{value}'. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for set_config_value ({key})...")


async def get_config_value(key: str, default_value: str | None = None) -> str | None:
    if not db_pool: return default_value
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        value = await conn.fetchval('SELECT value FROM config WHERE key=$1', key)
        duration = time.monotonic() - start_time
        log.debug(f"Config key '{key}' requested. Value: '{value}' (Default: '{default_value}')")
        return value if value is not None else default_value


async def get_wheel_daily_limit() -> int:
    value = await get_config_value('wheel_daily_limit', default_value=str(DEFAULT_WHEEL_DAILY_LIMIT))
    try:
        return int(value) if value else DEFAULT_WHEEL_DAILY_LIMIT
    except (ValueError, TypeError):
        return DEFAULT_WHEEL_DAILY_LIMIT


async def get_exchange_daily_limit() -> int:
    value = await get_config_value('exchange_daily_limit', default_value=str(DEFAULT_EXCHANGE_DAILY_LIMIT))
    try:
        return int(value) if value else DEFAULT_EXCHANGE_DAILY_LIMIT
    except (ValueError, TypeError):
        return DEFAULT_EXCHANGE_DAILY_LIMIT


async def get_exchange_referral_req() -> int:
    value = await get_config_value('exchange_referral_req', default_value=str(DEFAULT_EXCHANGE_REFERRAL_REQ))
    try:
        return int(value) if value else DEFAULT_EXCHANGE_REFERRAL_REQ
    except (ValueError, TypeError):
        return DEFAULT_EXCHANGE_REFERRAL_REQ


async def get_wheel_referral_req() -> int:
    value = await get_config_value('wheel_referral_req', default_value=str(DEFAULT_WHEEL_REFERRAL_REQ))
    try:
        return int(value) if value else DEFAULT_WHEEL_REFERRAL_REQ
    except (ValueError, TypeError):
        return DEFAULT_WHEEL_REFERRAL_REQ


async def get_project_balance() -> float:
    val = await get_config_value('project_balance')
    try:
        return float(val) if val is not None else 1000.0
    except (ValueError, TypeError):
        return 1000.0


async def set_project_balance(value: float | int):
    try:
        await set_config_value('project_balance', float(value))
    except (ValueError, TypeError):
        log.error(f"Неверное значение для баланса проекта: {value}")


async def get_total_withdrawn() -> float:
    if not db_pool: return 0.0
    await _log_pool_stats("get_total_withdrawn")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_total_withdrawn...")
        total = await conn.fetchval('SELECT SUM(withdrawn) FROM users')
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_total_withdrawn): {duration:.4f}s")
        log.debug("Releasing connection for get_total_withdrawn...")
        return float(total) if total is not None else 0.0


async def get_total_combined() -> float:
    if not db_pool: return 0.0
    await _log_pool_stats("get_total_combined")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_total_combined...")
        res = await conn.fetchrow('SELECT SUM(stars) as s, SUM(withdrawn) as w FROM users')
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_total_combined): {duration:.4f}s")
        total_stars = float(res['s']) if res and res['s'] is not None else 0.0
        total_withdrawn = float(res['w']) if res and res['w'] is not None else 0.0
        log.debug("Releasing connection for get_total_combined...")
        return total_stars + total_withdrawn


async def get_top_users() -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats("get_top_users")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_top_users...")
        result = await conn.fetch('''
            SELECT id, username, (stars + withdrawn) AS total_earned
            FROM users ORDER BY total_earned DESC LIMIT 10
        ''')
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_top_users): {duration:.4f}s")
        log.debug("Releasing connection for get_top_users...")
        return result


async def get_click_top() -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats("get_click_top")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_click_top...")
        result = await conn.fetch('''
            SELECT id, username, click_count
            FROM users WHERE click_count > 0
            ORDER BY click_count DESC LIMIT 10
        ''')
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_click_top): {duration:.4f}s")
        log.debug("Releasing connection for get_click_top...")
        return result


async def get_inactive_users(days: int) -> list[int]:
    if not db_pool: return []
    await _log_pool_stats(f"get_inactive_users ({days} days)")
    target_dt_utc = datetime.now(timezone.utc) - timedelta(days=days)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_inactive_users ({days} days)...")
        rows = await conn.fetch("SELECT id FROM users WHERE last_click_time IS NULL OR last_click_time < $1",
                                target_dt_utc)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_inactive_users): {duration:.4f}s")
        log.debug(f"Releasing connection for get_inactive_users ({days} days)...")
        return [row['id'] for row in rows]


async def is_user_blocked(user_id: int) -> bool:
    if not db_pool: return False
    await _log_pool_stats("is_user_blocked")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for is_user_blocked ({user_id})...")
        is_blocked = await conn.fetchval('SELECT is_blocked FROM block_status WHERE user_id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (is_user_blocked): {duration:.4f}s")
        log.debug(f"Releasing connection for is_user_blocked ({user_id})...")
        return bool(is_blocked == 1)


async def block_user_in_db(user_id: int) -> bool:
    if not db_pool: return False
    await _log_pool_stats("block_user_in_db")
    now_utc = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for block_user_in_db ({user_id})...")
        try:
            await conn.execute('''
                INSERT INTO block_status (user_id, is_blocked, blocked_at, unblocked_at)
                VALUES ($1, 1, $2, (SELECT unblocked_at FROM block_status WHERE user_id = $1))
                ON CONFLICT (user_id) DO UPDATE SET
                    is_blocked = 1,
                    blocked_at = excluded.blocked_at
            ''', user_id, now_utc)
            duration = time.monotonic() - start_time
            log.info(f"Пользователь {user_id} заблокирован в БД. Duration: {duration:.4f}s")
            log.debug(f"Releasing connection for block_user_in_db ({user_id})...")
            return True
        except Exception as e:
            duration = time.monotonic() - start_time
            log.error(f"Ошибка блокировки пользователя {user_id}. Duration: {duration:.4f}s Error: {e}")
            log.debug(f"Releasing connection for block_user_in_db ({user_id}) after error...")
            return False


async def unblock_user_in_db(user_id: int) -> bool:
    if not db_pool: return False
    await _log_pool_stats("unblock_user_in_db")
    now_utc = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for unblock_user_in_db ({user_id})...")
        try:
            res = await conn.execute('''
                UPDATE block_status SET is_blocked = 0, unblocked_at = $1
                WHERE user_id = $2 AND is_blocked = 1
            ''', now_utc, user_id)
            duration = time.monotonic() - start_time
            if res and int(res.split()[-1]) > 0:
                log.info(f"Пользователь {user_id} разблокирован в БД. Duration: {duration:.4f}s")
            else:
                log.info(
                    f"Пользователь {user_id} не был заблокирован или не найден в block_status. Duration: {duration:.4f}s")
            log.debug(f"Releasing connection for unblock_user_in_db ({user_id})...")
            return True
        except Exception as e:
            duration = time.monotonic() - start_time
            log.error(f"Ошибка разблокировки пользователя {user_id}. Duration: {duration:.4f}s Error: {e}")
            log.debug(f"Releasing connection for unblock_user_in_db ({user_id}) after error...")
            return False


async def get_last_robbery_time(user_id: int) -> datetime | None:
    if not db_pool: return None
    await _log_pool_stats("get_last_robbery_time")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_last_robbery_time ({user_id})...")
        robbery_time = await conn.fetchval('''
            SELECT robbery_time FROM robberies
            WHERE user_id = $1 ORDER BY robbery_time DESC LIMIT 1
        ''', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_last_robbery_time): {duration:.4f}s")
        log.debug(f"Releasing connection for get_last_robbery_time ({user_id})...")
        return robbery_time


async def update_last_robbery_time(user_id: int, target_user_id: int):
    if not db_pool: return
    await _log_pool_stats("update_last_robbery_time")
    current_time_utc = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for update_last_robbery_time ({user_id}->{target_user_id})...")
        await conn.execute('''
            INSERT INTO robberies (user_id, target_user_id, robbery_time)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, target_user_id) DO UPDATE SET robbery_time = excluded.robbery_time
        ''', user_id, target_user_id, current_time_utc)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (update_last_robbery_time): {duration:.4f}s")
        log.debug(f"Releasing connection for update_last_robbery_time ({user_id}->{target_user_id})...")


async def get_random_user(exclude_id: int | None = None) -> asyncpg.Record | None:
    if not db_pool: return None
    await _log_pool_stats("get_random_user")
    admin_ids_tuple = tuple(ADMIN_IDS)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_random_user (exclude: {exclude_id})...")
        where_clauses = ["stars > 0"]
        params = []
        if exclude_id is not None:
            params.append(exclude_id)
            where_clauses.append(f"id != ${len(params)}")
        if admin_ids_tuple:
            params.append(list(admin_ids_tuple))
            where_clauses.append(f"id != ALL(${len(params)}::bigint[])")

        where_sql = " AND ".join(where_clauses)
        query = f'''
            SELECT id, stars FROM users
            WHERE {where_sql}
            ORDER BY RANDOM() LIMIT 1
        '''
        result = await conn.fetchrow(query, *params)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_random_user): {duration:.4f}s")
        log.debug(f"Releasing connection for get_random_user...")
        return result


async def update_user_balance(user_id: int, new_balance: float):
    if not db_pool: return
    await _log_pool_stats("update_user_balance")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for update_user_balance ({user_id})...")
        await conn.execute("UPDATE users SET stars = GREATEST(0, $1) WHERE id = $2", new_balance, user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (update_user_balance): {duration:.4f}s")
        log.debug(f"Releasing connection for update_user_balance ({user_id})...")


async def set_custom_reward_in_db(user_id: int, min_reward: float, max_reward: float, duration_days: int | None = None):
    if not db_pool: return
    await _log_pool_stats("set_custom_reward_in_db")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for set_custom_reward_in_db ({user_id})...")
        await conn.execute('''
            INSERT INTO custom_rewards (user_id, min_reward, max_reward)
            VALUES ($1, $2, $3)
            ON CONFLICT(user_id) DO UPDATE SET min_reward=excluded.min_reward, max_reward=excluded.max_reward
        ''', user_id, min_reward, max_reward)
        duration = time.monotonic() - start_time
        log.info(f"Custom click reward for user {user_id} set to {min_reward}:{max_reward}. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for set_custom_reward_in_db ({user_id})...")


async def get_custom_reward_from_db(user_id: int) -> tuple[float, float]:
    if not db_pool: return CLICK_MIN_REWARD, CLICK_MAX_REWARD
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        result = await conn.fetchrow("SELECT min_reward, max_reward FROM custom_rewards WHERE user_id = $1", user_id)
        duration = time.monotonic() - start_time
        if duration > 0.05: log.debug(f"DB Query duration (get_custom_reward_from_db for {user_id}): {duration:.4f}s")
        if result and result['min_reward'] is not None and result['max_reward'] is not None:
            return result['min_reward'], result['max_reward']
        else:
            return CLICK_MIN_REWARD, CLICK_MAX_REWARD


async def set_ref_reward(user_id: int, min_f_reward: float, max_f_reward: float, duration_days: int | None = None):
    if not db_pool: return
    await _log_pool_stats("set_ref_reward")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for set_ref_reward ({user_id})...")
        await conn.execute('''
            INSERT INTO custom_rewards (user_id, min_f_reward, max_f_reward)
            VALUES ($1, $2, $3)
            ON CONFLICT(user_id) DO UPDATE SET min_f_reward=excluded.min_f_reward, max_f_reward=excluded.max_f_reward
        ''', user_id, min_f_reward, max_f_reward)
        duration = time.monotonic() - start_time
        log.info(
            f"Custom referral reward for user {user_id} set to {min_f_reward}:{max_f_reward}. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for set_ref_reward ({user_id})...")


async def get_referral_reward_range(user_id: int) -> tuple[float, float]:
    if not db_pool: return MIN_REF_REWARD, MAX_REF_REWARD
    await _log_pool_stats("get_referral_reward_range")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_referral_reward_range ({user_id})...")
        result = await conn.fetchrow("SELECT min_f_reward, max_f_reward FROM custom_rewards WHERE user_id = $1",
                                     user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_referral_reward_range): {duration:.4f}s")
        log.debug(f"Releasing connection for get_referral_reward_range ({user_id})...")
        if result and result['min_f_reward'] is not None and result['max_f_reward'] is not None:
            return result['min_f_reward'], result['max_f_reward']
        else:
            return MIN_REF_REWARD, MAX_REF_REWARD


async def get_unique_users_count() -> int:
    if not db_pool: return 0
    await _log_pool_stats("get_unique_users_count")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_unique_users_count...")
        count = await conn.fetchval('''
            SELECT COUNT(DISTINCT user_id)
            FROM custom_rewards
            WHERE min_reward IS NOT NULL OR max_reward IS NOT NULL
                  OR min_f_reward IS NOT NULL OR max_f_reward IS NOT NULL
        ''')
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_unique_users_count): {duration:.4f}s")
        log.debug("Releasing connection for get_unique_users_count...")
        return count or 0


async def update_verified_signups(special_code: str):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE special_links SET verified_signups = verified_signups + 1 WHERE special_code = $1",
                           special_code)


async def mark_onboarding_completed(user_id: int):
    if not db_pool: return
    await _log_pool_stats("mark_onboarding_completed")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for mark_onboarding_completed ({user_id})...")
        async with conn.transaction():
            tx_start_time = time.monotonic()
            log.debug(f"Starting transaction for mark_onboarding_completed ({user_id})...")
            updated_rows_result = await conn.execute(
                "UPDATE users SET completed_onboarding = 1 WHERE id = $1 AND completed_onboarding = 0", user_id)
            updated_rows = int(updated_rows_result.split()[-1]) if updated_rows_result else 0

            if updated_rows > 0:
                special_code = await conn.fetchval("SELECT special_ref FROM users WHERE id = $1", user_id)
                if special_code:
                    log.info(f"Пользователь {user_id} прошел онбординг по спец. ссылке: {special_code}")
                    await conn.execute(
                        "UPDATE special_links SET completed_onboarding = completed_onboarding + 1 WHERE special_code = $1",
                        special_code)
            else:
                log.debug(f"Онбординг для пользователя {user_id} уже был отмечен или пользователь не найден.")
            tx_duration = time.monotonic() - tx_start_time
            log.debug(f"Transaction duration (mark_onboarding_completed): {tx_duration:.4f}s")
        duration = time.monotonic() - start_time
        log.info(f"Отметка выполнения онбординга для пользователя {user_id}. Total duration: {duration:.4f}s")
        log.debug(f"Releasing connection for mark_onboarding_completed ({user_id})...")


async def get_user_referrals(user_id: int) -> tuple[list[asyncpg.Record], int, int]:
    if not db_pool: return [], 0, 0
    await _log_pool_stats("get_user_referrals")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_user_referrals ({user_id})...")
        all_referrals = await conn.fetch('''
            SELECT id, username, registration_time
            FROM users WHERE referral_id = $1
            ORDER BY registration_time DESC
        ''', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_user_referrals - fetch all): {duration:.4f}s")
    total_refs = len(all_referrals)
    weekly_refs = await get_referrals_count_week(user_id)
    log.debug(f"Releasing connection for get_user_referrals ({user_id})...")
    return all_referrals, total_refs, weekly_refs


async def add_sponsor_button(name: str, url: str):
    if not db_pool: return
    await _log_pool_stats("add_sponsor_button")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for add_sponsor_button ('{name}')...")
        await conn.execute("INSERT INTO sponsor_buttons (name, url) VALUES ($1, $2)", name, url)
        duration = time.monotonic() - start_time
        log.info(f"Sponsor button '{name}' added. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for add_sponsor_button ('{name}')...")


async def remove_sponsor_button(name: str, url: str) -> bool:
    if not db_pool: return False
    await _log_pool_stats("remove_sponsor_button")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for remove_sponsor_button ('{name}')...")
        result = await conn.execute("DELETE FROM sponsor_buttons WHERE name = $1 AND url = $2", name, url)
        duration = time.monotonic() - start_time
        deleted_count = int(result.split()[-1]) if result else 0
        log.info(f"Remove sponsor button result: {deleted_count}. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for remove_sponsor_button ('{name}')...")
        return deleted_count > 0


async def get_sponsor_buttons() -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats("get_sponsor_buttons")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_sponsor_buttons...")
        result = await conn.fetch("SELECT name, url FROM sponsor_buttons")
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_sponsor_buttons): {duration:.4f}s")
        log.debug("Releasing connection for get_sponsor_buttons...")
        return result


async def get_spent_stars_for_day(date_obj: date | None = None) -> float:
    if not db_pool: return 0.0
    target_date = date_obj if date_obj else date.today()
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        amount = await conn.fetchval("SELECT COALESCE(SUM(amount), 0.0) FROM spent_stars WHERE date = $1", target_date)
        duration = time.monotonic() - start_time
        if duration > 0.05: log.debug(f"DB Query duration (get_spent_stars_for_day): {duration:.4f}s")
        return float(amount) if amount is not None else 0.0


async def get_spent_stars_for_week() -> float:
    if not db_pool: return 0.0
    await _log_pool_stats("get_spent_stars_for_week")
    today = date.today()
    week_start_dt = today - timedelta(days=today.weekday())
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_spent_stars_for_week...")
        amount = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0.0) FROM spent_stars WHERE date >= $1 AND date <= $2", week_start_dt, today)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_spent_stars_for_week): {duration:.4f}s")
        log.debug("Releasing connection for get_spent_stars_for_week...")
        return float(amount) if amount is not None else 0.0


async def get_spent_stars_for_month() -> float:
    if not db_pool: return 0.0
    await _log_pool_stats("get_spent_stars_for_month")
    today = date.today()
    first_day_of_month_dt = today.replace(day=1)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug("Acquired connection for get_spent_stars_for_month...")
        amount = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0.0) FROM spent_stars WHERE date >= $1 AND date <= $2", first_day_of_month_dt,
            today)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_spent_stars_for_month): {duration:.4f}s")
        log.debug("Releasing connection for get_spent_stars_for_month...")
        return float(amount) if amount is not None else 0.0


async def get_daily_withdrawal_count(user_id: int, withdrawal_type: str) -> int:
    if not db_pool: return 0
    today_date = date.today()
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        count = await conn.fetchval(
            "SELECT count FROM daily_withdrawals WHERE user_id = $1 AND withdrawal_date = $2 AND withdrawal_type = $3",
            user_id, today_date, withdrawal_type
        )
        duration = time.monotonic() - start_time
        if duration > 0.05: log.debug(
            f"DB Query duration (get_daily_withdrawal_count for {user_id}/{withdrawal_type}): {duration:.4f}s")
        log.debug(
            f"Daily withdrawal count check: user={user_id}, type={withdrawal_type}, date={today_date}. Count: {count or 0}")
        return count or 0


async def increment_daily_withdrawal_count(conn: asyncpg.Connection, user_id: int,
                                           withdrawal_type: str) -> bool:
    today_date = date.today()
    log.debug(f"Operating on existing connection for increment_daily_withdrawal_count ({user_id}/{withdrawal_type})...")
    try:
        await conn.execute(''' 
            INSERT INTO daily_withdrawals (user_id, withdrawal_date, withdrawal_type, count)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (user_id, withdrawal_date, withdrawal_type) DO UPDATE SET
                count = daily_withdrawals.count + 1;
        ''', user_id, today_date, withdrawal_type)
        log.info(
            f"Incremented daily withdrawal count for user={user_id}, type={withdrawal_type}, date={today_date} (using provided conn)")
        return True
    except Exception as e:
        log.exception(
            f"Failed to increment daily withdrawal count for user {user_id}, type {withdrawal_type} (using provided conn). Error: {e}")
        return False


async def get_last_click_time(user_id: int) -> datetime | None:
    if not db_pool: return None
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        result = await conn.fetchval('SELECT last_click_time FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        if duration > 0.05: log.debug(f"DB Query duration (get_last_click_time for {user_id}): {duration:.4f}s")
        return result


async def update_last_click_time(user_id: int):
    if not db_pool: return
    now_utc = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        await conn.execute('UPDATE users SET last_click_time = $1 WHERE id = $2', now_utc, user_id)
        duration = time.monotonic() - start_time
        if duration > 0.05: log.debug(f"DB Query duration (update_last_click_time for {user_id}): {duration:.4f}s")


async def increment_click_count(user_id: int):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        await conn.execute('UPDATE users SET click_count = click_count + 1 WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        if duration > 0.05: log.debug(f"DB Query duration (increment_click_count for {user_id}): {duration:.4f}s")


async def get_last_gift(user_id: int) -> datetime | None:
    if not db_pool: return None
    await _log_pool_stats("get_last_gift")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_last_gift ({user_id})...")
        result = await conn.fetchval('SELECT last_gift_time FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_last_gift): {duration:.4f}s")
        log.debug(f"Releasing connection for get_last_gift ({user_id})...")
        return result


async def update_last_gift(user_id: int):
    if not db_pool: return
    await _log_pool_stats("update_last_gift")
    now_utc = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for update_last_gift ({user_id})...")
        await conn.execute('UPDATE users SET last_gift_time = $1 WHERE id = $2', now_utc, user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (update_last_gift): {duration:.4f}s")
        log.debug(f"Releasing connection for update_last_gift ({user_id})...")


async def increment_gift_count(user_id: int):
    if not db_pool: return
    await _log_pool_stats("increment_gift_count")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for increment_gift_count ({user_id})...")
        await conn.execute('UPDATE users SET gift_count = gift_count + 1 WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (increment_gift_count): {duration:.4f}s")
        log.debug(f"Releasing connection for increment_gift_count ({user_id})...")


async def get_last_free_spin_time(user_id: int) -> datetime | None:
    if not db_pool: return None
    await _log_pool_stats("get_last_free_spin_time")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_last_free_spin_time ({user_id})...")
        result = await conn.fetchval('SELECT last_free_spin_time FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_last_free_spin_time): {duration:.4f}s")
        log.debug(f"Releasing connection for get_last_free_spin_time ({user_id})...")
        return result


async def update_last_free_spin_time(user_id: int):
    if not db_pool: return
    await _log_pool_stats("update_last_free_spin_time")
    now_utc = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for update_last_free_spin_time ({user_id})...")
        await conn.execute('UPDATE users SET last_free_spin_time = $1 WHERE id = $2', now_utc, user_id)
        duration = time.monotonic() - start_time
        log.info(f"Updated last free spin time for user {user_id} to {now_utc.isoformat()}. Duration: {duration:.4f}s")
        log.debug(f"Releasing connection for update_last_free_spin_time ({user_id})...")


async def create_wheel_win_request(conn: asyncpg.Connection, user_id: int, amount: float, emoji: str,
                                   gift_id: int | None, prize_name: str) -> int | None:
    try:
        start_time = time.monotonic()
        admin_description = f"🎡 Выигрыш: {prize_name} {emoji}"
        request_id = await conn.fetchval('''
            INSERT INTO withdraw_requests (user_id, amount, status, gift_id, emoji, request_time)
            VALUES ($1, $2, 'pending', $3, $4, CURRENT_TIMESTAMP)
            RETURNING id
        ''', user_id, amount, gift_id, admin_description)
        duration = time.monotonic() - start_time

        if request_id:
            log.info(
                f"Wheel win withdrawal request {request_id} recorded user {user_id}, prize={prize_name}, amount={amount}, gift_id={gift_id}. Duration: {duration:.4f}s")
            return request_id
        else:
            log.error(
                f"Failed to get RETURNING id for wheel win request user {user_id}, prize={prize_name}. Duration: {duration:.4f}s")
            return None
    except Exception as e:
        log.exception(f"Failed to create wheel win request user {user_id}, prize={prize_name}: {e}")
        return None


async def get_user_username(user_id: int) -> str | None:
    if not db_pool: return None
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        result = await conn.fetchval('SELECT username FROM users WHERE id = $1', user_id)
        duration = time.monotonic() - start_time
        if duration > 0.05: log.debug(f"DB Query duration (get_user_username for {user_id}): {duration:.4f}s")
        return result


async def add_game_history_record(user_id: int, game_type: str, amount: float, description: str | None = None,
                                  max_retries=3, initial_delay=0.1):
    if not db_pool: return False
    await _log_pool_stats(f"add_game_history_record ({user_id},{game_type})")
    if not isinstance(amount, (int, float)):
        log.warning(
            f"Попытка добавить неверную сумму {amount} в историю игр для пользователя {user_id}, тип {game_type}")
        return False

    retries = 0
    while retries <= max_retries:
        try:
            async with db_pool.acquire() as conn:
                start_time = time.monotonic()
                log.debug(f"Acquired connection for add_game_history_record ({user_id},{game_type})...")
                async with conn.transaction():
                    tx_start_time = time.monotonic()
                    await conn.execute('''
                        INSERT INTO game_history (user_id, game_type, amount, description, timestamp)
                        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                    ''', user_id, game_type, amount, description)
                    tx_duration = time.monotonic() - tx_start_time
                duration = time.monotonic() - start_time
                log.info(
                    f"Запись истории игры: user={user_id}, type={game_type}, amount={amount:.2f}, desc={description}. TX dur: {tx_duration:.4f}s, Total dur: {duration:.4f}s")
                log.debug(f"Releasing connection for add_game_history_record ({user_id},{game_type})...")
                return True
        except (asyncpg.exceptions.DeadlockDetectedError, asyncpg.exceptions.CannotConnectNowError,
                asyncpg.exceptions.InterfaceError) as e:
            if retries < max_retries:
                retries += 1
                delay = initial_delay * (2 ** (retries - 1)) + random.uniform(0, initial_delay * 0.5)
                log.warning(
                    f"DB lock/connection error on history write for user {user_id}. Retrying ({retries}/{max_retries}) after {delay:.2f}s... Error: {e}")
                await asyncio.sleep(delay)
            else:
                log.exception(
                    f"Failed to add game history record for user {user_id} after retries or due to other OperationalError: {e}")
                return False
        except Exception as e:
            log.exception(f"Неожиданная ошибка добавления записи истории игры для пользователя {user_id}: {e}")
            return False
    log.error(
        f"Failed to add game history record for user {user_id} after all retries due to locking/connection issues.")
    return False


async def get_game_history(user_id: int, limit: int = 20) -> list[asyncpg.Record]:
    if not db_pool: return []
    await _log_pool_stats("get_game_history")
    async with db_pool.acquire() as conn:
        start_time = time.monotonic()
        log.debug(f"Acquired connection for get_game_history ({user_id}, limit={limit})...")
        result = await conn.fetch('''
            SELECT game_type, amount, description, timestamp
            FROM game_history
            WHERE user_id = $1
            ORDER BY timestamp DESC
            LIMIT $2
        ''', user_id, limit)
        duration = time.monotonic() - start_time
        log.debug(f"DB Query duration (get_game_history): {duration:.4f}s")
        log.debug(f"Releasing connection for get_game_history ({user_id})...")
        return result


async def get_selected_daily_gift() -> int | None:
    if not db_pool: return None
    default_gift_id = AVAILABLE_DAILY_GIFTS.get(DEFAULT_DAILY_GIFT_KEY)
    gift_id_str = await get_config_value('selected_daily_gift_id')
    if gift_id_str:
        try:
            return int(gift_id_str)
        except (ValueError, TypeError):
            log.error(f"Invalid daily gift ID in config: '{gift_id_str}'. Falling back to default.")
            return default_gift_id
    else:
        return default_gift_id


async def set_selected_daily_gift(gift_id: int):
    if not db_pool: return
    await set_config_value('selected_daily_gift_id', str(gift_id))


async def activate_boost_in_db(user_id: int, boost_id_key: str, boost_details: dict) -> bool:
    if not db_pool:
        log.error("activate_boost_in_db: DB pool not initialized!")
        return False

    await _log_pool_stats("activate_boost_in_db")

    now_utc = datetime.now(timezone.utc)
    duration_hours = 0
    boost_params_to_store = {"purchase_price_stars": boost_details.get("price_stars")}

    if "speed_boost_7d" == boost_id_key:
        duration_hours = 7 * 24
        boost_params_to_store["type"] = "farm_speed"
        boost_params_to_store["effect_value"] = 1.5
    elif "luck_boost_3h" == boost_id_key:
        duration_hours = 3
        boost_params_to_store["type"] = "game_luck"
        boost_params_to_store["effect_value"] = 10
    else:
        log.error(f"activate_boost_in_db: Неизвестный boost_id_key '{boost_id_key}' для пользователя {user_id}")
        return False

    if duration_hours <= 0:
        log.error(f"activate_boost_in_db: Нулевая или отрицательная длительность для буста '{boost_id_key}'")
        return False

    expiration_time = now_utc + timedelta(hours=duration_hours)

    async with db_pool.acquire() as conn:
        start_time_tx = time.monotonic()
        try:
            await conn.execute('''
                INSERT INTO user_active_boosts (user_id, boost_id_key, activation_time, expiration_time, boost_params)
                VALUES ($1, $2, $3, $4, $5)
            ''', user_id, boost_id_key, now_utc, expiration_time, json.dumps(boost_params_to_store))

            duration_tx = time.monotonic() - start_time_tx
            log.info(
                f"Буст '{boost_id_key}' успешно активирован для пользователя {user_id} до {expiration_time.isoformat()}. "
                f"Детали: {boost_params_to_store}. Duration: {duration_tx:.4f}s")
            return True
        except Exception as e:
            duration_tx = time.monotonic() - start_time_tx
            log.exception(f"Ошибка активации буста '{boost_id_key}' для пользователя {user_id} в БД. "
                          f"Duration: {duration_tx:.4f}s Error: {e}")
            return False


async def get_active_boosts_by_type(user_id: int, boost_type_prefix: str) -> list[asyncpg.Record]:
    if not db_pool: return []

    now_utc = datetime.now(timezone.utc)
    async with db_pool.acquire() as conn:
        start_time_q = time.monotonic()
        query = '''
            SELECT id, user_id, boost_id_key, activation_time, expiration_time, boost_params, is_active
            FROM user_active_boosts
            WHERE user_id = $1 AND boost_id_key LIKE $2 AND expiration_time > $3 AND is_active = TRUE
            ORDER BY expiration_time DESC
        '''
        active_boosts = await conn.fetch(query, user_id, f"{boost_type_prefix}%", now_utc)
        duration_q = time.monotonic() - start_time_q
        if duration_q > 0.01:
            log.debug(
                f"DB Query duration (get_active_boosts_by_type for {user_id}, prefix '{boost_type_prefix}'): {duration_q:.4f}s. Found: {len(active_boosts)}")
        return active_boosts


async def get_active_farm_speed_multiplier(user_id: int) -> float:
    active_speed_boosts = await get_active_boosts_by_type(user_id, "speed_boost")

    current_multiplier = 1.0
    if active_speed_boosts:
        latest_boost = active_speed_boosts[0]
        if latest_boost['boost_params'] and isinstance(latest_boost['boost_params'], dict):
            effect_val = latest_boost['boost_params'].get('effect_value')
            if isinstance(effect_val, (int, float)) and effect_val > 0:
                current_multiplier = effect_val
                log.debug(
                    f"User {user_id} has active farm speed boost. Multiplier: {current_multiplier} from boost_id: {latest_boost['boost_id_key']}")

    return current_multiplier


async def get_active_luck_boost_percentage(user_id: int) -> float:
    active_luck_boosts = await get_active_boosts_by_type(user_id, "luck_boost")

    luck_increase = 0.0
    if active_luck_boosts:
        latest_boost = active_luck_boosts[0]
        if latest_boost['boost_params'] and isinstance(latest_boost['boost_params'], dict):
            effect_val = latest_boost['boost_params'].get('effect_value')
            if isinstance(effect_val, (int, float)) and effect_val > 0:
                luck_increase = effect_val
                log.debug(
                    f"User {user_id} has active luck boost. Increase: {luck_increase}% from boost_id: {latest_boost['boost_id_key']}")

    return luck_increase


# --- Режим тех. работ ---

async def is_maintenance_mode() -> bool:
    value = await get_config_value('maintenance_mode', default_value='0')
    return value == '1'


async def set_maintenance_mode(enabled: bool):
    await set_config_value('maintenance_mode', '1' if enabled else '0')


async def get_maintenance_message() -> str:
    return await get_config_value('maintenance_message', default_value='⚙️ Бот на тех. обслуживании. Пожалуйста, подождите.') or '⚙️ Бот на тех. обслуживании.'


async def set_maintenance_message(text: str):
    await set_config_value('maintenance_message', text)


async def get_maintenance_end_text() -> str:
    return await get_config_value('maintenance_end_text', default_value='✅ Тех. работы завершены! Бот снова работает.') or '✅ Тех. работы завершены!'


async def set_maintenance_end_text(text: str):
    await set_config_value('maintenance_end_text', text)


async def get_all_user_ids() -> list:
    if not db_pool: return []
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM users")
        return [row['id'] for row in rows]


# --- Огонёк (Streak) ---

DEFAULT_STREAK_DAYS = 10
DEFAULT_STREAK_REWARD = 15.0


async def get_streak_days_required() -> int:
    value = await get_config_value('streak_days_required', default_value=str(DEFAULT_STREAK_DAYS))
    try:
        return int(value)
    except (ValueError, TypeError):
        return DEFAULT_STREAK_DAYS


async def get_streak_reward() -> float:
    value = await get_config_value('streak_reward', default_value=str(DEFAULT_STREAK_REWARD))
    try:
        return float(value)
    except (ValueError, TypeError):
        return DEFAULT_STREAK_REWARD


async def update_user_streak(user_id: int) -> dict:
    """
    Обновляет стрик пользователя при входе.
    Возвращает: {streak, reward_given, reward_amount, already_logged}
    """
    if not db_pool:
        return {'streak': 0, 'reward_given': False, 'reward_amount': 0, 'already_logged': False}

    today = date.today()

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT login_streak, last_login_date FROM users WHERE id = $1', user_id
        )
        if not row:
            return {'streak': 0, 'reward_given': False, 'reward_amount': 0, 'already_logged': False}

        current_streak = row['login_streak'] or 0
        last_login = row['last_login_date']

        if last_login == today:
            return {'streak': current_streak, 'reward_given': False, 'reward_amount': 0, 'already_logged': True}

        yesterday = today - timedelta(days=1)

        if last_login == yesterday:
            new_streak = current_streak + 1
        else:
            new_streak = 1

        await conn.execute(
            'UPDATE users SET login_streak = $1, last_login_date = $2 WHERE id = $3',
            new_streak, today, user_id
        )

        streak_days_required = await get_streak_days_required()
        reward_given = False
        reward_amount = 0.0

        if streak_days_required > 0 and new_streak > 0 and new_streak % streak_days_required == 0:
            reward_amount = await get_streak_reward()
            if reward_amount > 0:
                await conn.execute('UPDATE users SET stars = stars + $1 WHERE id = $2', reward_amount, user_id)
                reward_given = True
                log.info(f"User {user_id} reached streak {new_streak}, awarded {reward_amount} stars")

        return {
            'streak': new_streak,
            'reward_given': reward_given,
            'reward_amount': reward_amount,
            'already_logged': False
        }


async def get_user_streak(user_id: int) -> int:
    if not db_pool: return 0
    async with db_pool.acquire() as conn:
        val = await conn.fetchval('SELECT login_streak FROM users WHERE id = $1', user_id)
        return val or 0


# --- Прокси-магазин ---

async def add_proxy(proxy_type: str, address: str, price: float) -> int:
    if not db_pool: return 0
    async with db_pool.acquire() as conn:
        proxy_id = await conn.fetchval(
            'INSERT INTO proxies (proxy_type, address, price) VALUES ($1, $2, $3) RETURNING id',
            proxy_type, address, price
        )
        log.info(f"Proxy added: id={proxy_id}, type={proxy_type}, price={price}")
        return proxy_id


async def get_available_proxies() -> list:
    if not db_pool: return []
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT id, proxy_type, price, added_at FROM proxies WHERE is_sold = FALSE ORDER BY price ASC'
        )
        return [dict(r) for r in rows]


async def get_all_proxies(include_sold=False) -> list:
    if not db_pool: return []
    async with db_pool.acquire() as conn:
        if include_sold:
            rows = await conn.fetch('SELECT * FROM proxies ORDER BY id DESC')
        else:
            rows = await conn.fetch('SELECT * FROM proxies WHERE is_sold = FALSE ORDER BY id DESC')
        return [dict(r) for r in rows]


async def get_proxy_by_id(proxy_id: int):
    if not db_pool: return None
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM proxies WHERE id = $1', proxy_id)
        return dict(row) if row else None


async def buy_proxy(user_id: int, proxy_id: int) -> tuple:
    if not db_pool:
        return False, "❌ Ошибка БД.", None

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            proxy = await conn.fetchrow(
                'SELECT * FROM proxies WHERE id = $1 AND is_sold = FALSE FOR UPDATE', proxy_id
            )
            if not proxy:
                return False, "❌ Прокси не найден или уже продан.", None

            price = proxy['price']
            address = proxy['address']

            user = await conn.fetchrow('SELECT stars FROM users WHERE id = $1 FOR UPDATE', user_id)
            if not user:
                return False, "❌ Пользователь не найден.", None

            if user['stars'] < price:
                return False, f"❌ Недостаточно звёзд! Нужно: {price:.2f}⭐, у тебя: {user['stars']:.2f}⭐", None

            await conn.execute('UPDATE users SET stars = stars - $1 WHERE id = $2', price, user_id)
            await conn.execute(
                'UPDATE proxies SET is_sold = TRUE, sold_to = $1, sold_at = CURRENT_TIMESTAMP WHERE id = $2',
                user_id, proxy_id
            )
            await conn.execute(
                'INSERT INTO proxy_purchases (user_id, proxy_id, price) VALUES ($1, $2, $3)',
                user_id, proxy_id, price
            )

            log.info(f"User {user_id} bought proxy {proxy_id} for {price} stars")
            return True, f"✅ Прокси куплен за {price:.2f}⭐!", address


async def delete_proxy(proxy_id: int) -> bool:
    if not db_pool: return False
    async with db_pool.acquire() as conn:
        result = await conn.execute('DELETE FROM proxies WHERE id = $1 AND is_sold = FALSE', proxy_id)
        deleted = result.split()[-1] != '0'
        if deleted:
            log.info(f"Proxy {proxy_id} deleted from shop")
        return deleted


async def get_user_purchased_proxies(user_id: int) -> list:
    if not db_pool: return []
    async with db_pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT p.id, p.proxy_type, p.address, p.price, pp.purchased_at
            FROM proxy_purchases pp
            JOIN proxies p ON pp.proxy_id = p.id
            WHERE pp.user_id = $1
            ORDER BY pp.purchased_at DESC
        ''', user_id)
        return [dict(r) for r in rows]


async def get_proxy_stats() -> dict:
    if not db_pool:
        return {'total': 0, 'available': 0, 'sold': 0, 'revenue': 0}
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM proxies")
        available = await conn.fetchval("SELECT COUNT(*) FROM proxies WHERE is_sold = FALSE")
        sold = await conn.fetchval("SELECT COUNT(*) FROM proxies WHERE is_sold = TRUE")
        revenue = await conn.fetchval("SELECT COALESCE(SUM(price), 0) FROM proxies WHERE is_sold = TRUE")
        return {'total': total, 'available': available, 'sold': sold, 'revenue': revenue}
