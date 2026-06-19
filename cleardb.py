import sqlite3

def clear_database():
    # Подключение к базе данных
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Отключаем ограничения внешних ключей, чтобы избежать ошибок при удалении
    cursor.execute('PRAGMA foreign_keys = OFF;')

    # Очистка данных из таблиц
    cursor.execute('DELETE FROM users;')
    cursor.execute('DELETE FROM custom_rewards;')
    cursor.execute('DELETE FROM tasks;')
    cursor.execute('DELETE FROM used_promocodes;')
    cursor.execute('DELETE FROM promocodes;')
    cursor.execute('DELETE FROM completed_tasks;')
    cursor.execute('DELETE FROM channels;')
    cursor.execute('DELETE FROM block_status;')
    cursor.execute('DELETE FROM config;')

    # Сброс автоинкрементных счетчиков для всех таблиц
    cursor.execute('DELETE FROM sqlite_sequence;')

    # Включаем ограничения внешних ключей обратно
    cursor.execute('PRAGMA foreign_keys = ON;')

    # Сохраняем изменения и закрываем соединение
    conn.commit()
    conn.close()

    print("База данных очищена!")

# Вызов функции для очистки базы данных
clear_database()
