@echo off
REM setup_minikube.bat
REM Runs the PowerShell setup script with ExecutionPolicy Bypass.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_minikube.ps1"
pause
