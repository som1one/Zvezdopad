import sqlite3
import time
import random
import logging
from datetime import datetime, timedelta, date
from html import escape

from settings import (
    WIN_CHANCE, MAX_REF_REWARD, MIN_REF_REWARD,
    CLICK_MAX_REWARD, CLICK_MIN_REWARD, ADMIN_IDS,
    CLICK_MIN_REWARD_X2, CLICK_MAX_REWARD_X2,
    REF_VIVOD_MIN, AVAILABLE_DAILY_GIFTS, DEFAULT_DAILY_GIFT_KEY, TOKEN
)

log = logging.getLogger(__name__)

DEFAULT_WHEEL_REFERRAL_REQ = 10
DEFAULT_WHEEL_DAILY_LIMIT = 10
DEFAULT_EXCHANGE_DAILY_LIMIT = 5
DEFAULT_EXCHANGE_REFERRAL_REQ = REF_VIVOD_MIN


def get_db_connection():
    conn = sqlite3.connect('database.db', timeout=20.0)  # <--- Увеличено
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode=WAL;")  # <--- Раскомментировано
        log.debug("WAL mode enabled for DB connection.")
    except sqlite3.Error as e:
        log.error(f"Error setting PRAGMA on new connection: {e}")
    return conn


def check_and_create_tables():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        tables_to_create = {
            'users': '''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    stars REAL DEFAULT 0.0,
                    count_refs INTEGER DEFAULT 0,
                    referral_id INTEGER DEFAULT NULL,
                    withdrawn REAL DEFAULT 0.0,
                    lang TEXT NOT NULL DEFAULT 'ru',
                    ref_rewarded INTEGER DEFAULT 0,
                    second_level_rewards REAL DEFAULT 0.0,
                    last_gift_time TEXT DEFAULT NULL,
                    click_count INTEGER DEFAULT 0,
                    gift_count INTEGER DEFAULT 0,
                    registration_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    special_ref TEXT DEFAULT NULL,
                    completed_onboarding INTEGER DEFAULT 0,
                    last_click_time TEXT DEFAULT NULL,
                    last_free_spin_time TEXT DEFAULT NULL
                )
            ''',
            'robberies': '''
                CREATE TABLE IF NOT EXISTS robberies (
                    user_id INTEGER NOT NULL,
                    target_user_id INTEGER NOT NULL,
                    robbery_time TEXT NOT NULL,
                    PRIMARY KEY (user_id, target_user_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(target_user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'custom_rewards': '''
                CREATE TABLE IF NOT EXISTS custom_rewards (
                    user_id INTEGER PRIMARY KEY,
                    min_reward REAL,
                    max_reward REAL,
                    min_f_reward REAL,
                    max_f_reward REAL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'tasks': '''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    reward REAL NOT NULL,
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
                    reward REAL NOT NULL,
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    min_referrals INTEGER NOT NULL DEFAULT 0
                )
            ''',
            'channels': '''
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER UNIQUE NOT NULL,
                    delete_time INTEGER
                )
            ''',
            'special_links': '''
                CREATE TABLE IF NOT EXISTS special_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL
                )
            ''',
            'spent_stars': '''
                CREATE TABLE IF NOT EXISTS spent_stars (
                    date TEXT PRIMARY KEY,
                    amount REAL NOT NULL DEFAULT 0.0
                )
            ''',
            'special_link_visits': '''
                CREATE TABLE IF NOT EXISTS special_link_visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    special_code TEXT NOT NULL,
                    visit_time TEXT NOT NULL,
                    UNIQUE(user_id, special_code),
                    FOREIGN KEY(special_code) REFERENCES special_links(special_code) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'block_status': '''
                CREATE TABLE IF NOT EXISTS block_status (
                    user_id INTEGER PRIMARY KEY,
                    is_blocked INTEGER DEFAULT 0,
                    blocked_at TEXT,
                    unblocked_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'completed_tasks': '''
                CREATE TABLE IF NOT EXISTS completed_tasks (
                    user_id INTEGER NOT NULL,
                    task_id INTEGER NOT NULL,
                    completed_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, task_id),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            ''',
            'used_promocodes': '''
                CREATE TABLE IF NOT EXISTS used_promocodes (
                    user_id INTEGER NOT NULL,
                    promocode TEXT NOT NULL,
                    used_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, promocode),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    request_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    processed_time TEXT,
                    gift_id INTEGER,
                    emoji TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'daily_withdrawals': '''
                CREATE TABLE IF NOT EXISTS daily_withdrawals (
                    user_id INTEGER NOT NULL,
                    withdrawal_date TEXT NOT NULL,
                    withdrawal_type TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, withdrawal_date, withdrawal_type),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''',
            'game_history': '''
                CREATE TABLE IF NOT EXISTS game_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    game_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            '''
        }

        log.info("Creating/checking tables...")
        for table_name, create_query in tables_to_create.items():
            try:
                cursor.execute(create_query)
            except sqlite3.Error as e:
                log.error(f"Error creating table {table_name}: {e}")
                if "unrecognized token" in str(e):
                    raise

        log.info("Checking/adding missing columns...")
        add_missing_columns(cursor)

        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='withdraw_requests'")
            if cursor.fetchone():
                updated_count = cursor.execute(
                    "UPDATE withdraw_requests SET request_time = CURRENT_TIMESTAMP WHERE request_time IS NULL"
                ).rowcount
                if updated_count > 0:
                    log.info(f"Updated NULL request_time for {updated_count} withdrawal requests.")
        except sqlite3.Error as e:
            log.error(f"Error updating old NULL request_time values in withdraw_requests: {e}")

        try:
            conn.commit()
        except sqlite3.Error as e:
            log.error(f"Error committing schema changes: {e}")
            conn.rollback()

    log.info("Database schema initialization process finished.")


def add_column_if_not_exists(cursor, table_name, column_name, column_definition):
    try:
        cursor.execute(f"PRAGMA table_info(`{table_name}`)")
        columns = [column['name'] for column in cursor.fetchall()]
        if column_name not in columns:
            cursor.execute(f'ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {column_definition}')
            log.info(f"Column '{column_name}' added to table '{table_name}'.")
    except sqlite3.Error as e:
        log.error(f"Error adding column {column_name} to table {table_name}: {e}")


def add_missing_columns(cursor):
    table_columns = {
        'users': [
            ('username', 'TEXT'),
            ('stars', 'REAL DEFAULT 0.0'),
            ('count_refs', 'INTEGER DEFAULT 0'),
            ('referral_id', 'INTEGER DEFAULT NULL'),
            ('withdrawn', 'REAL DEFAULT 0.0'),
            ('lang', "TEXT NOT NULL DEFAULT 'ru'"),
            ('ref_rewarded', 'INTEGER DEFAULT 0'),
            ('second_level_rewards', 'REAL DEFAULT 0.0'),
            ('last_gift_time', 'TEXT DEFAULT NULL'),
            ('click_count', 'INTEGER DEFAULT 0'),
            ('gift_count', 'INTEGER DEFAULT 0'),
            ('registration_time', 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP'),
            ('special_ref', 'TEXT DEFAULT NULL'),
            ('completed_onboarding', 'INTEGER DEFAULT 0'),
            ('last_click_time', 'TEXT DEFAULT NULL'),
            ('last_free_spin_time', 'TEXT DEFAULT NULL')
        ],
        'daily_withdrawals': [
            ('withdrawal_date', 'TEXT NOT NULL'),
            ('withdrawal_type', 'TEXT NOT NULL'),
            ('count', 'INTEGER NOT NULL DEFAULT 0')
        ],
        'custom_rewards': [
            ('min_reward', 'REAL'),
            ('max_reward', 'REAL'),
            ('min_f_reward', 'REAL'),
            ('max_f_reward', 'REAL')
        ],
        'tasks': [
            ('channel_id', 'TEXT NOT NULL'),
            ('reward', 'REAL NOT NULL'),
            ('completed_count', 'INTEGER DEFAULT 0'),
            ('max_completions', 'INTEGER NOT NULL'),
            ('active', 'INTEGER DEFAULT 1'),
            ('requires_subscription', 'INTEGER DEFAULT 1'),
            ('task_type', "TEXT DEFAULT 'sub'")
        ],
        'promocodes': [
            ('reward', 'REAL NOT NULL'),
            ('max_uses', 'INTEGER NOT NULL DEFAULT 1'),
            ('min_referrals', 'INTEGER NOT NULL DEFAULT 0')
        ],
        'channels': [
            ('channel_id', 'INTEGER UNIQUE NOT NULL'),
            ('delete_time', 'INTEGER')
        ],
        'special_links': [
            ('user_id', 'INTEGER NOT NULL'),
            ('special_code', 'TEXT UNIQUE NOT NULL'),
            ('unique_visits', 'INTEGER DEFAULT 0'),
            ('total_visits', 'INTEGER DEFAULT 0'),
            ('verified_signups', 'INTEGER DEFAULT 0'),
            ('completed_onboarding', 'INTEGER DEFAULT 0')
        ],
        'sponsor_buttons': [
            ('name', 'TEXT NOT NULL'),
            ('url', 'TEXT NOT NULL')
        ],
        'spent_stars': [
            ('amount', 'REAL NOT NULL DEFAULT 0.0')
        ],
        'special_link_visits': [
            ('user_id', 'INTEGER NOT NULL'),
            ('special_code', 'TEXT NOT NULL'),
            ('visit_time', 'TEXT NOT NULL')
        ],
        'block_status': [
            ('is_blocked', 'INTEGER DEFAULT 0'),
            ('blocked_at', 'TEXT'),
            ('unblocked_at', 'TEXT')
        ],
        'completed_tasks': [
            ('user_id', 'INTEGER NOT NULL'),
            ('task_id', 'INTEGER NOT NULL'),
            ('completed_at', 'TEXT NOT NULL')
        ],
        'used_promocodes': [
            ('user_id', 'INTEGER NOT NULL'),
            ('promocode', 'TEXT NOT NULL'),
            ('used_at', 'TEXT NOT NULL')
        ],
        'withdraw_requests': [
            ('user_id', 'INTEGER NOT NULL'),
            ('amount', 'REAL NOT NULL'),
            ('status', "TEXT NOT NULL DEFAULT 'pending'"),
            ('request_time', 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP'),
            ('processed_time', 'TEXT'),
            ('gift_id', 'INTEGER'),
            ('emoji', 'TEXT')
        ],
        'robberies': [
            ('user_id', 'INTEGER NOT NULL'),
            ('target_user_id', 'INTEGER NOT NULL'),
            ('robbery_time', 'TEXT NOT NULL')
        ],
        'config': [
            ('value', 'TEXT')
        ],
        'game_history': [
            ('user_id', 'INTEGER NOT NULL'),
            ('game_type', 'TEXT NOT NULL'),
            ('amount', 'REAL NOT NULL'),
            ('description', 'TEXT'),
            ('timestamp', 'TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP')
        ]
    }

    for table_name, columns in table_columns.items():
        try:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if cursor.fetchone():
                for column_name, column_definition in columns:
                    add_column_if_not_exists(cursor, table_name, column_name, column_definition)
        except sqlite3.Error as e:
            log.error(f"Error checking/adding columns for table {table_name}: {e}")


def set_selected_daily_gift(gift_id: int):
    if gift_id is None:
        set_config_value('selected_daily_gift_id', '')
        log.info("Selected daily gift cleared.")
    else:
        set_config_value('selected_daily_gift_id', str(gift_id))
        log.info(f"Selected daily gift set to ID: {gift_id}")


def get_selected_daily_gift() -> int | None:
    default_gift_id = AVAILABLE_DAILY_GIFTS.get(DEFAULT_DAILY_GIFT_KEY)
    value = get_config_value('selected_daily_gift_id', default_value=str(default_gift_id) if default_gift_id else None)
    if not value:
        log.warning("No selected_daily_gift_id in config. Returning default.")
        return default_gift_id
    try:
        return int(value)
    except (ValueError, TypeError):
        log.warning(f"Invalid selected_daily_gift_id ('{value}') in config. Returning default.")
        return default_gift_id


def are_withdrawals_enabled() -> bool:
    value = get_config_value('withdrawals_enabled', default_value='1')
    return value == '1'


def set_withdrawals_enabled(enabled: bool):
    value = '1' if enabled else '0'
    set_config_value('withdrawals_enabled', value)
    log.info(f"Withdrawals status set to: {'ENABLED' if enabled else 'DISABLED'}")


def are_referrals_enabled() -> bool:
    value = get_config_value('referrals_enabled', default_value='1')
    return value == '1'


def set_referrals_enabled(enabled: bool):
    value = '1' if enabled else '0'
    set_config_value('referrals_enabled', value)
    log.info(f"Referral program status set to: {'ENABLED' if enabled else 'DISABLED'}")


def user_exists(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        result = cursor.execute('SELECT 1 FROM users WHERE id = ?', (user_id,)).fetchone()
        return bool(result)


def add_user(user_id, username, referral_id=None, lang='ru', special_ref=None):
    registration_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    username_to_db = username or f"id_{user_id}"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO users (id, username, stars, count_refs, referral_id, lang, click_count, gift_count, registration_time, special_ref, ref_rewarded, completed_onboarding, last_click_time, last_gift_time, last_free_spin_time)
                VALUES (?, ?, 0.0, 0, ?, ?, 0, 0, ?, ?, 0, 0, NULL, NULL, NULL)
            ''', (user_id, username_to_db, referral_id, lang, registration_time, special_ref))
            conn.commit()
            log.info(f"User {user_id} added successfully.")
            return True
        except sqlite3.IntegrityError:
            log.warning(f"User {user_id} already exists. Checking username...")
            cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
            existing_user = cursor.fetchone()
            if existing_user and existing_user['username'] != username_to_db:
                update_user_username(user_id, username_to_db)
            return False
        except sqlite3.Error as e:
            log.error(f"Error adding user {user_id}: {e}")
            return False


def get_user(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        return cursor.fetchone()


def get_users():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users')
        return [row['id'] for row in cursor.fetchall()]


def delete_user(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                log.warning(f"User {user_id} and related data deleted from database (CASCADE).")
            return deleted_count > 0
        except sqlite3.Error as e:
            log.error(f"Error deleting user {user_id}: {e}")
            conn.rollback()
            return False


def update_user_username(user_id, new_username):
    username_to_update = new_username or f"id_{user_id}"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET username = ? WHERE id = ?', (username_to_update, user_id))
        conn.commit()
        if cursor.rowcount > 0:
            log.info(f"Updated username for user {user_id} to '{username_to_update}'")


def update_user_lang(user_id, lang):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET lang = ? WHERE id = ?', (lang, user_id))
        conn.commit()


def get_user_lang(user_id):
    user = get_user(user_id)
    return user['lang'] if user else 'ru'


def get_user_registration_time(user_id):
    user = get_user(user_id)
    return user['registration_time'] if user else None


def get_user_counts():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        total_users = cursor.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
        day_ago_dt = datetime.now() - timedelta(days=1)
        day_ago = day_ago_dt.strftime('%Y-%m-%d %H:%M:%S')
        daily_users = cursor.execute("SELECT COUNT(*) FROM users WHERE registration_time >= ?", (day_ago,)).fetchone()[
            0]
        month_ago_dt = datetime.now() - timedelta(days=30)
        month_ago = month_ago_dt.strftime('%Y-%m-%d %H:%M:%S')
        monthly_users = \
            cursor.execute("SELECT COUNT(*) FROM users WHERE registration_time >= ?", (month_ago,)).fetchone()[0]
        return {"total": total_users, "daily": daily_users, "monthly": monthly_users}


def add_stars(user_id, amount):
    if not isinstance(amount, (int, float)) or amount <= 0:
        log.warning(f"Attempted to add invalid amount {amount} for user {user_id}")
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET stars = stars + ? WHERE id = ?', (amount, user_id))
        conn.commit()
        log.debug(f"Added {amount} stars to user {user_id}")


def subtract_stars(user_id, amount):
    if not isinstance(amount, (int, float)) or amount <= 0:
        log.warning(f"Attempted to subtract invalid amount {amount} for user {user_id}")
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET stars = MAX(0, stars - ?) WHERE id = ?', (amount, user_id))
        conn.commit()
        log.debug(f"Subtracted {amount} stars from user {user_id}")


def get_users_balance(user_id):
    user = get_user(user_id)
    return float(user['stars']) if user else 0.0


def reset_user_balances():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET stars = 0.0")
        conn.commit()
        count = cursor.rowcount
        log.warning(f"All user balances ({count}) have been reset to 0.")
        return count


def give_stars_to_all(amount):
    if not isinstance(amount, (int, float)) or amount <= 0:
        log.warning("Attempted to give non-positive stars amount to all users.")
        return 0
    log.info(f"Adding {amount} stars to all users...")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET stars = stars + ?", (amount,))
        conn.commit()
        count = cursor.rowcount
        log.info(f"Added {amount} stars to {count} users.")
        return count


def withdraw_stars(user_id, amount):
    if not isinstance(amount, (int, float)) or amount <= 0:
        return False
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        try:
            cursor.execute("SELECT stars FROM users WHERE id = ?", (user_id,))
            current_balance_row = cursor.fetchone()
            if not current_balance_row or current_balance_row['stars'] < amount:
                log.warning(
                    f"Withdrawal failed for user {user_id}: insufficient balance ({current_balance_row['stars'] if current_balance_row else 'N/A'}) for amount {amount}."
                )
                conn.rollback()
                return False
            cursor.execute('UPDATE users SET stars = stars - ?, withdrawn = withdrawn + ? WHERE id = ?',
                           (amount, amount, user_id))
            conn.commit()
            log.info(f"Withdrew {amount} stars from user {user_id}. Updated withdrawn counter.")
            return True
        except sqlite3.Error as e:
            log.error(f"Database error during withdraw_stars for user {user_id}: {e}")
            conn.rollback()
            return False


def increment_referrals(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET count_refs = count_refs + 1 WHERE id = ?', (user_id,))
        conn.commit()


def update_user_ref_rewarded(user_id, rewarded: bool):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET ref_rewarded = ? WHERE id = ?", (int(rewarded), user_id))
        conn.commit()


def get_referral_id(user_id):
    user = get_user(user_id)
    return user['referral_id'] if user else None


def get_referrals(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, stars, registration_time FROM users WHERE referral_id = ? ORDER BY registration_time DESC",
            (user_id,))
        return cursor.fetchall()


def get_referrals_count(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referral_id=?", (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0


def get_referrals_count_week(user_id):
    today_utc = datetime.utcnow().date()
    start_of_week_utc = today_utc - timedelta(days=today_utc.weekday())
    start_of_week_str = start_of_week_utc.strftime("%Y-%m-%d") + " 00:00:00"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referral_id = ? AND registration_time >= ?",
                       (user_id, start_of_week_str))
        count = cursor.fetchone()[0]
        log.debug(f"Weekly referrals for {user_id} (since {start_of_week_str} UTC): {count}")
        return count


def get_referral_top():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, count_refs FROM users WHERE count_refs > 0 ORDER BY count_refs DESC LIMIT 10"
        )
        return cursor.fetchall()


def get_referral_top_by_period(period):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now()
    if period == 'day':
        time_threshold = now - timedelta(days=1)
    elif period == 'week':
        time_threshold = now - timedelta(days=7)
    elif period == 'month':
        time_threshold = now - timedelta(days=30)
    else:
        conn.close()
        raise ValueError("Invalid period specified for referral top.")
    time_threshold_str = time_threshold.strftime('%Y-%m-%d %H:%M:%S')
    query = '''
        SELECT referral_id, COUNT(*) as ref_count FROM users
        WHERE referral_id IS NOT NULL AND registration_time >= ?
        GROUP BY referral_id HAVING ref_count > 0
        ORDER BY ref_count DESC LIMIT 10
    '''
    cursor.execute(query, (time_threshold_str,))
    result = cursor.fetchall()
    conn.close()
    return result


def add_promocode(promocode, reward, max_uses, min_referrals):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT OR REPLACE INTO promocodes (promocode, reward, max_uses, min_referrals)
               VALUES (?, ?, ?, ?)''',
            (promocode, reward, max_uses, min_referrals)
        )
        conn.commit()


def use_promocode(user_id, promocode):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION;")
            cursor.execute("SELECT 1 FROM used_promocodes WHERE user_id = ? AND promocode = ?", (user_id, promocode))
            if cursor.fetchone():
                conn.rollback()
                return False, "❌ Вы уже использовали этот промокод."
            cursor.execute("SELECT reward, max_uses, min_referrals FROM promocodes WHERE promocode = ?", (promocode,))
            promo_data = cursor.fetchone()
            if not promo_data:
                conn.rollback()
                return False, "❌ Промокод не найден."
            reward, max_uses, min_referrals = promo_data['reward'], promo_data['max_uses'], promo_data['min_referrals']
            if max_uses <= 0:
                conn.rollback()
                return False, "❌ Этот промокод уже исчерпал лимит использований."
            cursor.execute("SELECT COUNT(*) FROM users WHERE referral_id=?", (user_id,))
            user_referral_count = cursor.fetchone()[0]
            if user_referral_count < min_referrals:
                conn.rollback()
                return False, f"❌ Вам нужно хотя бы {min_referrals} рефералов для активации (у вас {user_referral_count})."
            cursor.execute("UPDATE promocodes SET max_uses = max_uses - 1 WHERE promocode = ?", (promocode,))
            used_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("INSERT INTO used_promocodes (user_id, promocode, used_at) VALUES (?, ?, ?)",
                           (user_id, promocode, used_at))
            cursor.execute("UPDATE users SET stars = stars + ? WHERE id = ?", (reward, user_id))
            conn.commit()
            log.info(f"User {user_id} activated promocode '{promocode}'. Awarded {reward} stars.")
            cursor.execute("SELECT max_uses FROM promocodes WHERE promocode = ?", (promocode,))
            updated_promo_data = cursor.fetchone()
            if updated_promo_data and updated_promo_data['max_uses'] <= 0:
                delete_promo(promocode)
            return True, f"✅ Промокод <code>{escape(promocode)}</code> активирован! Вы получили {reward:.2f}⭐️."
        except sqlite3.Error as e:
            log.error(f"Error activating promocode {promocode} for user {user_id}: {e}")
            conn.rollback()
            return False, "❌ Ошибка базы данных при активации промокода."
        except Exception as e:
            log.exception(f"Unexpected error activating promocode {promocode} for {user_id}: {e}")
            conn.rollback()
            return False, "❌ Непредвиденная ошибка при активации промокода."


def check_promocode_usage(user_id, promocode):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM used_promocodes WHERE user_id = ? AND promocode = ?", (user_id, promocode))
        return bool(cursor.fetchone())


def delete_promo(promocode):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM promocodes WHERE promocode = ?", (promocode,))
        deleted_main = cursor.rowcount
        conn.commit()
        if deleted_main > 0:
            log.info(f"Promocode '{promocode}' deleted from 'promocodes'. Usage history remains.")
        return deleted_main > 0


def get_user_withdrawals(user_id: int, limit: int = 5):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT amount, status, request_time
            FROM withdraw_requests
            WHERE user_id = ?
            ORDER BY request_time DESC
            LIMIT ?
        ''', (user_id, limit))
        withdrawals = cursor.fetchall()
        return [dict(row) for row in withdrawals]


def get_all_promocodes():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT promocode, reward, max_uses, min_referrals FROM promocodes ORDER BY promocode')
        return cursor.fetchall()


def get_promocode_reward(promocode):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT reward FROM promocodes WHERE promocode = ?", (promocode,))
        result = cursor.fetchone()
        return result['reward'] if result else None


def get_total_promocodes():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM promocodes")
        return cursor.fetchone()[0]


def get_active_promocodes():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM promocodes WHERE max_uses > 0")
        return cursor.fetchone()[0]


def add_task(channel_id_or_link, reward, max_completions, requires_subscription=True):
    if max_completions <= 0:
        raise ValueError("max_completions must be positive")
    task_type = "sub" if requires_subscription else "nosub"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO tasks (channel_id, reward, max_completions, active, requires_subscription, task_type, completed_count)
               VALUES (?, ?, ?, 1, ?, ?, 0)''',
            (str(channel_id_or_link), reward, max_completions, int(requires_subscription), task_type)
        )
        conn.commit()
        log.info(
            f"Task added: type={task_type}, target='{channel_id_or_link}', reward={reward}, limit={max_completions}")


def remove_task(channel_id_or_link):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tasks WHERE channel_id = ?', (str(channel_id_or_link),))
        deleted_count = cursor.rowcount
        conn.commit()
        if deleted_count > 0:
            log.info(
                f"Task(s) associated with '{channel_id_or_link}' deleted. Related completed_tasks also removed (CASCADE).")
        return deleted_count > 0


def get_tasks():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, channel_id, reward, completed_count, max_completions, requires_subscription, task_type
            FROM tasks WHERE active=1
        ''')
        return cursor.fetchall()


def mark_task_completed(user_id, task_id):
    completed_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN TRANSACTION;")
            cursor.execute('''
                INSERT OR IGNORE INTO completed_tasks (user_id, task_id, completed_at)
                VALUES (?, ?, ?)
            ''', (user_id, task_id, completed_at))
            if cursor.rowcount > 0:
                cursor.execute('UPDATE tasks SET completed_count = completed_count + 1 WHERE id = ?', (task_id,))
            conn.commit()
            log.debug(f"Marked task {task_id} completed for user {user_id}.")
        except sqlite3.Error as e:
            log.error(f"Error marking task {task_id} completed for user {user_id}: {e}")
            conn.rollback()


def user_completed_task(user_id, task_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM completed_tasks WHERE user_id=? AND task_id=?', (user_id, task_id))
        return bool(cursor.fetchone())


def get_total_tasks():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        return cursor.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]


def get_active_tasks():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        return cursor.execute("SELECT COUNT(*) FROM tasks WHERE active = 1").fetchone()[0]


def get_completed_tasks():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        return cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE completed_count >= max_completions AND active = 1"
        ).fetchone()[0]


def add_channel_db(channel_id: int, delete_timestamp: int | None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR REPLACE INTO channels (channel_id, delete_time) VALUES (?, ?)",
                           (channel_id, delete_timestamp))
            conn.commit()
            log.info(f"Channel {channel_id} added/updated. Deletion time: {delete_timestamp}")
        except sqlite3.Error as e:
            log.error(f"Error adding/updating channel {channel_id}: {e}")


def delete_channel_db(channel_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
        deleted_count = cursor.rowcount
        conn.commit()
        if deleted_count > 0:
            log.info(f"Channel {channel_id} deleted from OP list.")
        return deleted_count > 0


def get_channels_db(get_delete_time=False):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if get_delete_time:
            cursor.execute('SELECT channel_id, delete_time FROM channels ORDER BY id')
            return cursor.fetchall()
        else:
            cursor.execute('SELECT channel_id FROM channels ORDER BY id')
            return [row['channel_id'] for row in cursor.fetchall()]


def get_total_channels():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        return cursor.execute("SELECT COUNT(*) FROM channels").fetchone()[0]


def get_active_channels():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        current_ts = int(time.time())
        return cursor.execute(
            "SELECT COUNT(*) FROM channels WHERE delete_time IS NULL OR delete_time > ?",
            (current_ts,)
        ).fetchone()[0]


def set_lucky_time(start: datetime, duration_minutes=60):
    end = start + timedelta(minutes=duration_minutes)
    set_config_value('lucky_start', start.isoformat())
    set_config_value('lucky_end', end.isoformat())
    log.info(f"Lucky time set: {start.isoformat()} to {end.isoformat()}")


def is_lucky_time_now():
    start_str = get_config_value('lucky_start')
    end_str = get_config_value('lucky_end')
    if start_str and end_str:
        try:
            start_utc = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            end_utc = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            now_utc = datetime.utcnow()
            if start_utc.tzinfo is None:
                now_utc = now_utc.replace(tzinfo=None)
            return start_utc <= now_utc <= end_utc
        except ValueError as e:
            log.error(f"Could not parse lucky time from config: start='{start_str}', end='{end_str}'. Error: {e}")
            return False
    return False


def set_config_value(key, value):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', (key, str(value)))
        conn.commit()
        log.info(f"Config key '{key}' set to '{value}'")


def get_config_value(key, default_value=None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM config WHERE key=?', (key,))
        result = cursor.fetchone()
        value = result['value'] if result else default_value
        log.debug(f"Config key '{key}' requested. Value: '{value}' (Default: '{default_value}')")
        return value


def get_wheel_daily_limit():
    value = get_config_value('wheel_daily_limit', default_value=str(DEFAULT_WHEEL_DAILY_LIMIT))
    try:
        return int(value)
    except (ValueError, TypeError):
        log.warning(f"Invalid wheel_daily_limit in config ('{value}'). Using default {DEFAULT_WHEEL_DAILY_LIMIT}.")
        return DEFAULT_WHEEL_DAILY_LIMIT


def get_exchange_daily_limit():
    value = get_config_value('exchange_daily_limit', default_value=str(DEFAULT_EXCHANGE_DAILY_LIMIT))
    try:
        return int(value)
    except (ValueError, TypeError):
        log.warning(
            f"Invalid exchange_daily_limit in config ('{value}'). Using default {DEFAULT_EXCHANGE_DAILY_LIMIT}.")
        return DEFAULT_EXCHANGE_DAILY_LIMIT


def get_exchange_referral_req():
    value = get_config_value('exchange_referral_req', default_value=str(DEFAULT_EXCHANGE_REFERRAL_REQ))
    try:
        return int(value)
    except (ValueError, TypeError):
        log.warning(
            f"Invalid exchange_referral_req in config ('{value}'). Using default {DEFAULT_EXCHANGE_REFERRAL_REQ}.")
        return DEFAULT_EXCHANGE_REFERRAL_REQ


def get_wheel_referral_req():
    value = get_config_value('wheel_referral_req', default_value=str(DEFAULT_WHEEL_REFERRAL_REQ))
    try:
        return int(value)
    except (ValueError, TypeError):
        log.warning(f"Invalid wheel_referral_req in config ('{value}'). Using default {DEFAULT_WHEEL_REFERRAL_REQ}.")
        return DEFAULT_WHEEL_REFERRAL_REQ


def get_project_balance():
    val = get_config_value('project_balance')
    try:
        return float(val) if val is not None else 1000.0
    except (ValueError, TypeError):
        log.warning(f"Invalid project_balance value in config: '{val}'. Using default.")
        return 1000.0


def set_project_balance(value):
    try:
        set_config_value('project_balance', float(value))
    except (ValueError, TypeError):
        log.error(f"Invalid value provided for project balance: {value}")


def get_total_withdrawn():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        result = cursor.execute('SELECT SUM(withdrawn) FROM users').fetchone()
        return result[0] if result and result[0] is not None else 0.0


def get_total_combined():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        result = cursor.execute('SELECT SUM(stars), SUM(withdrawn) FROM users').fetchone()
        total_stars = result['SUM(stars)'] if result and result['SUM(stars)'] is not None else 0.0
        total_withdrawn = result['SUM(withdrawn)'] if result and result['SUM(withdrawn)'] is not None else 0.0
        return total_stars + total_withdrawn


def get_top_users():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, (stars + withdrawn) AS total_earned
            FROM users ORDER BY total_earned DESC LIMIT 10
        ''')
        return cursor.fetchall()


def get_click_top():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, click_count
            FROM users WHERE click_count > 0
            ORDER BY click_count DESC LIMIT 10
        ''')
        return cursor.fetchall()


def get_inactive_users(days):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        target_dt_utc = datetime.utcnow() - timedelta(days=days)
        target_date_iso = target_dt_utc.isoformat()
        cursor.execute("SELECT id FROM users WHERE last_click_time IS NULL OR last_click_time < ?", (target_date_iso,))
        return [row['id'] for row in cursor.fetchall()]


def is_user_blocked(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT is_blocked FROM block_status WHERE user_id = ?', (user_id,))
        block_status = cursor.fetchone()
        return bool(block_status and block_status['is_blocked'] == 1)


def block_user_in_db(user_id):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO block_status (user_id, is_blocked, blocked_at, unblocked_at)
                VALUES (?, 1, ?, (SELECT unblocked_at FROM block_status WHERE user_id = ?))
            ''', (user_id, now_str, user_id))
            conn.commit()
            log.info(f"User {user_id} blocked in DB.")
            return True
        except sqlite3.Error as e:
            log.error(f"Error blocking user {user_id}: {e}")
            conn.rollback()
            return False


def unblock_user_in_db(user_id):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            res = cursor.execute('''
                UPDATE block_status SET is_blocked = 0, unblocked_at = ?
                WHERE user_id = ? AND is_blocked = 1
            ''', (now_str, user_id))
            conn.commit()
            if res.rowcount > 0:
                log.info(f"User {user_id} unblocked in DB.")
            else:
                log.info(f"User {user_id} was not blocked or not found in block_status.")
            return True
        except sqlite3.Error as e:
            log.error(f"Error unblocking user {user_id}: {e}")
            conn.rollback()
            return False


async def get_last_robbery_time(user_id: int) -> datetime | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT robbery_time FROM robberies
            WHERE user_id = ? ORDER BY robbery_time DESC LIMIT 1
        ''', (user_id,))
        result = cursor.fetchone()
        if result and result['robbery_time']:
            try:
                return datetime.strptime(result['robbery_time'], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                log.error(f"Could not parse robbery_time '{result['robbery_time']}' for user {user_id}")
                return None
        return None


async def update_last_robbery_time(user_id: int, target_user_id: int):
    current_time_utc_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO robberies (user_id, target_user_id, robbery_time)
            VALUES (?, ?, ?)
        ''', (user_id, target_user_id, current_time_utc_str))
        conn.commit()


async def get_random_user():
    admin_ids_tuple = tuple(ADMIN_IDS)
    placeholders = ','.join('?' * len(admin_ids_tuple)) if admin_ids_tuple else 'NULL'
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = f'''
            SELECT id, stars FROM users
            WHERE stars > 0 AND id NOT IN ({placeholders})
            ORDER BY RANDOM() LIMIT 1
        '''
        try:
            cursor.execute(query, admin_ids_tuple)
            random_user_row = cursor.fetchone()
            return (random_user_row['id'], random_user_row['stars']) if random_user_row else None
        except sqlite3.OperationalError as e:
            if "near \"NULL\": syntax error" in str(e) and not admin_ids_tuple:
                cursor.execute("SELECT id, stars FROM users WHERE stars > 0 ORDER BY RANDOM() LIMIT 1")
                random_user_row = cursor.fetchone()
                return (random_user_row['id'], random_user_row['stars']) if random_user_row else None
            else:
                raise


async def update_user_balance(user_id, new_balance):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET stars = MAX(0, ?) WHERE id = ?", (new_balance, user_id))
        conn.commit()


def set_custom_reward_in_db(user_id, min_reward, max_reward):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO custom_rewards (user_id, min_reward, max_reward)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET min_reward=excluded.min_reward, max_reward=excluded.max_reward
        ''', (user_id, min_reward, max_reward))
        conn.commit()
        log.info(f"Custom click reward for user {user_id} set to {min_reward}:{max_reward}")


def get_custom_reward_from_db(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT min_reward, max_reward FROM custom_rewards WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result and result['min_reward'] is not None and result['max_reward'] is not None:
            return result['min_reward'], result['max_reward']
        else:
            return CLICK_MIN_REWARD, CLICK_MAX_REWARD


def set_ref_reward(user_id, min_f_reward, max_f_reward):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO custom_rewards (user_id, min_f_reward, max_f_reward)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET min_f_reward=excluded.min_f_reward, max_f_reward=excluded.max_f_reward
        ''', (user_id, min_f_reward, max_f_reward))
        conn.commit()
        log.info(f"Custom referral reward for user {user_id} set to {min_f_reward}:{max_f_reward}")


def get_referral_reward_range(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT min_f_reward, max_f_reward FROM custom_rewards WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        if result and result['min_f_reward'] is not None and result['max_f_reward'] is not None:
            return result['min_f_reward'], result['max_f_reward']
        else:
            return MIN_REF_REWARD, MAX_REF_REWARD


def get_unique_users_count():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(DISTINCT user_id)
            FROM custom_rewards
            WHERE min_reward IS NOT NULL OR max_reward IS NOT NULL
                  OR min_f_reward IS NOT NULL OR max_f_reward IS NOT NULL
        ''')
        result = cursor.fetchone()
        return result[0] if result else 0


def update_verified_signups(special_code):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE special_links SET verified_signups = verified_signups + 1 WHERE special_code = ?",
                       (special_code,))
        conn.commit()


async def mark_onboarding_completed(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        log.info(f"Marking onboarding completed for user {user_id}")
        cursor.execute("UPDATE users SET completed_onboarding = 1 WHERE id = ? AND completed_onboarding = 0",
                       (user_id,))
        updated_rows = cursor.rowcount
        if updated_rows > 0:
            cursor.execute("SELECT special_ref FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()
            if user and user['special_ref']:
                special_code = user['special_ref']
                log.info(f"User {user_id} completed onboarding via special ref: {special_code}")
                cursor.execute(
                    "UPDATE special_links SET completed_onboarding = completed_onboarding + 1 WHERE special_code = ?",
                    (special_code,))
        conn.commit()


def get_user_referrals(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, registration_time
            FROM users WHERE referral_id = ?
            ORDER BY registration_time DESC
        ''', (user_id,))
        all_referrals = cursor.fetchall()
        total_refs = len(all_referrals)
        weekly_refs = get_referrals_count_week(user_id)
        return all_referrals, total_refs, weekly_refs


def add_sponsor_button(name, url):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sponsor_buttons (name, url) VALUES (?, ?)", (name, url))
        conn.commit()


def remove_sponsor_button(name, url):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sponsor_buttons WHERE name = ? AND url = ?", (name, url))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count > 0


def get_sponsor_buttons():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, url FROM sponsor_buttons")
        return cursor.fetchall()


def record_spent_stars(amount):
    if not isinstance(amount, (int, float)) or amount <= 0:
        return
    today_str = datetime.now().strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO spent_stars (date, amount)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET amount = amount + excluded.amount;
        ''', (today_str, amount))
        conn.commit()


def get_spent_stars_for_day(date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(amount), 0.0) FROM spent_stars WHERE date = ?", (date_str,))
        return cursor.fetchone()[0]


def get_spent_stars_for_week():
    today = datetime.now()
    week_start_dt = today - timedelta(days=today.weekday())
    week_start_str = week_start_dt.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(amount), 0.0) FROM spent_stars WHERE date >= ? AND date <= ?",
                       (week_start_str, today_str))
        return cursor.fetchone()[0]


def get_spent_stars_for_month():
    today = datetime.now()
    first_day_of_month_dt = today.replace(day=1)
    first_day_str = first_day_of_month_dt.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(SUM(amount), 0.0) FROM spent_stars WHERE date >= ? AND date <= ?",
                       (first_day_str, today_str))
        return cursor.fetchone()[0]


def get_next_withdraw_request_id():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(id) FROM withdraw_requests")
        max_id = cursor.fetchone()[0]
        return (max_id or 0) + 1


def get_daily_withdrawal_count(user_id: int, withdrawal_type: str) -> int:
    today_str = date.today().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT count FROM daily_withdrawals WHERE user_id = ? AND withdrawal_date = ? AND withdrawal_type = ?",
            (user_id, today_str, withdrawal_type)
        )
        result = cursor.fetchone()
        count = result['count'] if result else 0
        log.debug(
            f"Daily withdrawal count check: user={user_id}, type={withdrawal_type}, date={today_str}. Count: {count}")
        return count


def increment_daily_withdrawal_count(user_id: int, withdrawal_type: str):
    today_str = date.today().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO daily_withdrawals (user_id, withdrawal_date, withdrawal_type, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, withdrawal_date, withdrawal_type) DO UPDATE SET count = count + 1;
            ''', (user_id, today_str, withdrawal_type))
            conn.commit()
            log.info(f"Incremented daily withdrawal count for user={user_id}, type={withdrawal_type}, date={today_str}")
            return True
        except sqlite3.Error as e:
            log.exception(f"Failed to increment daily withdrawal count for user {user_id}, type {withdrawal_type}: {e}")
            conn.rollback()
            return False


def get_last_click_time(user_id):
    user = get_user(user_id)
    return user['last_click_time'] if user else None


def update_last_click_time(user_id):
    now_utc_iso = datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET last_click_time = ? WHERE id = ?', (now_utc_iso, user_id))
        conn.commit()


def increment_click_count(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET click_count = click_count + 1 WHERE id = ?', (user_id,))
        conn.commit()


def get_last_gift(user_id):
    user = get_user(user_id)
    return user['last_gift_time'] if user else None


def update_last_gift(user_id):
    now_utc_iso = datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET last_gift_time = ? WHERE id = ?', (now_utc_iso, user_id))
        conn.commit()


def increment_gift_count(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET gift_count = gift_count + 1 WHERE id = ?', (user_id,))
        conn.commit()


def get_last_free_spin_time(user_id):
    user = get_user(user_id)
    return user['last_free_spin_time'] if user and 'last_free_spin_time' in user.keys() else None


def update_last_free_spin_time(user_id):
    now_utc_iso = datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET last_free_spin_time = ? WHERE id = ?', (now_utc_iso, user_id))
        conn.commit()
        log.info(f"Updated last free spin time for user {user_id} to {now_utc_iso}")


def create_wheel_win_request(cursor: sqlite3.Cursor, user_id: int, amount: float, emoji: str, gift_id: int | None,
                             prize_name: str) -> int | None:
    try:
        cursor.execute("SELECT MAX(id) FROM withdraw_requests")
        max_id_row = cursor.fetchone()
        max_id = max_id_row[0] if max_id_row else 0
        request_id = (max_id or 0) + 1
        admin_description = f"🎡 Выигрыш: {prize_name} {emoji}"
        cursor.execute('''
            INSERT INTO withdraw_requests (id, user_id, amount, status, gift_id, emoji, request_time)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (request_id, user_id, amount, 'pending', gift_id, admin_description))
        log.info(
            f"Wheel win withdrawal request {request_id} recorded for user {user_id}, prize={prize_name}, amount={amount}, gift_id={gift_id}.")
        return request_id
    except sqlite3.Error as e:
        log.exception(f"Failed to create wheel win request for user {user_id}, prize={prize_name}: {e}")
        return None


def get_user_username(user_id):
    user = get_user(user_id)
    return user['username'] if user else None


def add_game_history_record(user_id: int, game_type: str, amount: float, description: str | None = None, max_retries=3,
                            initial_delay=0.1):
    if not isinstance(amount, (int, float)):
        log.warning(f"Attempted to add invalid game history amount {amount} for user {user_id}, type {game_type}")
        return False

    retries = 0
    while retries <= max_retries:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # cursor.execute("BEGIN IMMEDIATE;") # Попробуем эксклюзивную блокировку на время записи
                cursor.execute('''
                    INSERT INTO game_history (user_id, game_type, amount, description, timestamp)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, game_type, amount, description))
                conn.commit()
                log.info(
                    f"Game history recorded: user={user_id}, type={game_type}, amount={amount:.2f}, desc={description}")
                return True
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and retries < max_retries:
                retries += 1
                delay = initial_delay * (2 ** (retries - 1)) + random.uniform(0, initial_delay * 0.5)
                log.warning(
                    f"Database locked on history write for user {user_id}. Retrying ({retries}/{max_retries}) after {delay:.2f}s...")
                time.sleep(delay)
            else:
                log.exception(
                    f"Failed to add game history record for user {user_id} after retries or due to other OperationalError: {e}")
                # conn.rollback() # with get_db_connection должен сделать rollback при выходе с ошибкой
                return False
        except sqlite3.Error as e:
            log.exception(f"Failed to add game history record (DB error) for user {user_id}: {e}")
            # conn.rollback() # with get_db_connection должен сделать rollback при выходе с ошибкой
            return False
        except Exception as e:
            log.exception(f"Unexpected error adding game history record for user {user_id}: {e}")
            return False
    log.error(f"Failed to add game history record for user {user_id} after all retries due to locking.")
    return False


def get_game_history(user_id: int, limit: int = 20):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT game_type, amount, description, timestamp
            FROM game_history
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        history = cursor.fetchall()
        return [dict(row) for row in history]


# --- Режим тех. работ ---

def is_maintenance_mode() -> bool:
    """Проверяет, включен ли режим тех. работ."""
    value = get_config_value('maintenance_mode', default_value='0')
    return value == '1'


def set_maintenance_mode(enabled: bool):
    """Включает/выключает режим тех. работ."""
    set_config_value('maintenance_mode', '1' if enabled else '0')


def get_maintenance_message() -> str:
    """Возвращает текст сообщения для режима тех. работ."""
    return get_config_value('maintenance_message', default_value='⚙️ Бот находится на тех. обслуживании. Пожалуйста, подождите.')


def set_maintenance_message(text: str):
    """Устанавливает текст сообщения для режима тех. работ."""
    set_config_value('maintenance_message', text)


def get_maintenance_end_text() -> str:
    """Возвращает текст рассылки после окончания тех. работ."""
    return get_config_value('maintenance_end_text', default_value='✅ Тех. работы завершены! Бот снова работает.')


def set_maintenance_end_text(text: str):
    """Устанавливает текст рассылки после окончания тех. работ."""
    set_config_value('maintenance_end_text', text)


def get_all_user_ids() -> list:
    """Возвращает список ID всех пользователей для рассылки."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users")
        return [row['id'] for row in cursor.fetchall()]
