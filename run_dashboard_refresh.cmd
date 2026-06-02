@echo off
REM Weekly auto-refresh for the Hedera Moderator Intelligence Dashboard.
REM Scrapes newest r/Hedera data, appends to CSVs, rebuilds dashboard_hedera.html.
cd /d "C:\Users\Administrator\Music\reddit-universal-scraper"
echo ===== %DATE% %TIME% refresh start ===== >> "logs\dashboard_refresh.log"
"C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe" -X utf8 refresh_dashboard.py >> "logs\dashboard_refresh.log" 2>&1
echo ===== %DATE% %TIME% refresh end (exit %ERRORLEVEL%) ===== >> "logs\dashboard_refresh.log"
