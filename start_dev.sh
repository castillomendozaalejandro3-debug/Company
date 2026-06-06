#!/bin/bash
# Script para iniciar todos los servicios de Helios en modo desarrollo

set -e

echo "🚀 Iniciando Helios AI Development Environment..."
echo ""

# Función para limpiar al salir
cleanup() {
    echo ""
    echo "🛑 Deteniendo servicios..."
    kill 0 2>/dev/null || true
    exit 0
}

trap cleanup EXIT INT TERM

# Iniciar servicios en segundo plano
echo "1️⃣  Iniciando Rust Core (puerto 50051)..."
cd core && cargo run &
sleep 2

echo "2️⃣  Iniciando FastAPI Engine (puerto 8000)..."
cd .. && uvicorn ai_engine.main:app --reload --host 0.0.0.0 --port 8000 &
sleep 2

echo "3️⃣  Iniciando Next.js Dashboard (puerto 3000)..."
cd dashboard_ui && npm run dev &

echo ""
echo "✅ Todos los servicios están iniciando..."
echo ""
echo "📊 Accede a:"
echo "   - Dashboard: http://localhost:3000"
echo "   - API Docs:  http://localhost:8000/docs"
echo "   - Rust Core: localhost:50051"
echo ""
echo "Presiona Ctrl+C para detener todos los servicios"
echo ""

# Mantener el script ejecutándose
wait
