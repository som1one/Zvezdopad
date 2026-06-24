#!/bin/bash
# Локальный запуск проекта (Linux/Mac)

echo "=== Запуск Backend ==="

# Backend
cd backend
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt

# Запуск в фоне
python -m uvicorn main:app --reload --port 8000 &
BACKEND_PID=$!

echo "Backend запущен на http://localhost:8000 (PID: $BACKEND_PID)"

cd ..

# Ждем немного
sleep 3

echo ""
echo "=== Запуск Frontend ==="

# Frontend
cd frontend
npm install
npm run dev &
FRONTEND_PID=$!

echo "Frontend запущен на http://localhost:3000 (PID: $FRONTEND_PID)"

cd ..

echo ""
echo "✅ Сервисы запущены!"
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo ""
echo "Для остановки: kill $BACKEND_PID $FRONTEND_PID"

