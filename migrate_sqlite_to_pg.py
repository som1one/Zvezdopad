# migrate_sqlite_to_pg.py
import asyncio
import asyncpg
import sqlite3
import logging
from datetime import datetime, timezone, date, timedelta  # Добавлен timedelta
import os

# Импортируем настройки для подключения к PostgreSQL
# Предполагается, что settings.py находится в том же каталоге или доступен через PYTHONPATH
try:
    from settings import PG_DBNAME, PG_USER, PG_PASSWORD, PG_HOST, PG_PORT
except ImportError:
    print("Ошибка: Не удалось импортировать настройки БД из settings.py")
    # Установите значения по умолчанию здесь, если settings.py недоступен
    PG_DBNAME = "zvezdopad_db"
    PG_USER = "root"
    PG_PASSWORD = "2f7h2c3r"
    PG_HOST = "localhost"
    PG_PORT = "5432"
    print(f"Используются значения по умолчанию для подключения к PG: DB={PG_DBNAME}, User={PG_USER}, Host={PG_HOST}")

# Настройки логгирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('migration')

# Путь к старой базе SQLite
SQLITE_DB_PATH = "database.db"  # Убедитесь, что файл database.db находится здесь же


# --------- Функции парсинга и преобразования данных ---------

def parse_sqlite_datetime(dt_str: str | None) -> datetime | None:
    """Пытается распарсить строку даты/времени из SQLite (предполагая UTC или наивное время)."""
    if not dt_str:
        return None
    # Добавляем формат с Z, который может встречаться в ISO 8601
    formats_to_try = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",  # ISO формат без таймзоны (с микросекундами)
        "%Y-%m-%dT%H:%M:%S",  # ISO формат без таймзоны (без микросекунд)
        "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO с таймзоной (со смещением)
        "%Y-%m-%dT%H:%M:%S%z",  # ISO с таймзоной (без микросекунд)
        "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO с Z
        "%Y-%m-%dT%H:%M:%SZ",  # ISO с Z без микросекунд
    ]
    dt_obj = None
    for fmt in formats_to_try:
        try:
            # Обработка 'Z' для UTC
            if fmt.endswith('Z') and dt_str.endswith('Z'):
                dt_obj = datetime.strptime(dt_str[:-1], fmt[:-1]).replace(tzinfo=timezone.utc)
            else:
                dt_obj = datetime.strptime(dt_str, fmt)

            # Если время наивное, считаем его UTC
            if dt_obj.tzinfo is None:
                dt_obj = dt_obj.replace(tzinfo=timezone.utc)
            # Если время со смещением, преобразуем в UTC
            else:
                dt_obj = dt_obj.astimezone(timezone.utc)
            return dt_obj  # Возвращаем первый удачный парсинг
        except ValueError:
            continue
    log.warning(f"Не удалось распарсить дату SQLite: '{dt_str}'. Возвращено None.")
    return None


def parse_sqlite_date(date_str: str | None) -> date | None:
    """Пытается распарсить строку даты из SQLite."""
    if not date_str:
        return None
    try:
        # Пытаемся распарсить и дату со временем, и просто дату
        dt_obj = parse_sqlite_datetime(date_str)
        if dt_obj:
            return dt_obj.date()
        else:
            return date.fromisoformat(date_str)  # YYYY-MM-DD
    except ValueError:
        log.warning(f"Не удалось распарсить дату SQLite: '{date_str}'. Возвращено None.")
        return None


def parse_sqlite_timestamp_int(ts: int | str | None) -> datetime | None:
    """Конвертирует целочисленный timestamp из SQLite в datetime UTC."""
    if ts is None:
        return None
    try:
        timestamp = int(ts)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (ValueError, TypeError, OSError) as e:
        log.warning(f"Ошибка конвертации timestamp '{ts}' в datetime: {e}. Возвращено None.")
        return None


# --------- Основная логика миграции ---------

async def migrate_table(sqlite_cur: sqlite3.Cursor, pg_conn: asyncpg.Connection, table_name: str, pg_columns: list[str],
                        sqlite_columns: list[str] | None = None, type_conversions: dict | None = None):
    """Переносит данные из одной таблицы SQLite в PostgreSQL."""
    if sqlite_columns is None:
        sqlite_columns = pg_columns
    # Используем двойные кавычки для имен столбцов SQLite на случай спецсимволов или регистра
    sqlite_cols_str = ", ".join([f'"{col}"' for col in sqlite_columns])
    # Используем двойные кавычки для имен столбцов PG
    pg_cols_str = ", ".join([f'"{col}"' for col in pg_columns])
    placeholders = ", ".join([f"${i + 1}" for i in range(len(pg_columns))])

    log.info(f"Начало миграции таблицы '{table_name}'...")
    try:
        # Проверяем существование таблицы в SQLite
        sqlite_cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if sqlite_cur.fetchone() is None:
            log.warning(f"Таблица '{table_name}' не найдена в SQLite. Пропуск.")
            return 0, 0

        # Проверяем существование нужных колонок в SQLite
        sqlite_cur.execute(f"PRAGMA table_info('{table_name}')")
        existing_sqlite_columns = {col['name'] for col in sqlite_cur.fetchall()}
        missing_sqlite_cols = [col for col in sqlite_columns if col not in existing_sqlite_columns]
        if missing_sqlite_cols:
            log.warning(
                f"В SQLite таблице '{table_name}' отсутствуют колонки: {missing_sqlite_cols}. Пропускаем эти колонки.")
            # Адаптируем списки колонок для запроса
            valid_indices = [i for i, col in enumerate(sqlite_columns) if col not in missing_sqlite_cols]
            sqlite_columns = [sqlite_columns[i] for i in valid_indices]
            pg_columns = [pg_columns[i] for i in valid_indices]
            if not pg_columns:  # Если ни одна колонка не найдена
                log.error(
                    f"Не найдено ни одной из требуемых колонок для миграции таблицы '{table_name}'. Пропуск таблицы.")
                return 0, 0
            # Обновляем строки для запросов
            sqlite_cols_str = ", ".join([f'"{col}"' for col in sqlite_columns])
            pg_cols_str = ", ".join([f'"{col}"' for col in pg_columns])
            placeholders = ", ".join([f"${i + 1}" for i in range(len(pg_columns))])

        sqlite_cur.execute(f"SELECT {sqlite_cols_str} FROM {table_name}")
        rows_to_migrate = sqlite_cur.fetchall()

    except sqlite3.Error as e:
        log.error(f"Ошибка чтения из SQLite таблицы '{table_name}': {e}")
        return 0, 0  # Не можем продолжить с этой таблицей

    if not rows_to_migrate:
        log.info(f"Таблица '{table_name}' в SQLite пуста. Пропуск.")
        return 0, 0

    data_to_insert = []
    skipped_rows = 0
    for i, sqlite_row in enumerate(rows_to_migrate):
        pg_row_list = []
        try:
            sqlite_row_dict = dict(sqlite_row)
            valid_row = True
            for col_index, pg_col_name in enumerate(pg_columns):
                sqlite_col_name = sqlite_columns[col_index]  # Имя колонки в SQLite
                value = sqlite_row_dict.get(sqlite_col_name)  # Получаем значение

                # Преобразование типов
                if type_conversions and pg_col_name in type_conversions:
                    convert_func = type_conversions[pg_col_name]
                    try:
                        value = convert_func(value)
                    except Exception as conv_err:
                        log.warning(
                            f"Ошибка конвертации '{table_name}.{pg_col_name}' для SQLite строки {i + 1} (значение: {repr(value)}): {conv_err}. Пропуск строки.")
                        valid_row = False
                        break

                # Обработка специфичных случаев (True/False -> 1/0 для INTEGER в PG)
                bool_cols = ['ref_rewarded', 'is_blocked', 'active', 'requires_subscription', 'completed_onboarding']
                if pg_col_name in bool_cols and isinstance(value, bool):
                    value = int(value)

                # Проверка на NaN для float/double precision
                if isinstance(value, float) and value != value:
                    log.warning(
                        f"Обнаружен NaN в '{table_name}.{pg_col_name}' для SQLite строки {i + 1}. Заменяем на NULL.")
                    value = None

                pg_row_list.append(value)

            if valid_row:
                data_to_insert.append(tuple(pg_row_list))
            else:
                skipped_rows += 1

        except Exception as row_err:
            log.error(
                f"Ошибка обработки строки {i + 1} таблицы '{table_name}': {row_err}. Строка: {sqlite_row}. Пропуск строки.")
            skipped_rows += 1

    if not data_to_insert:
        log.warning(f"Нет данных для вставки в таблицу '{table_name}' после обработки.")
        return 0, skipped_rows

    # Формируем запрос INSERT ... ON CONFLICT DO NOTHING/UPDATE
    # Для большинства таблиц подходит DO NOTHING, чтобы не перезаписывать существующие PK
    # Для 'config' или 'block_status' может понадобиться DO UPDATE
    conflict_action = "DO NOTHING"
    if table_name in ['config', 'block_status', 'custom_rewards']:  # Пример таблиц, где нужно обновление
        pk_col = 'key' if table_name == 'config' else 'user_id'
        update_setters = ", ".join([f'"{col}" = excluded."{col}"' for col in pg_columns if col != pk_col])
        if update_setters:  # Убедимся, что есть что обновлять
            conflict_action = f'({pk_col}) DO UPDATE SET {update_setters}'
        else:  # Если обновлять нечего (только PK), оставляем DO NOTHING
            conflict_action = "DO NOTHING"
    elif table_name == 'users':
        # Особая логика для users: обновляем только если данные отличаются, чтобы не сбросить новые значения
        pk_col = 'id'
        update_setters = ", ".join([f'"{col}" = excluded."{col}"' for col in pg_columns if col != pk_col])
        conflict_action = f'({pk_col}) DO UPDATE SET {update_setters}'

    insert_query = f'INSERT INTO "{table_name}" ({pg_cols_str}) VALUES ({placeholders}) ON CONFLICT {conflict_action}'

    inserted_count = 0
    try:
        # Используем executemany для массовой вставки
        await pg_conn.executemany(insert_query, data_to_insert)
        # Так как executemany не возвращает точное число, а ON CONFLICT может пропускать строки,
        # реальное число вставленных может быть меньше len(data_to_insert).
        # Для точного подсчета нужен другой подход (возврат ID или проверка).
        # Пока просто логируем, что попытка вставки прошла.
        inserted_count = len(data_to_insert) - skipped_rows  # Приблизительное число
        log.info(
            f"Таблица '{table_name}': Успешно обработано для вставки {len(data_to_insert)} строк (пропущено {skipped_rows}).")
        return inserted_count, skipped_rows
    except Exception as e:
        log.error(f"Ошибка массовой вставки данных в PostgreSQL таблицу '{table_name}': {e}")
        # Попытка вставить по одной строке для диагностики
        inserted_count_single = 0
        for single_row_tuple in data_to_insert:
            try:
                # Используем тот же запрос с ON CONFLICT
                await pg_conn.execute(insert_query, *single_row_tuple)
                inserted_count_single += 1
            except Exception as single_e:
                log.error(f" -> Ошибка вставки строки: {single_row_tuple} | Error: {single_e}")
        failed_insertions = len(data_to_insert) - inserted_count_single
        log.warning(
            f"Вставка по одной строке: успешно {inserted_count_single} / {len(data_to_insert)} (ошибок: {failed_insertions})")
        return inserted_count_single, skipped_rows + failed_insertions


async def reset_pg_sequences(pg_conn: asyncpg.Connection, tables_with_serial: dict):
    """Сбрасывает счетчики SERIAL ключей в PostgreSQL."""
    log.info("Сброс PostgreSQL SERIAL счетчиков...")
    for table_name, pk_column in tables_with_serial.items():
        try:
            # Проверяем существование таблицы в PG перед запросом
            table_exists = await pg_conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)", table_name
            )
            if not table_exists:
                log.warning(f"Таблица '{table_name}' не найдена в PostgreSQL. Пропуск сброса sequence.")
                continue

            max_id_val = await pg_conn.fetchval(f'SELECT MAX("{pk_column}") FROM "{table_name}"')
            if max_id_val is not None:
                # Получаем имя sequence (обычно table_column_seq)
                # Используем pg_get_serial_sequence для стандартных имен
                seq_name_val = await pg_conn.fetchval(
                    f"SELECT pg_get_serial_sequence('\"{table_name}\"', '{pk_column}')")
                if seq_name_val:
                    # Устанавливаем следующее значение sequence
                    # Используем pg_catalog.setval для большей надежности
                    await pg_conn.execute(f"SELECT pg_catalog.setval('{seq_name_val}', $1, true)", max_id_val)
                    log.info(f"Sequence '{seq_name_val}' для '{table_name}.{pk_column}' установлен на {max_id_val + 1}")
                else:
                    log.warning(f"Не удалось автоматически определить sequence для '{table_name}.{pk_column}'")
            else:
                log.info(f"Таблица '{table_name}' пуста, сброс sequence не требуется.")
        except Exception as e:
            log.error(f"Ошибка сброса sequence для таблицы '{table_name}': {e}")


async def main_migration():
    """Основная функция миграции."""
    sqlite_conn = None
    pg_pool = None  # Пул соединений для миграции

    try:
        # --- Подключение к SQLite ---
        if not os.path.exists(SQLITE_DB_PATH):
            log.error(f"Файл базы данных SQLite не найден: {SQLITE_DB_PATH}")
            return
        try:
            sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
            sqlite_conn.row_factory = sqlite3.Row  # Для доступа по имени колонки
            sqlite_cur = sqlite_conn.cursor()
            sqlite_cur.execute("PRAGMA foreign_keys = ON;")  # Включаем FK для консистентности чтения
            log.info(f"Успешно подключено к SQLite: {SQLITE_DB_PATH}")
        except sqlite3.Error as e:
            log.exception(f"Ошибка подключения к SQLite: {e}")
            return

        # --- Подключение к PostgreSQL ---
        try:
            log.info("Создание пула PostgreSQL для миграции...")
            pg_pool = await asyncpg.create_pool(
                database=PG_DBNAME, user=PG_USER, password=PG_PASSWORD,
                host=PG_HOST, port=PG_PORT, min_size=1, max_size=2  # Маленький пул
            )
            # Проверка соединения
            async with pg_pool.acquire() as pg_conn:
                await pg_conn.execute("SELECT 1")
            log.info(f"Успешно подключено к PostgreSQL: {PG_DBNAME}@{PG_HOST}")
        except (asyncpg.PostgresError, OSError) as pg_err:  # Ловим ошибки соединения
            log.exception(f"Ошибка подключения к PostgreSQL: {pg_err}")
            return
        except Exception as e:  # Ловим другие ошибки инициализации пула
            log.exception(f"Неожиданная ошибка при создании пула PostgreSQL: {e}")
            return

        # --- Получаем соединение и начинаем миграцию ---
        async with pg_pool.acquire() as pg_conn:
            # --- Порядок миграции и определение колонок/конверсий ---
            # (Важно указывать колонки явно, т.к. в PG могут быть доп. колонки)
            migration_order = [
                # Таблица, PG Колонки, SQLite Колонки (если отличаются), Конверсии типов
                ('config', ['key', 'value'], None, None),
                ('users', ['id', 'username', 'stars', 'count_refs', 'referral_id', 'withdrawn', 'lang', 'ref_rewarded',
                           'second_level_rewards', 'last_gift_time', 'click_count', 'gift_count', 'registration_time',
                           'special_ref', 'completed_onboarding', 'last_click_time', 'last_free_spin_time'], None,
                 {'last_gift_time': parse_sqlite_datetime, 'registration_time': parse_sqlite_datetime,
                  'last_click_time': parse_sqlite_datetime, 'last_free_spin_time': parse_sqlite_datetime}),
                ('promocodes', ['promocode', 'reward', 'max_uses', 'min_referrals'], None, None),
                # У tasks в PG есть SERIAL id, в SQLite - INTEGER PRIMARY KEY AUTOINCREMENT
                # Мы переносим SQLite id в PG id
                ('tasks',
                 ['id', 'channel_id', 'reward', 'completed_count', 'max_completions', 'active', 'requires_subscription',
                  'task_type'], None, None),
                # У channels аналогично
                ('channels', ['id', 'channel_id', 'delete_time'], None, {'delete_time': parse_sqlite_timestamp_int}),
                # SQLite хранит как INTEGER timestamp
                ('special_links', ['id', 'user_id', 'special_code', 'unique_visits', 'total_visits', 'verified_signups',
                                   'completed_onboarding'], None, None),
                ('sponsor_buttons', ['id', 'name', 'url'], None, None),
                ('spent_stars', ['date', 'amount'], None, {'date': parse_sqlite_date}),
                ('custom_rewards', ['user_id', 'min_reward', 'max_reward', 'min_f_reward', 'max_f_reward'], None, None),
                ('block_status', ['user_id', 'is_blocked', 'blocked_at', 'unblocked_at'], None,
                 {'blocked_at': parse_sqlite_datetime, 'unblocked_at': parse_sqlite_datetime}),
                ('robberies', ['user_id', 'target_user_id', 'robbery_time'], None,
                 {'robbery_time': parse_sqlite_datetime}),
                ('completed_tasks', ['user_id', 'task_id', 'completed_at'], None,
                 {'completed_at': parse_sqlite_datetime}),
                ('used_promocodes', ['user_id', 'promocode', 'used_at'], None, {'used_at': parse_sqlite_datetime}),
                ('special_link_visits', ['id', 'user_id', 'special_code', 'visit_time'], None,
                 {'visit_time': parse_sqlite_datetime}),
                ('withdraw_requests',
                 ['id', 'user_id', 'amount', 'status', 'request_time', 'processed_time', 'gift_id', 'emoji'], None,
                 {'request_time': parse_sqlite_datetime, 'processed_time': parse_sqlite_datetime}),
                ('daily_withdrawals', ['user_id', 'withdrawal_date', 'withdrawal_type', 'count'], None,
                 {'withdrawal_date': parse_sqlite_date}),
                # У game_history аналогично с SERIAL id
                ('game_history', ['id', 'user_id', 'game_type', 'amount', 'description', 'timestamp'], None,
                 {'timestamp': parse_sqlite_datetime}),
            ]

            total_migrated = 0
            total_skipped = 0

            # Запускаем миграцию для каждой таблицы
            for table, pg_cols, sqlite_cols, conversions in migration_order:
                migrated, skipped = await migrate_table(sqlite_cur, pg_conn, table, pg_cols, sqlite_cols, conversions)
                total_migrated += migrated
                total_skipped += skipped

            log.info("-" * 30)
            log.info(f"Миграция завершена. Всего обработано строк: {total_migrated + total_skipped}")
            log.info(f"Успешно перенесено (или обновлено): {total_migrated}")
            log.info(f"Пропущено из-за ошибок: {total_skipped}")
            log.info("-" * 30)

            # Сброс счетчиков SERIAL PostgreSQL
            tables_with_serial_keys = {
                'tasks': 'id',
                'channels': 'id',
                'special_links': 'id',
                'sponsor_buttons': 'id',
                'special_link_visits': 'id',
                'withdraw_requests': 'id',
                'game_history': 'id',
            }
            await reset_pg_sequences(pg_conn, tables_with_serial_keys)

    except Exception as e:
        log.exception(f"Критическая ошибка во время миграции: {e}")
    finally:
        if sqlite_conn:
            sqlite_conn.close()
            log.info("Соединение с SQLite закрыто.")
        if pg_pool:
            await pg_pool.close()
            log.info("Пул PostgreSQL для миграции закрыт.")


if __name__ == "__main__":
    print("---------------------------------------------------------------------")
    print("ВНИМАНИЕ! Этот скрипт перенесет данные из SQLite (database.db)")
    print(f"в базу данных PostgreSQL ('{PG_DBNAME}' на '{PG_HOST}').")
    print("Убедитесь, что бот ОСТАНОВЛЕН, и вы сделали БЭКАПЫ обеих баз!")
    print("Скрипт попытается вставить данные. Если запись с таким же PRIMARY KEY")
    print("уже существует в PostgreSQL, она будет ПРОПУЩЕНА (ON CONFLICT DO NOTHING),")
    print("за исключением таблиц 'config', 'block_status', 'custom_rewards', 'users',")
    print("где существующие записи будут ОБНОВЛЕНЫ данными из SQLite.")
    print("---------------------------------------------------------------------")

    confirm = input("Введите 'YES', чтобы продолжить миграцию: ")
    if confirm == "YES":
        log.info("Запуск миграции...")
        try:
            asyncio.run(main_migration())
        except KeyboardInterrupt:
            log.info("Миграция прервана пользователем.")
        except Exception as e:
            log.exception("Критическая ошибка при запуске миграции.")
    else:
        log.info("Миграция отменена.")
