@echo off
REM pre-push hook for Windows PowerShell
REM Place this in: .git/hooks/pre-push (without .ps1 extension)
REM Or run: Copy-Item pre-commit-hook.ps1 -Destination .git/hooks/pre-push

echo.
echo [*] Pre-push hook: Preparing Docker images...
echo.

REM Get git info
for /f %%i in ('git rev-parse --short HEAD') do set GIT_HASH=%%i
for /f %%i in ('git rev-parse --abbrev-ref HEAD') do set GIT_BRANCH=%%i

echo [*] Current commit: %GIT_HASH% on branch %GIT_BRANCH%
echo.

REM Check for uncommitted changes
git status --porcelain | findstr . >nul
if errorlevel 1 (
    echo [OK] No uncommitted changes
) else (
    echo [!] WARNING: You have uncommitted changes!
    echo.
)

REM Check if Dockerfile or requirements.txt changed
git diff HEAD~1 HEAD --quiet -- Dockerfile requirements.txt
if errorlevel 1 (
    echo [!] Dockerfile or requirements.txt changed - clearing container cache
    echo [*] Removing old images...
    docker rmi real-estate-env:latest 2>nul
    docker image prune -f 2>nul
) else (
    echo [OK] Dockerfile and requirements.txt unchanged
)

echo.
echo [OK] Pre-push hook complete. Proceeding with push.
echo.

exit /b 0
