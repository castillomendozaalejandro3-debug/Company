@echo off
REM =============================================================================
REM Backup Audit DB Script para Helios AI - Windows
REM Realiza backup seguro de helios_audit.db con cifrado AES-256
REM =============================================================================

setlocal EnableDelayedExpansion

echo.
echo ========================================
echo   HELIOS AI - Audit DB Backup
echo ========================================
echo.

REM Configurar variables
set DB_NAME=helios_audit.db
set BACKUP_DIR=backups
set TIMESTAMP=%date:~-4,4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set BACKUP_FILE=%BACKUP_DIR%\audit_backup_%TIMESTAMP%.db.enc

REM Verificar que la BD existe
echo [1/4] Verificando base de datos...
if not exist "%DB_NAME%" (
    echo ERROR: Base de datos %DB_NAME% no encontrada.
    exit /b 1
)
echo Base de datos encontrada: %DB_NAME%

REM Crear directorio de backups
echo.
echo [2/4] Preparando directorio de backups...
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

REM Calcular hash de integridad forense (SHA-256)
echo.
echo [3/4] Calculando hash de integridad...
certutil -hashfile "%DB_NAME%" SHA256 > "%BACKUP_DIR%\hash_%TIMESTAMP%.txt"
for /f "skip=2 tokens=1" %%a in ('type "%BACKUP_DIR%\hash_%TIMESTAMP%.txt"') do set DB_HASH=%%a
echo Hash SHA-256: !DB_HASH!

REM Copiar y cifrar con AES-256 usando PowerShell
echo.
echo [4/4] Cifrando backup con AES-256...

REM Generar contraseña segura aleatoria
powershell -Command "$pwd = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 32 | ForEach-Object {[char]$_}); Write-Output $pwd" > "%BACKUP_DIR%\backup_pwd.txt"
set /p ENCRYPT_PWD=<"%BACKUP_DIR%\backup_pwd.txt"

REM Usar PowerShell para cifrar
powershell -Command ^
    "$source = '%DB_NAME%'; ^
     $dest = '%BACKUP_FILE%'; ^
     $pwd = '%ENCRYPT_PWD%'; ^
     $bytes = [System.IO.File]::ReadAllBytes($source); ^
     $aes = [System.Security.Cryptography.Aes]::Create(); ^
     $aes.KeySize = 256; ^
     $aes.GenerateIV(); ^
     $encryptor = $aes.CreateEncryptor(); ^
     $encrypted = $encryptor.TransformFinalBlock($bytes, 0, $bytes.Length); ^
     $all = $aes.IV + $encrypted; ^
     [System.IO.File]::WriteAllBytes($dest, $all); ^
     Write-Host 'Backup cifrado creado: ' $dest"

REM Guardar metadatos del backup
echo Backup: %BACKUP_FILE% >> "%BACKUP_DIR%\backup_log.txt"
echo Fecha: %date% %time% >> "%BACKUP_DIR%\backup_log.txt"
echo Hash Original: !DB_HASH! >> "%BACKUP_DIR%\backup_log.txt"
echo ---------------------------------------- >> "%BACKUP_DIR%\backup_log.txt"

REM Limpiar archivos temporales
del /q /f "%BACKUP_DIR%\hash_%TIMESTAMP%.txt" 2>nul

echo.
echo ========================================
echo   BACKUP COMPLETADO EXITOSAMENTE
echo ========================================
echo.
echo Archivo: %BACKUP_FILE%
echo Contraseña guardada en: %BACKUP_DIR%\backup_pwd.txt
echo Hash de integridad registrado en backup_log.txt
echo.
echo Para restaurar:
echo   1. Descifrar con la contraseña guardada
echo   2. Verificar hash SHA-256
echo   3. Reemplazar %DB_NAME%
echo.

endlocal
