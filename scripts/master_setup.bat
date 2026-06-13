@echo off
REM =============================================================================
REM Master Setup Script para Helios AI
REM Configura entorno, dependencias, compilación Rust y base de datos
REM =============================================================================

setlocal EnableDelayedExpansion

echo.
echo ========================================
echo   HELIOS AI - Master Setup Script
echo ========================================
echo.

REM Verificar Python
echo [1/6] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no encontrado. Instale Python 3.9+
    exit /b 1
)
echo Python instalado correctamente.

REM Crear entorno virtual
echo.
echo [2/6] Creando entorno virtual...
if not exist "venv" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Fallo al crear entorno virtual
        exit /b 1
    )
    echo Entorno virtual creado.
) else (
    echo Entorno virtual ya existe.
)

REM Activar entorno virtual
call venv\Scripts\activate.bat

REM Instalar dependencias Python
echo.
echo [3/6] Instalando dependencias Python...
if exist "requirements.txt" (
    pip install --upgrade pip
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo WARNING: Algunas dependencias fallaron
    )
) else (
    echo requirements.txt no encontrado en directorio actual
)

if exist "ai_engine\requirements.txt" (
    pip install -r ai_engine\requirements.txt
)

REM Verificar e instalar Rust
echo.
echo [4/6] Verificando Rust/Cargo...
cargo --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Rust no encontrado. Intentando instalar...
    echo Descargando rustup...
    curl https://sh.rustup.rs -sSf | sh
    if %errorlevel% neq 0 (
        echo WARNING: Instalacion automatica fallo. Instale Rust manualmente desde https://rustup.rs
    ) else (
        call "%USERPROFILE%\.cargo\env"
    )
) else (
    echo Rust instalado correctamente.
)

REM Compilar nucleo Rust
echo.
echo [5/6] Compilando nucleo Rust...
if exist "core\Cargo.toml" (
    cd core
    cargo build --release
    if %errorlevel% neq 0 (
        echo WARNING: Compilacion Rust fallo o tiene advertencias
    ) else (
        echo Compilacion Rust completada.
    )
    cd ..
) else (
    echo Cargo.toml no encontrado. Saltando compilacion Rust.
)

REM Generar stubs gRPC
echo.
echo [6/6] Generando stubs gRPC...
python -m grpc_tools.protoc --version >nul 2>&1
if %errorlevel% equ 0 (
    if exist "core\proto\helios.proto" (
        mkdir ai_engine\proto_generated 2>nul
        python -m grpc_tools.protoc ^
            -Icore/proto ^
            --python_out=ai_engine/proto_generated ^
            --grpc_python_out=ai_engine/proto_generated ^
            core/proto/helios.proto
        echo Stubs gRPC generados.
    ) else (
        echo Proto file no encontrado.
    )
) else (
    echo grpc_tools no instalado. Ejecutando: pip install grpcio-tools
    pip install grpcio-tools
)

REM Inicializar base de datos SQLite
echo.
echo Inicializando base de datos SQLite...
python -c "from ai_engine.core.audit_logger import AuditLogger; AuditLogger()" 2>nul
if %errorlevel% equ 0 (
    echo Base de datos inicializada.
) else (
    echo WARNING: No se pudo inicializar la BD. Verifique imports.
)

REM Crear directorios necesarios
echo.
echo Creando directorios de trabajo...
mkdir logs 2>nul
mkdir data 2>nul
mkdir temp 2>nul
mkdir config 2>nul

echo.
echo ========================================
echo   SETUP COMPLETADO
echo ========================================
echo.
echo Siguientes pasos:
echo 1. Configure las variables de entorno en .env
echo 2. Ejecute: scripts\start_daemon.bat
echo.

endlocal
