@echo off
REM Runs the daily WhatsApp reminder jobs (OPD appointment reminders +
REM IPD discharge follow-up reminders). Scheduled via Windows Task
REM Scheduler -- see the "HMS Daily WhatsApp Reminders" task.

cd /d "%~dp0"

if not exist "logs" mkdir "logs"

set LOGFILE=logs\daily_reminders.log

echo. >> "%LOGFILE%"
echo ==== %date% %time% ==== >> "%LOGFILE%"

".venv_new\Scripts\python.exe" manage.py send_appointment_reminders >> "%LOGFILE%" 2>&1
".venv_new\Scripts\python.exe" manage.py send_discharge_followup_reminders >> "%LOGFILE%" 2>&1

echo ==== done ==== >> "%LOGFILE%"
