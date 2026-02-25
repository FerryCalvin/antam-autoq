@echo off
echo ===================================================
echo     MEMULAI ANTAM AUTO-QUEUE WEB DASHBOARD...
echo ===================================================
echo.

echo [1/2] Menyalakan Backend (FastAPI - Python) di port 8000...
:: Start backend properly to respect Windows asyncio policy
start "Antam Backend" cmd /k "python backend/main.py"

echo [2/2] Menyalakan Frontend (React) di port 3000...
:: Navigate to web_panel directory and start the dev server
cd web_panel
start "Antam Frontend" cmd /k "npm start"

echo.
echo Kedua mesin sedang berjalan di latar belakang (jendela hitam terpisah).
echo Tunggu sekitar 10 detik agar mesin siap...
timeout /t 10 /nobreak >nul

echo Selesai! Anda bisa menutup jendela peluncur utama ini.
pause
