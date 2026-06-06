@echo off
REM Script para generar stubs de Python desde el archivo .proto (Windows)

set PROTO_FILE=core\proto\helios.proto
set OUTPUT_DIR=ai_engine\proto_generated

echo Generando stubs de Python desde %PROTO_FILE%...

python -m grpc_tools.protoc ^
    -I core\proto ^
    --python_out=%OUTPUT_DIR% ^
    --grpc_python_out=%OUTPUT_DIR% ^
    %PROTO_FILE%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Stubs generados exitosamente en %OUTPUT_DIR%
    dir %OUTPUT_DIR%
) else (
    echo.
    echo ❌ Error al generar los stubs
    exit /b %ERRORLEVEL%
)
