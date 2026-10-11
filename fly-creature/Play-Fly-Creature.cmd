@echo off
rem Double-click to play. Starts the neural service and Godot, and stops the
rem service when the game window closes. See tools\play.ps1 for options.
start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\play.ps1" %*
