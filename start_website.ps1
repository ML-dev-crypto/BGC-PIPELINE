# BGC-QDR Website Startup Script
# Starts both frontend (Vite) and backend (Flask) servers

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "  BGC-QDR Website - Full Stack Startup" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found. Please install Python 3.8+" -ForegroundColor Red
    exit 1
}

# Check if Node.js is available
try {
    $nodeVersion = node --version
    Write-Host "✅ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js not found. Please install Node.js 16+" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "📦 Installing dependencies..." -ForegroundColor Yellow
Write-Host ""

# Install Python dependencies
Write-Host "  Installing Flask backend..." -ForegroundColor Cyan
pip install -q -r backend_requirements.txt
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✅ Backend dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  Backend install had warnings (continuing...)" -ForegroundColor Yellow
}

# Install Node dependencies (if not already installed)
if (-not (Test-Path "website/node_modules")) {
    Write-Host "  Installing Vite frontend..." -ForegroundColor Cyan
    Push-Location website
    npm install
    Pop-Location
    Write-Host "  ✅ Frontend dependencies installed" -ForegroundColor Green
}

Write-Host ""
Write-Host "🚀 Starting servers..." -ForegroundColor Yellow
Write-Host ""

# Start backend in background
Write-Host "  Starting Flask backend on http://localhost:5000..." -ForegroundColor Cyan
Start-Process python -ArgumentList "backend_api.py" -WindowStyle Normal

# Wait a moment for backend to start
Start-Sleep -Seconds 2

# Start frontend
Write-Host "  Starting Vite frontend on http://localhost:3000..." -ForegroundColor Cyan
Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host "  ✅ BGC-QDR Website is running!" -ForegroundColor Green
Write-Host ("=" * 60) -ForegroundColor Green
Write-Host ""
Write-Host "  🌐 Frontend: http://localhost:3000" -ForegroundColor Cyan
Write-Host "  📡 Backend:  http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop the frontend" -ForegroundColor Yellow
Write-Host "  (Backend will continue running in separate window)" -ForegroundColor Yellow
Write-Host ""

Push-Location website
npm run dev
Pop-Location
