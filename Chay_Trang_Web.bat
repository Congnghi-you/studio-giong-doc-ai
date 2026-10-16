@echo off
chcp 65001 >nul
title Studio Giọng Đọc AI Tiếng Việt
echo =======================================================
echo    STUDIO GIỌNG ĐỌC AI TIẾNG VIỆT (TỰ NHIÊN, KHÔNG GIỚI HẠN)
echo =======================================================
echo.
echo Đang đóng các tiến trình cũ để tránh xung đột cổng...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM python3.13.exe 2>nul

echo.
echo Đang khởi động trang web...
echo Mở trình duyệt tại: http://localhost:5000
echo.
start http://localhost:5000
python app.py
pause
