@echo off
echo.
echo ============================================================
echo    BGC-QDR Full-Stack Integration Setup
echo ============================================================
echo.

echo [1/5] Creating directories...
if not exist "frontend" mkdir frontend
if not exist "frontend\assets" mkdir frontend\assets
if not exist "uploads" mkdir uploads
if not exist "results" mkdir results
echo   Done!

echo.
echo [2/5] Copying HTML file...
if exist "New folder\index.html" (
    copy "New folder\index.html" "frontend\index.html" >nul
    echo   Done!
) else (
    echo   Warning: Source file not found
)

echo.
echo [3/5] Copying video file...
if exist "New folder\DNA.mp4" (
    copy "New folder\DNA.mp4" "frontend\assets\DNA.mp4" >nul
    echo   Done!
) else (
    echo   Warning: Video file not found
)

echo.
echo [4/5] Verifying files...
if exist "frontend\app.js" (echo   frontend\app.js - OK) else (echo   frontend\app.js - MISSING)
if exist "frontend\styles.css" (echo   frontend\styles.css - OK) else (echo   frontend\styles.css - MISSING)
if exist "backend_api.py" (echo   backend_api.py - OK) else (echo   backend_api.py - MISSING)

echo.
echo [5/5] Checking Python...
python --version 2>nul
if errorlevel 1 (
    echo   Python not found!
) else (
    echo   Python OK!
)

echo.
echo ============================================================
echo    Setup Complete!
echo ============================================================
echo.
echo Next steps:
echo.
echo 1. Start backend:  python backend_api.py
echo 2. Start frontend: cd frontend ^&^& python -m http.server 3000
echo 3. Open browser:   http://localhost:3000
echo.
echo Or run: start_fullstack.ps1
echo.
pause
