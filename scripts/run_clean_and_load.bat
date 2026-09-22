@echo off
cd /d C:\Dev\india-air-quality-intel
"C:\Dev\india-air-quality-intel\venv\Scripts\python.exe" -m src.loading.run_clean_and_load >> "C:\Dev\india-air-quality-intel\logs\task_scheduler_clean_and_load.log" 2>&1
exit /b %ERRORLEVEL%
