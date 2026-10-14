@echo off
title Shipping Watch - 1-Command Launcher
echo ======================================================================
echo  SHIPPING WATCH: 1-COMMAND LAUNCHER (WINDOWS)
echo ======================================================================

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found in your PATH.
    echo Please install Python 3.10+ or run with Docker: docker compose up --build
    pause
    exit /b 1
)

REM Run unified launcher
python start.py

pause
