@echo off
chcp 65001 >nul
cd /d "%~dp0"
"TradeQuery.exe" --set-admin-password
pause
