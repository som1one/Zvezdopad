# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл зависимостей и устанавливаем их
COPY requirements.txt .
# Обновляем pip и устанавливаем зависимости (включая build-essential для некоторых пакетов)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем остальной код проекта в рабочую директорию
COPY . .

# Копируем сессию Pyrogram, ЕСЛИ она уже создана локально
# Если файла нет, Pyrogram запросит вход при первом запуске в контейнере
COPY ClientStars.session* .

# Указываем порт, который слушает ваше приложение aiohttp
EXPOSE 8080

# Команда для запуска вашего приложения при старте контейнера
CMD ["python", "main.py"]