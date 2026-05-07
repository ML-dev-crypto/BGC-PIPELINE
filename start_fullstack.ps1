# BGC-QDR Full-Stack Startup Script
# Starts both backend API and frontend server

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "  BGC-QDR Full-Stack Application Startup" -ForegroundColor White
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
Write-Host "Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Python not found! Please install Python 3.8+" -ForegroundColor Red
    exit 1
}

# Check if required Python packages are installed
Write-Host ""
Write-Host "Checking Python dependencies..." -ForegroundColor Yellow
$requiredPackages = @("flask", "flask_cors", "pandas")
$missingPackages = @()

foreach ($package in $requiredPackages) {
    $installed = python -c "import $package" 2>&1
    if ($LASTEXITCODE -ne 0) {
        $missingPackages += $package
        Write-Host "  ✗ $package not installed" -ForegroundColor Red
    } else {
        Write-Host "  ✓ $package installed" -ForegroundColor Green
    }
}

if ($missingPackages.Count -gt 0) {
    Write-Host ""
    Write-Host "Installing missing packages..." -ForegroundColor Yellow
    pip install -r backend_requirements.txt
}

# Create necessary directories
Write-Host ""
Write-Host "Setting up directories..." -ForegroundColor Yellow
$dirs = @("uploads", "results", "frontend/assets")
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  ✓ Created $dir" -ForegroundColor Green
    } else {
        Write-Host "  ✓ $dir exists" -ForegroundColor Green
    }
}

# Copy video file if it exists
if (Test-Path "New folder/DNA.mp4") {
    Write-Host ""
    Write-Host "Copying video asset..." -ForegroundColor Yellow
    Copy-Item "New folder/DNA.mp4" "frontend/assets/DNA.mp4" -Force
    Write-Host "  ✓ DNA.mp4 copied to frontend/assets" -ForegroundColor Green
}

# Start backend server in a new window
Write-Host ""
Write-Host "Starting backend API server..." -ForegroundColor Yellow
$backendJob = Start-Process python -ArgumentList "backend_api.py" -PassThru -WindowStyle Normal
Write-Host "  ✓ Backend API started (PID: $($backendJob.Id))" -ForegroundColor Green
Write-Host "  → http://localhost:5000/api" -ForegroundColor Cyan

# Wait a moment for backend to start
Start-Sleep -Seconds 2

# Start frontend server in a new window
Write-Host ""
Write-Host "Starting frontend server..." -ForegroundColor Yellow
Set-Location frontend
$frontendJob = Start-Process python -ArgumentList "-m", "http.server", "3000" -PassThru -WindowStyle Normal
Set-Location ..
Write-Host "  ✓ Frontend server started (PID: $($frontendJob.Id))" -ForegroundColor Green
Write-Host "  → http://localhost:3000" -ForegroundColor Cyan

# Display summary
Write-Host ""
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "  Application Started Successfully!" -ForegroundColor Green
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""
Write-Host "  Frontend:  " -NoNewline -ForegroundColor White
Write-Host "http://localhost:3000" -ForegroundColor Cyan
Write-Host "  Backend:   " -NoNewline -ForegroundColor White
Write-Host "http://localhost:5000/api" -ForegroundColor Cyan
Write-Host "  API Docs:  " -NoNewline -ForegroundColor White
Write-Host "http://localhost:5000/api/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop both servers" -ForegroundColor Yellow
Write-Host ""
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan

# Keep script running and monitor processes
try {
    while ($true) {
        Start-Sleep -Seconds 5
        
        # Check if processes are still running
        if ($backendJob.HasExited) {
            Write-Host ""
            Write-Host "  ✗ Backend server stopped unexpectedly" -ForegroundColor Red
            break
        }
        if ($frontendJob.HasExited) {
            Write-Host ""
            Write-Host "  ✗ Frontend server stopped unexpectedly" -ForegroundColor Red
            break
        }
    }
} finally {
    # Cleanup on exit
    Write-Host ""
    Write-Host "Shutting down servers..." -ForegroundColor Yellow
    
    if (!$backendJob.HasExited) {
        Stop-Process -Id $backendJob.Id -Force
        Write-Host "  ✓ Backend server stopped" -ForegroundColor Green
    }
    
    if (!$frontendJob.HasExited) {
        Stop-Process -Id $frontendJob.Id -Force
        Write-Host "  ✓ Frontend server stopped" -ForegroundColor Green
    }
    
    Write-Host ""
    Write-Host "Goodbye! 👋" -ForegroundColor Cyan
}
