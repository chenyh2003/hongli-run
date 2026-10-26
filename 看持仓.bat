@echo off
cd /d "%~dp0"
echo Updating Strategy-1 BCD ...
python code\run_s1.py
if errorlevel 1 goto err
python code\dashboard.py
if errorlevel 1 goto err
start "" "output\report\dashboard.html"
exit /b 0
:err
echo Run failed. See output\run.log
pause
