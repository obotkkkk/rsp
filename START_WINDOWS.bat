@echo off
chcp 65001 >nul
title VanGioi RSP Pro
cd /d "%~dp0"
echo ============================================================
echo   VanGioi RSP Pro - Local Studio + Lite Pack Creator
echo ============================================================
echo.
where py >nul 2>&1
if not errorlevel 1 (
  py -3 app.py
  goto :end
)
where python >nul 2>&1
if not errorlevel 1 (
  python app.py
  goto :end
)
echo [ERROR] Khong tim thay Python trong PATH.
echo Cai Python 3.10+ tai https://www.python.org/downloads/
:end
echo.
echo Da thoat ung dung. Bam phim bat ky de dong.
pause >nul
