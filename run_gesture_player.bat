@echo off
REM Launcher for the Gesture Media Controller
REM Double-click this file to start the program

cd /d "%~dp0"
python gesture_player.py

REM Keep the window open if the program exits with an error
if errorlevel 1 pause
