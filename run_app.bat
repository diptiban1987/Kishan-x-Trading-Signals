@echo off
title Trading Platform Server
cd /d "%~dp0"

echo ============================================
echo     Trading Platform - Local Server
echo ============================================
echo.

:: Detect virtual environment
if exist "venv_fresh\Scripts\activate.bat" (
    set VENV_DIR=venv_fresh
) else if exist "venv\Scripts\activate.bat" (
    set VENV_DIR=venv
) else (
    echo [ERROR] Virtual environment not found.
    echo Please run: python -m venv venv_fresh
    pause
    exit /b 1
)

echo [1/3] Activating virtual environment: %VENV_DIR%
call %VENV_DIR%\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo [OK]
echo.

:: Verify key dependencies using venv python directly
echo [2/3] Checking dependencies...
%VENV_DIR%\Scripts\python.exe -c "import flask" 2>nul
if errorlevel 1 (
    echo [WARN] Installing dependencies from requirements.txt...
    %VENV_DIR%\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
)
echo [OK]
echo.

:: Set environment defaults
set FLASK_APP=app.py
set FLASK_ENV=development

:: Get today's date in YYYY-MM-DD format
for /f "tokens=*" %%a in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%a
set LOG_DIR_TRADING=trading\%TODAY%
set LOG_DIR_LOGS=logs\%TODAY%

:: Create today's log directories
if not exist "%LOG_DIR_TRADING%" mkdir "%LOG_DIR_TRADING%"
if not exist "%LOG_DIR_LOGS%" mkdir "%LOG_DIR_LOGS%"

:: Append trading session header to root-level session file
:: (temp Python script avoids pipe escaping issues in cmd)
echo from datetime import datetime > "%TEMP%\ts.py"
echo d = datetime.now() >> "%TEMP%\ts.py"
echo path = r'logs\trading_session_%TODAY%.md' >> "%TEMP%\ts.py"
echo with open(path, 'a') as f: >> "%TEMP%\ts.py"
echo     f.write(f'# Trading Session Activity Log - {d.strftime("%%Y-%%m-%%d")}\n\n') >> "%TEMP%\ts.py"
echo     f.write(f'**System:** Indian Auto Trader (DEMO Mode)\n') >> "%TEMP%\ts.py"
echo     f.write(f'**Started:** {d.strftime("%%Y-%%m-%%d %%H:%%M:%%S")}\n') >> "%TEMP%\ts.py"
echo     f.write(f'**Mode:** DEMO (Mock Funds 1,00,000)\n\n') >> "%TEMP%\ts.py"
echo     h = 'Time X Symbol X Action X Entry X Exit X Qty X P&L X Balance X Strategy'.replace('X', chr(124)) >> "%TEMP%\ts.py"
echo     s = '-----X--------X--------X-------X------X-----X-----X---------X----------'.replace('X', chr(124)) >> "%TEMP%\ts.py"
echo     f.write(h + chr(10) + s + chr(10)) >> "%TEMP%\ts.py"
"%VENV_DIR%\Scripts\python.exe" "%TEMP%\ts.py"
del "%TEMP%\ts.py"

:: Write temp tee-server script for dual logging (avoids cmd pipe issues)
echo import sys, subprocess, os > "%TEMP%\tee.py"
echo p, s, l1, l2 = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] >> "%TEMP%\tee.py"
echo os.environ['PORT'] = p >> "%TEMP%\tee.py"
echo proc = subprocess.Popen([sys.executable, s], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) >> "%TEMP%\tee.py"
echo with open(l1, 'a') as f1, open(l2, 'a') as f2: >> "%TEMP%\tee.py"
echo     for line in proc.stdout: >> "%TEMP%\tee.py"
echo         f1.write(line); f1.flush(); f2.write(line); f2.flush() >> "%TEMP%\tee.py"
echo proc.wait() >> "%TEMP%\tee.py"

:: Unbuffered Python output for real-time log streaming
set PYTHONUNBUFFERED=1

echo [3/3] Starting servers in background...
echo   Logs will be saved to:
echo     - %CD%\%LOG_DIR_TRADING%
echo     - %CD%\%LOG_DIR_LOGS%
echo.
echo   Main Server  : http://localhost:5000
echo   Indian Only  : http://localhost:5050
echo.
echo   Dashboard    : http://localhost:5000/login
echo   Admin        : http://localhost:5000/admin_panel
echo   Market       : http://localhost:5000/market
echo   Indian Focus : http://localhost:5050/indian
echo.
echo   Servers are running in minimized windows.
echo   They will keep running until market hours end.
echo   To stop all: taskkill /im python.exe
echo ============================================
echo.

:: Start Main Server on port 5000 (tees output to both log folders)
start /MIN "Main Server :5000" "%VENV_DIR%\Scripts\python.exe" "%TEMP%\tee.py" 5000 app.py "%LOG_DIR_TRADING%\main_server.log" "%LOG_DIR_LOGS%\main_server.log"

:: Start Indian Only Server on port 5050
start /MIN "Indian Only :5050" "%VENV_DIR%\Scripts\python.exe" "%TEMP%\tee.py" 5050 indian_only\app.py "%LOG_DIR_TRADING%\indian_only.log" "%LOG_DIR_LOGS%\indian_only.log"

echo.
echo Both servers started successfully.
echo Close this window or press any key to dismiss (servers stay running)...
pause >nul
