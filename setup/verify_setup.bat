@echo off
echo.
echo ============================================================
echo    BGC-QDR Integration Verification
echo ============================================================
echo.

echo Checking files...
echo.

set ALL_OK=1

if exist "frontend\index.html" (
    echo [OK] frontend\index.html
) else (
    echo [MISSING] frontend\index.html
    set ALL_OK=0
)

if exist "frontend\app.js" (
    echo [OK] frontend\app.js
) else (
    echo [MISSING] frontend\app.js
    set ALL_OK=0
)

if exist "frontend\styles.css" (
    echo [OK] frontend\styles.css
) else (
    echo [MISSING] frontend\styles.css
    set ALL_OK=0
)

if exist "frontend\assets\DNA.mp4" (
    echo [OK] frontend\assets\DNA.mp4
) else (
    echo [MISSING] frontend\assets\DNA.mp4
    set ALL_OK=0
)

if exist "backend_api.py" (
    echo [OK] backend_api.py
) else (
    echo [MISSING] backend_api.py
    set ALL_OK=0
)

echo.
echo Checking HTML links...
echo.

findstr /C:"styles.css" frontend\index.html >nul
if %errorlevel%==0 (
    echo [OK] CSS linked in HTML
) else (
    echo [MISSING] CSS link in HTML
    set ALL_OK=0
)

findstr /C:"app.js" frontend\index.html >nul
if %errorlevel%==0 (
    echo [OK] JavaScript linked in HTML
) else (
    echo [MISSING] JavaScript link in HTML
    set ALL_OK=0
)

findstr /C:"assets/DNA.mp4" frontend\index.html >nul
if %errorlevel%==0 (
    echo [OK] Video path correct
) else (
    echo [WRONG] Video path incorrect
    set ALL_OK=0
)

echo.
echo ============================================================

if %ALL_OK%==1 (
    echo    Status: READY TO RUN!
    echo ============================================================
    echo.
    echo Everything is set up correctly!
    echo.
    echo To start the application:
    echo.
    echo 1. Open Terminal 1 and run:
    echo    python backend_api.py
    echo.
    echo 2. Open Terminal 2 and run:
    echo    cd frontend
    echo    python -m http.server 3000
    echo.
    echo 3. Open browser to:
    echo    http://localhost:3000
    echo.
) else (
    echo    Status: ISSUES FOUND
    echo ============================================================
    echo.
    echo Please fix the issues above and run this script again.
    echo.
)

pause
