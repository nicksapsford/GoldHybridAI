@echo off
title GoldHybrid A.I. - Port 5043
cd /d C:\Users\abc\Desktop\GoldHybridAI
start /min "GoldHybrid A.I. Dashboard" cmd /c C:\Users\abc\AppData\Local\Programs\Python\Python313\python.exe dashboard_gold.py
start /min "GoldHybrid A.I. Engine" cmd /c C:\Users\abc\AppData\Local\Programs\Python\Python313\python.exe watchdog_gold.py
timeout /t 5 /nobreak >nul
start http://localhost:5043
