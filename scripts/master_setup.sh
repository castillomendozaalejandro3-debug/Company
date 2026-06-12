#!/bin/bash
# =============================================================================
# Master Setup Script para Helios AI (Linux/Mac)
# Configura entorno, dependencias, compilación Rust y base de datos
# =============================================================================

set -e

echo ""
echo "========================================"
echo "  HELIOS AI - Master Setup Script"
echo "========================================"
echo ""

# Verificar Python
echo "[1/6] Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 no encontrado. Instale Python 3.9+"
    exit 1
fi
python3 --version
echo "Python instalado correctamente."

# Crear entorno virtual
echo ""
echo "[2/6] Creando entorno virtual..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Entorno virtual creado."
else
    echo "Entorno virtual ya existe."
fi

# Activar entorno virtual
source venv/bin/activate

# Instalar dependencias Python
echo ""
echo "[3/6] Instalando dependencias Python..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt || echo "WARNING: Algunas dependencias fallaron"
fi
if [ -f "ai_engine/requirements.txt" ]; then
    pip install -r ai_engine/requirements.txt
fi

# Verificar e instalar Rust
echo ""
echo "[4/6] Verificando Rust/Cargo..."
if ! command -v cargo &> /dev/null; then
    echo "Rust no encontrado. Intentando instalar..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env" 2>/dev/null || true
else
    echo "Rust instalado correctamente."
fi

# Compilar núcleo Rust
echo ""
echo "[5/6] Compilando núcleo Rust..."
if [ -f "core/Cargo.toml" ]; then
    cd core
    cargo build --release || echo "WARNING: Compilación Rust falló o tiene advertencias"
    cd ..
    echo "Compilación Rust completada."
else
    echo "Cargo.toml no encontrado. Saltando compilación Rust."
fi

# Generar stubs gRPC
echo ""
echo "[6/6] Generando stubs gRPC..."
if python3 -m grpc_tools.protoc --version &> /dev/null; then
    if [ -f "core/proto/helios.proto" ]; then
        mkdir -p ai_engine/proto_generated
        python3 -m grpc_tools.protoc \
            -Icore/proto \
            --python_out=ai_engine/proto_generated \
            --grpc_python_out=ai_engine/proto_generated \
            core/proto/helios.proto
        echo "Stubs gRPC generados."
    else
        echo "Proto file no encontrado."
    fi
else
    echo "grpc_tools no instalado. Ejecutando: pip install grpcio-tools"
    pip install grpcio-tools
fi

# Inicializar base de datos SQLite
echo ""
echo "Inicializando base de datos SQLite..."
python3 -c "from ai_engine.core.audit_logger import AuditLogger; AuditLogger()" 2>/dev/null && \
    echo "Base de datos inicializada." || \
    echo "WARNING: No se pudo inicializar la BD. Verifique imports."

# Crear directorios necesarios
echo ""
echo "Creando directorios de trabajo..."
mkdir -p logs data temp config

echo ""
echo "========================================"
echo "  SETUP COMPLETADO"
echo "========================================"
echo ""
echo "Siguientes pasos:"
echo "1. Configure las variables de entorno en .env"
echo "2. Ejecute: ./scripts/start_daemon.sh"
echo ""
