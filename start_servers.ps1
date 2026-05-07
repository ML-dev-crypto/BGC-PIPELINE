# BGC-QDR Full-Stack Startup Script
# Starts both backend and frontend servers

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  BGC-QDR Full-Stack Application Startup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found! Please install Python 3.8+" -ForegroundColor Red
    exit 1
}

# Check if Flask is installed
try {
    python -c "import flask" 2>&1 | Out-Null
    Write-Host "✅ Flask is installed" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Flask not found. Installing..." -ForegroundColor Yellow
    pip install flask flask-cors
}

Write-Host ""
Write-Host "Starting servers..." -ForegroundColor Cyan
Write-Host ""

# Start backend in a new window
Write-Host "🚀 Starting Backend API (port 5000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python backend_api.py"

# Wait a bit for backend to start
Start-Sleep -Seconds 2

# Start frontend in a new window
Write-Host "🌐 Starting Frontend Server (port 3000)..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; python -m http.server 3000"

# Wait a bit for frontend to start
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  ✅ Servers Started Successfully!" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Backend API:  http://localhost:5000/api" -ForegroundColor Cyan
Write-Host "Frontend:     http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Opening browser..." -ForegroundColor Yellow
Start-Sleep -Seconds 2

# Open browser
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Servers are running in separate windows" -ForegroundColor Cyan
Write-Host "  Close those windows to stop the servers" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to run integration tests..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Run tests
Write-Host ""
Write-Host "Running integration tests..." -ForegroundColor Cyan
python test_integration.py

Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Yellow
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
