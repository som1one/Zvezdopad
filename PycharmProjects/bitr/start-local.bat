@echo off
echo ========================================
echo    ЗАПУСК ПРОЕКТА ЛОКАЛЬНО
echo ========================================
echo.

echo [1/2] Запуск Backend...
start "Backend - http://localhost:8000" cmd /k "cd backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && python -m uvicorn main:app --reload --port 8000"

timeout /t 5 /nobreak >nul

echo [2/2] Запуск Frontend...
start "Frontend - http://localhost:3000" cmd /k "cd frontend && npm install && npm run dev"

echo.
echo ========================================
echo    СЕРВИСЫ ЗАПУЩЕНЫ!
echo ========================================
echo.
echo Frontend:  http://localhost:3000
echo Backend:   http://localhost:8000
echo API:       http://localhost:8000/api
echo.
echo Два новых окна были открыты
echo Закройте их для остановки сервисов
echo.
pause




















