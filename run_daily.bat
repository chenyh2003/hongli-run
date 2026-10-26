@echo off
cd /d "%~dp0"
python code\run_all.py >> output\run.log 2>&1
