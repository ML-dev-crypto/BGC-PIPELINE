# BGC-QDR Full-Stack Integration Setup Script
# This script sets up the complete full-stack application

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   BGC-QDR Full-Stack Integration Setup                    ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Step 1: Create frontend directory structure
Write-Host "[1/6] Creating directory structure..." -ForegroundColor Yellow
$dirs = @("frontend", "frontend/assets", "uploads", "results")
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  ✓ Created $dir" -ForegroundColor Green
    } else {
        Write-Host "  ✓ $dir already exists" -ForegroundColor Green
    }
}

# Step 2: Copy HTML file
Write-Host ""
Write-Host "[2/6] Copying frontend HTML..." -ForegroundColor Yellow
if (Test-Path "New folder/index.html") {
    Get-Content "New folder/index.html" | Set-Content "frontend/index.html" -Encoding UTF8
    Write-Host "  ✓ index.html copied to frontend/" -ForegroundColor Green
} else {
    Write-Host "  ✗ Source file 'New folder/index.html' not found" -ForegroundColor Red
    Write-Host "  → Please manually copy index.html to frontend/" -ForegroundColor Yellow
}

# Step 3: Copy video file
Write-Host ""
Write-Host "[3/6] Copying video asset..." -ForegroundColor Yellow
if (Test-Path "New folder/DNA.mp4") {
    Copy-Item "New folder/DNA.mp4" "frontend/assets/DNA.mp4" -Force
    Write-Host "  ✓ DNA.mp4 copied to frontend/assets/" -ForegroundColor Green
} else {
    Write-Host "  ✗ Source file 'New folder/DNA.mp4' not found" -ForegroundColor Red
    Write-Host "  → Video background will not work without this file" -ForegroundColor Yellow
}

# Step 4: Update HTML to include JS and CSS
Write-Host ""
Write-Host "[4/6] Updating HTML with JS and CSS links..." -ForegroundColor Yellow
if (Test-Path "frontend/index.html") {
    $html = Get-Content "frontend/index.html" -Raw
    
    # Check if already updated
    if ($html -notmatch "app\.js" -and $html -notmatch "styles\.css") {
        # Add CSS link before </head>
        $html = $html -replace '</head>', '<link rel="stylesheet" href="styles.css">`n</head>'
        
        # Add JS link before </body>
        $html = $html -replace '</body>', '<script src="app.js"></script>`n</body>'
        
        # Update video path
        $html = $html -replace 'src="dna\.mp4"', 'src="assets/DNA.mp4"'
        
        Set-Content "frontend/index.html" $html -Encoding UTF8
        Write-Host "  ✓ HTML updated with JS and CSS links" -ForegroundColor Green
        Write-Host "  ✓ Video path updated" -ForegroundColor Green
    } else {
        Write-Host "  ✓ HTML already updated" -ForegroundColor Green
    }
} else {
    Write-Host "  ✗ frontend/index.html not found" -ForegroundColor Red
}

# Step 5: Verify files exist
Write-Host ""
Write-Host "[5/6] Verifying integration files..." -ForegroundColor Yellow
$files = @(
    "frontend/index.html",
    "frontend/app.js",
    "frontend/styles.css",
    "backend_api.py",
    "backend_requirements.txt"
)

$allGood = $true
foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $file missing" -ForegroundColor Red
        $allGood = $false
    }
}

# Step 6: Check Python dependencies
Write-Host ""
Write-Host "[6/6] Checking Python dependencies..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  ✓ Python: $pythonVersion" -ForegroundColor Green
    
    # Check if packages are installed
    $packages = @("flask", "flask_cors", "pandas")
    $missing = @()
    
    foreach ($pkg in $packages) {
        $result = python -c "import $pkg" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ $pkg installed" -ForegroundColor Green
        } else {
            Write-Host "  ✗ $pkg not installed" -ForegroundColor Red
            $missing += $pkg
        }
    }
    
    if ($missing.Count -gt 0) {
        Write-Host ""
        Write-Host "  Installing missing packages..." -ForegroundColor Yellow
        pip install -r backend_requirements.txt
    }
    
} catch {
    Write-Host "  ✗ Python not found" -ForegroundColor Red
    $allGood = $false
}

# Summary
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "║   ✓ Integration Setup Complete!                           ║" -ForegroundColor Green
} else {
    Write-Host "║   ⚠ Integration Setup Complete with Warnings              ║" -ForegroundColor Yellow
}
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

Write-Host "Next Steps:" -ForegroundColor White
Write-Host ""
Write-Host "1. Start the backend server:" -ForegroundColor White
Write-Host "   python backend_api.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "2. Start the frontend server (in a new terminal):" -ForegroundColor White
Write-Host "   cd frontend" -ForegroundColor Cyan
Write-Host "   python -m http.server 3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "3. Open your browser:" -ForegroundColor White
Write-Host "   http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Or use the automated startup script:" -ForegroundColor White
Write-Host "   .\start_fullstack.ps1" -ForegroundColor Cyan
Write-Host ""
Write-Host "Documentation:" -ForegroundColor White
Write-Host "  - FULLSTACK_README.md - Complete setup guide" -ForegroundColor Gray
Write-Host "  - FULLSTACK_INTEGRATION.md - Technical details" -ForegroundColor Gray
Write-Host "  - frontend/README.md - Frontend-specific instructions" -ForegroundColor Gray
Write-Host ""
