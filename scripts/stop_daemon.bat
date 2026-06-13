@echo off
REM =============================================================================
REM Stop Daemon Script para Helios AI - Windows
REM Detiene el KernelDaemon de forma segura y limpia sockets
REM =============================================================================

setlocal EnableDelayedExpansion

echo.
echo ========================================
echo   HELIOS AI - Stopping KernelDaemon
echo ========================================
echo.

REM Buscar proceso del daemon
echo [1/3] Buscando proceso KernelDaemon...
tasklist /FI "WINDOWTITLE eq Helios KernelDaemon*" /FO CSV /NH >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2 delims=," %%a in ('tasklist /FI "WINDOWTITLE eq Helios KernelDaemon*" /FO CSV /NH') do (
        set PID=%%a
        goto :found
    )
)

REM Alternativa: buscar por nombre de script
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH ^| findstr kernel_daemon') do (
    set PID=%%a
    goto :found
)

echo No se encontro el proceso del daemon.
goto :cleanup

:found
echo Proceso encontrado: PID !PID!
echo.

REM Detener proceso
echo [2/3] Deteniendo proceso...
taskkill /F /PID !PID! 2>nul
if %errorlevel% equ 0 (
    echo Proceso detenido correctamente.
) else (
    echo WARNING: No se pudo detener el proceso. Puede que ya este cerrado.
)

:cleanup
echo.
echo [3/3] Limpiando recursos...

REM Liberar puerto (matar cualquier cosa en 50051)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":50051"') do (
    echo Liberando puerto 50051 (PID %%a)...
    taskkill /F /PID %%a 2>nul
)

REM Eliminar archivos temporales
del /q /f temp\*.sock 2>nul
del /q /f kernel_daemon.pid 2>nul
del /q /f *.pid 2>nul

echo Limpieza completada.

echo.
echo ========================================
echo   KERNELDAEMON DETENIDO
echo ========================================
echo.

endlocal
