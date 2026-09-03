@echo off
cd /d C:\Dev\india-air-quality-intel
"C:\Dev\india-air-quality-intel\venv\Scripts\python.exe" "C:\Dev\india-air-quality-intel\src\ingestion\fetch_data_gov_in.py" >> "C:\Dev\india-air-quality-intel\logs\task_scheduler_output.log" 2>&1