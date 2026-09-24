@echo off
chcp 65001 > nul
title Discord Music and TikTok Bot
cd /d "%~dp0"

echo ======================================================================
echo              Discord Music and TikTok Bot Launcher
echo ======================================================================
echo.

if not exist ".env" (
    echo [ERROR] .env file not found!
    echo Please copy .env.example to .env and configure your DISCORD_TOKEN.
    echo.
    pause
    exit /b 1
)

if exist "venv\Scripts\python.exe" (
    echo [INFO] Using virtual environment: venv
    set "PYTHON_CMD=venv\Scripts\python.exe"
) else (
    echo [INFO] Virtual environment not found, using system python...
    set "PYTHON_CMD=python"
)

echo [INFO] Starting bot.py...
echo ======================================================================
echo.

"%PYTHON_CMD%" bot.py

echo.
echo ======================================================================
echo [INFO] Bot process has exited.
echo ======================================================================
pause
