@echo off
title GoldHybrid A.I. -- Service Mode
cd /d %~dp0

echo Starting GoldHybrid A.I. in service mode (Task Scheduler)...

echo Cleaning up any existing GoldHybrid processes...
powershell -NoProfile -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*dashboard_gold.py*' -or $_.CommandLine -like '*watchdog_gold.py*' -or $_.CommandLine -like '*main_goldhybrid.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" > nul 2>&1
ping -n 3 127.0.0.1 > nul

start /B python dashboard_gold.py

ping -n 11 127.0.0.1 > nul

start /B python watchdog_gold.py

echo GoldHybrid A.I. launched in background -- dashboard + watchdog running.
exit /b 0
