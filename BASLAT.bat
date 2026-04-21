@echo off
setlocal
cd /d "%~dp0"

:: Mevcut projenin sanal ortamini kullan
set "VENV_PATH=%~dp0..\Introduction-to-Data-Visualization-Project-Assignment\.venv"

if not exist "%VENV_PATH%\Scripts\pythonw.exe" (
    echo [HATA] Sanal ortam bulunamadi: %VENV_PATH%
    echo [INFO] Lutfen once Introduction-to-Data-Visualization-Project-Assignment
    echo [INFO] klasoründeki kurulum.bat dosyasini calistirin.
    pause
    exit /b 1
)

start "Radyoloji Rapor Asistanı" /B "%VENV_PATH%\Scripts\pythonw.exe" "%~dp0main.pyw"
echo [OK] Radyoloji Rapor Asistanı baslatildi!
echo [INFO] F8 ile radyoloji raporu metnini analiz edin.
timeout /t 2 >nul
exit /b 0
