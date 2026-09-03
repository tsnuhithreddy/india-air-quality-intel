@echo off
cd /d C:\Dev\india-air-quality-intel
"C:\Dev\india-air-quality-intel\venv\Scripts\python.exe" "C:\Dev\india-air-quality-intel\src\ingestion\fetch_openaq.py" >> "C:\Dev\india-air-quality-intel\logs\task_scheduler_openaq.log" 2>&1