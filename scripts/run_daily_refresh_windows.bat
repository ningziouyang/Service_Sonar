@echo off
setlocal

REM Move to project root. This works because this file is inside the scripts folder.
cd /d "%~dp0.."

REM Create log folder if it does not exist.
if not exist logs mkdir logs

echo ============================================================ >> logs\daily_refresh.log
echo Service Sonar daily refresh started at %date% %time% >> logs\daily_refresh.log
echo ============================================================ >> logs\daily_refresh.log

REM Run scheduled pipeline refresh:
REM --scrape    = collect new forum posts
REM --innovate  = update Agent 4 service opportunities after analysis
REM --agent3-limit 50 = limit LLM processing per run to avoid API overload
REM Trend snapshots, proactive alerts and evaluation reports run by default.
python pipeline_refresh.py --scrape --innovate --agent3-limit 50 --agent3-sleep 1 >> logs\daily_refresh.log 2>&1

echo ============================================================ >> logs\daily_refresh.log
echo Service Sonar daily refresh finished at %date% %time% >> logs\daily_refresh.log
echo ============================================================ >> logs\daily_refresh.log
echo. >> logs\daily_refresh.log

endlocal
