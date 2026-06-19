# Содержимое файла: cleardb_pg.py (Версия для PostgreSQL с asyncpg)
import asyncio
import asyncpg
import os
import logging

# Импортируем настройки БД из settings.py
from settings import PG_DBNAME, PG_USER, PG_PASSWORD, PG_HOST, PG_PORT

log = logging.getLogger('cleardb_pg')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


async def clear_database_pg():
    conn = None
    try:
        conn = await asyncpg.connect(
            database=PG_DBNAME,
            user=PG_USER,
            password=PG_PASSWORD,
            host=PG_HOST,
            port=PG_PORT
        )
        log.info(f"Подключено к PostgreSQL базе данных '{PG_DBNAME}' для очистки.")


        tables_to_truncate = [
            'game_history', 'daily_withdrawals', 'withdraw_requests',
            'used_promocodes', 'completed_tasks', 'block_status',
            'special_link_visits', 'robberies', 'custom_rewards',
            'special_links', 'sponsor_buttons', 'spent_stars',
            'channels', 'tasks', 'promocodes', 'users', 'config'  # users и config обычно в конце
        ]

        log.warning("!!! ВНИМАНИЕ: Сейчас будут удалены ВСЕ данные из следующих таблиц:")
        for table in tables_to_truncate:
            log.warning(f"- {table}")

        confirmation = input("Вы уверены, что хотите продолжить? (yes/no): ")
        if confirmation.lower() != 'yes':
            log.info("Очистка отменена пользователем.")
            return

        log.info("Начало очистки таблиц...")
        async with conn.transaction():
            # Отключаем триггеры (если есть, чтобы избежать проблем с FK при TRUNCATE без CASCADE)
            # await conn.execute("SET session_replication_role = 'replica';")

            for table in tables_to_truncate:
                try:
                    log.info(f"Очистка таблицы {table}...")
                    # RESTART IDENTITY сбрасывает счетчики SERIAL
                    # CASCADE удаляет строки в связанных таблицах (использовать осторожно!)
                    await conn.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;')
                    log.info(f"Таблица {table} успешно очищена.")
                except asyncpg.exceptions.UndefinedTableError:
                    log.warning(f"Таблица {table} не найдена, пропуск.")
                except Exception as e:
                    log.error(f"Ошибка при очистке таблицы {table}: {e}")
                    # При ошибке транзакция будет отменена
                    raise  # Прерываем выполнение при ошибке

            # Включаем триггеры обратно
            # await conn.execute("SET session_replication_role = 'origin';")

        log.info("Очистка таблиц успешно завершена.")

    except ConnectionRefusedError:
        log.error(
            f"Не удалось подключиться к PostgreSQL. Проверьте, запущен ли сервер и данные подключения в settings.py/env.")
    except asyncpg.InvalidPasswordError:
        log.error(f"Неверный пароль для пользователя PostgreSQL '{PG_USER}'.")
    except Exception as e:
        log.exception(f"Ошибка во время очистки базы данных PostgreSQL: {e}")
    finally:
        if conn:
            await conn.close()
            log.info("Соединение с PostgreSQL закрыто.")


async def main():
    await clear_database_pg()


if __name__ == "__main__":
    # Запуск асинхронной функции
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Процесс прерван пользователем.")
