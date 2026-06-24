# Локальный запуск проекта (Windows PowerShell)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   ЗАПУСК ПРОЕКТА ЛОКАЛЬНО" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверка .env файла
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  ВНИМАНИЕ: .env файл не найден!" -ForegroundColor Yellow
    Write-Host "   Создайте .env файл в корне проекта" -ForegroundColor Yellow
    Write-Host "   Смотрите: ENV_SETUP_GUIDE.md" -ForegroundColor Yellow
    Write-Host ""
}

# 1. Backend
Write-Host "[1/2] Запуск Backend..." -ForegroundColor Green

$backendScript = @"
cd '$PWD\backend'
if (-not (Test-Path .venv)) {
    Write-Host 'Создание виртуального окружения...' -ForegroundColor Yellow
    python -m venv .venv
}
.venv\Scripts\activate
Write-Host 'Установка зависимостей...' -ForegroundColor Yellow
pip install -q -r requirements.txt
Write-Host ''
Write-Host '✅ Backend запускается на http://localhost:8000' -ForegroundColor Green
Write-Host '   API доступен: http://localhost:8000/api' -ForegroundColor Cyan
Write-Host ''
python -m uvicorn main:app --reload --port 8000
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendScript

Write-Host "   Backend запускается в новом окне..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# 2. Frontend
Write-Host "[2/2] Запуск Frontend..." -ForegroundColor Green

$frontendScript = @"
cd '$PWD\frontend'
Write-Host 'Установка зависимостей...' -ForegroundColor Yellow
npm install
Write-Host ''
Write-Host '✅ Frontend запускается на http://localhost:3000' -ForegroundColor Green
Write-Host ''
npm run dev
"@

Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendScript

Write-Host "   Frontend запускается в новом окне..." -ForegroundColor Yellow

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   ✅ СЕРВИСЫ ЗАПУЩЕНЫ!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📍 Адреса:" -ForegroundColor Yellow
Write-Host "   Frontend:  http://localhost:3000" -ForegroundColor White
Write-Host "   Backend:   http://localhost:8000" -ForegroundColor White
Write-Host "   API:       http://localhost:8000/api" -ForegroundColor White
Write-Host ""
Write-Host "💡 Два новых окна PowerShell были открыты" -ForegroundColor Cyan
Write-Host "   Закройте их для остановки сервисов" -ForegroundColor Cyan
Write-Host ""
Write-Host "⏳ Подождите 10-15 секунд для полного запуска..." -ForegroundColor Yellow
Write-Host ""