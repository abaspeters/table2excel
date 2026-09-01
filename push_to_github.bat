@echo off
REM ===================================================================
REM  Push this project to GitHub. Run once to set up, then any time
REM  afterwards to publish changes.
REM
REM  Before running:
REM    1. Install Git from git-scm.com (accept the defaults)
REM    2. Create an EMPTY repo on github.com - no README, no .gitignore
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

git --version >nul 2>&1
if errorlevel 1 (
    echo  [X] Git is not installed. Get it from https://git-scm.com
    pause
    exit /b 1
)

if not exist app.py (
    echo  [X] This script is not in the project folder.
    echo      It must sit next to app.py and the core folder.
    pause
    exit /b 1
)

REM Guard against publishing the API key. .gitignore covers this, but a
REM key on GitHub is compromised within minutes of the push - bots scan
REM for them continuously - so it is worth checking rather than trusting.
git check-ignore -q .env 2>nul
if errorlevel 1 (
    if exist .env (
        echo  [X] .env is NOT being ignored by git. Stopping.
        echo      Your API key would be published. Check .gitignore
        echo      contains a line reading:  .env
        pause
        exit /b 1
    )
)

REM Git refuses to commit without an identity. Check it BEFORE doing any
REM work, because the failure otherwise appears several steps later as
REM "src refspec main does not match any", which points at the push and
REM says nothing about the real cause.
for /f "delims=" %%e in ('git config --global user.email 2^>nul') do set GITEMAIL=%%e
if "!GITEMAIL!"=="" (
    echo.
    echo  Git does not know who you are yet. One-time setup.
    echo.
    set /p GITEMAIL="  Email on your GitHub account: "
    set /p GITNAME="  Your name: "
    git config --global user.email "!GITEMAIL!"
    git config --global user.name "!GITNAME!"
    echo  Saved.
)

if not exist .git (
    echo.
    echo  First-time setup.
    echo.
    set /p GHUSER="  Your GitHub username: "
    set /p GHREPO="  Repository name (e.g. table2excel): "

    git init
    git branch -M main
    git remote add origin https://github.com/!GHUSER!/!GHREPO!.git
    echo.
    echo  Linked to https://github.com/!GHUSER!/!GHREPO!
)

echo.
set /p MSG="  Describe this change (or press Enter): "
if "!MSG!"=="" set MSG=Update

git add .
git commit -m "!MSG!"

REM Do not infer "nothing to commit" from the exit code - a genuinely failed
REM commit returns the same thing. Ask git whether a commit actually exists.
git rev-parse HEAD >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [X] Nothing has been committed, so there is nothing to push.
    echo      Scroll up: the real error is in the commit output above.
    pause
    exit /b 1
)

echo.
echo  Pushing... a browser window may open to sign you in.
git push -u origin main

if errorlevel 1 (
    echo.
    echo  [X] Push failed. Most likely causes:
    echo      - Sign-in was cancelled or failed in the browser.
    echo      - The repo on GitHub already has files in it. Either create
    echo        a fresh empty repo, or run:  git pull --rebase origin main
    echo        and then run this script again.
    echo      - Wrong username or repo name. Delete the hidden .git folder
    echo        in here and run this again to re-enter them.
    pause
    exit /b 1
)

echo.
echo  Done. Your code is on GitHub.
echo  Next: follow ONLINE_SETUP.md Part 2 to deploy it.
echo.
pause
