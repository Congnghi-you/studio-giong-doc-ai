@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
title Studio Giong Doc AI Tieng Viet
cd /d "%~dp0"

echo =======================================================
echo    STUDIO GIONG DOC AI TIENG VIET
echo =======================================================
echo.

REM ---------- 1. Tim Python da co du thu vien ----------
set "PY="

py -3.13 -c "import flask, edge_tts, faster_whisper, yt_dlp, ctranslate2, onnxruntime, numpy" >nul 2>nul
if not errorlevel 1 set "PY=py -3.13"
if defined PY goto :chay

py -3 -c "import flask, edge_tts, faster_whisper, yt_dlp, ctranslate2, onnxruntime, numpy" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto :chay

python -c "import flask, edge_tts, faster_whisper, yt_dlp, ctranslate2, onnxruntime, numpy" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :chay

REM ---------- 2. Chua du thu vien: tu cai (chi lan dau, can Internet) ----------
echo [!] May chua co du thu vien, dang tu cai dat (chi lan dau)...
echo.

py -3.13 -V >nul 2>nul
if not errorlevel 1 goto :cai_py313

python -V >nul 2>nul
if not errorlevel 1 goto :cai_python

goto :khong_co_python

:cai_py313
set "PY=py -3.13"
goto :cai

:cai_python
set "PY=python"

:cai
%PY% -m pip install --disable-pip-version-check --upgrade pip
%PY% -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
if errorlevel 1 goto :cai_loi
goto :chay

REM ---------- 3. Chay ung dung ----------
:chay
echo.
echo Dang giai phong cong 5000 (neu dang bi chiem)...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /C:"LISTENING" ^| findstr /C:":5000 "') do taskkill /F /PID %%P >nul 2>nul

echo.
echo Dang khoi dong... trinh duyet se tu mo http://localhost:5000
echo (Dong cua so nay la tat ung dung)
echo.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:5000"
%PY% app.py
pause
exit /b 0

REM ---------- Loi ----------
:khong_co_python
echo.
echo [X] May chua cai Python 3.13.
echo     Tai tai: https://www.python.org/downloads/
echo     Khi cai nho tick "Add python.exe to PATH", roi bam lai file nay.
pause
exit /b 1

:cai_loi
echo.
echo [X] Cai thu vien that bai. Kiem tra ket noi Internet roi bam lai.
pause
exit /b 1
