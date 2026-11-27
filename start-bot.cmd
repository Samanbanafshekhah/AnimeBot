@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bot.ps1" start
if errorlevel 1 pause
