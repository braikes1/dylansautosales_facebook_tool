@echo off
title Auto Bot — Build EXE
color 0A
echo ============================================================
echo  Auto Bot EXE Builder
echo ============================================================
echo.

:: ── 1. Check Python ──────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not on PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found.

:: ── 2. Install / upgrade PyInstaller ─────────────────────────
echo.
echo Installing PyInstaller...
pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)
echo [OK] PyInstaller ready.

:: ── 3. Install project dependencies (so PyInstaller can find them) ──
echo.
echo Installing project dependencies...
pip install --quiet -r api\requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install project dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

:: ── 4. Run PyInstaller ────────────────────────────────────────
echo.
echo Building AutoBot.exe (this may take 1-3 minutes)...
echo.
pyinstaller autobot.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed. See errors above.
    pause
    exit /b 1
)

:: ── 5. Done ──────────────────────────────────────────────────
echo.
echo ============================================================
echo  BUILD COMPLETE!
echo  Your file is at:  dist\AutoBot.exe
echo ============================================================
echo.
echo Share the dist\AutoBot.exe file with your team.
echo They just need to double-click it — no setup required.
echo.
pause
