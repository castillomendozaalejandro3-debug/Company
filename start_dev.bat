@echo off
REM Script para iniciar todos los servicios de Helios en modo desarrollo (Windows)

echo 🚀 Iniciando Helios AI Development Environment...
echo.

REM Iniciar Rust Core
echo 1️⃣  Iniciando Rust Core (puerto 50051)...
start "Helios Core" cmd /k "cd core && cargo run"
timeout /t 3 /nobreak >nul

REM Iniciar FastAPI
echo 2️⃣  Iniciando FastAPI Engine (puerto 8000)...
start "Helios Engine" cmd /k "uvicorn ai_engine.main:app --reload --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul

REM Iniciar Next.js
echo 3️⃣  Iniciando Next.js Dashboard (puerto 3000)...
start "Helios Dashboard" cmd /k "cd dashboard_ui && npm run dev"

echo.
echo ✅ Todos los servicios están iniciando...
echo.
echo 📊 Accede a:
echo    - Dashboard: http://localhost:3000
echo    - API Docs:  http://localhost:8000/docs
echo    - Rust Core: localhost:50051
echo.
echo Cierra las ventanas para detener los servicios
pause
