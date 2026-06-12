@echo off
REM =============================================================================
REM Start Daemon Script para Helios AI - Windows
REM Inicia el KernelDaemon de forma segura con verificación de puerto
REM =============================================================================

setlocal EnableDelayedExpansion

echo.
echo ========================================
echo   HELIOS AI - Starting KernelDaemon
echo ========================================
echo.

REM Verificar si el puerto ya está en uso
echo [1/3] Verificando puerto 50051...
netstat -ano | findstr ":50051" >nul 2>&1
if %errorlevel% equ 0 (
    echo WARNING: Puerto 50051 ya está en uso.
    echo ¿Desea detener el proceso existente? (S/N)
    set /p response=" "
    if /i "!response!"=="S" (
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":50051"') do (
            echo Deteniendo proceso PID %%a...
            taskkill /F /PID %%a
        )
        timeout /t 2 >nul
    ) else (
        echo Cancelando inicio.
        exit /b 1
    )
)

REM Limpiar sockets residuales
echo.
echo [2/3] Limpiando archivos temporales...
del /q /f temp\*.sock 2>nul
del /q /f *.pid 2>nul
echo Limpieza completada.

REM Activar entorno virtual e iniciar daemon
echo.
echo [3/3] Iniciando KernelDaemon...
call venv\Scripts\activate.bat 2>nul

REM Guardar PID
echo %RANDOM% > kernel_daemon.pid

REM Iniciar en segundo plano
start "Helios KernelDaemon" cmd /c "python ai_engine\core\kernel_daemon.py"

timeout /t 3 >nul

REM Verificar que inició correctamente
netstat -ano | findstr ":50051" >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   KERNELDAEMON INICIADO EXITOSAMENTE
    echo ========================================
    echo Puerto: 50051
    echo.
    echo Para detener: scripts\stop_daemon.bat
    echo.
) else (
    echo.
    echo ERROR: El daemon no inició correctamente.
    echo Revise los logs en: logs\kernel_daemon.log
    echo.
    exit /b 1
)

endlocal
