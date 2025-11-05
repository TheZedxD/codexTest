@echo off
REM Windows batch launcher script for TVPlayer
REM Simple wrapper that calls the PowerShell runner

powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
