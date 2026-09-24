@echo off
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0opencode-repair-sessions.py" %*
) else (
    python "%~dp0opencode-repair-sessions.py" %*
)
pause
