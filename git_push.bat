@echo off
cd /d c:\weeklyleadershipreports
setlocal enabledelayedexpansion

REM Disable pager
git config core.pager ""

REM Set environment to avoid pager
set GIT_PAGER=
set GIT_EDITOR=true
set TERM=dumb

REM Push to upstream
echo Pushing to GitHub...
git push upstream main -v

if %errorlevel% equ 0 (
    echo Push successful!
) else (
    echo Push failed with exit code %errorlevel%
)

pause
