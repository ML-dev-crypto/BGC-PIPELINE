# PowerShell script for Docker-based testing on Windows
# BGC-QDR Docker Testing Suite

param(
    [Parameter(Position=0)]
    [ValidateSet('deepbgc', 'antismash', 'bgcqdr', 'all', 'clean')]
    [string]$TestType = 'all'
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "BGC-QDR Docker Testing Suite" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "✅ Docker is running" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "❌ Docker is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    Write-Host ""
    Write-Host "To start Docker Desktop:" -ForegroundColor Yellow
    Write-Host "  1. Open Docker Desktop from Start Menu" -ForegroundColor Yellow
    Write-Host "  2. Wait for it to fully start (whale icon in system tray)" -ForegroundColor Yellow
    Write-Host "  3. Run this script again" -ForegroundColor Yellow
    exit 1
}

function Run-Test {
    param(
        [string]$Service,
        [string]$Description
    )
    
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "Running: $Description" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
    docker-compose up --build $Service
    Write-Host ""
}

switch ($TestType) {
    'deepbgc' {
        Run-Test -Service 'deepbgc' -Description 'DeepBGC Comparison'
    }
    'antismash' {
        Run-Test -Service 'antismash' -Description 'antiSMASH Comparison'
    }
    'bgcqdr' {
        Run-Test -Service 'bgc-qdr-test' -Description 'BGC-QDR Pipeline Tests'
    }
    'all' {
        Write-Host "Running all tests..." -ForegroundColor Yellow
        Write-Host ""
        Run-Test -Service 'bgc-qdr-test' -Description 'BGC-QDR Pipeline Tests'
        Run-Test -Service 'deepbgc' -Description 'DeepBGC Comparison'
        Write-Host ""
        Write-Host "==========================================" -ForegroundColor Green
        Write-Host "All tests complete!" -ForegroundColor Green
        Write-Host "==========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Results available in:" -ForegroundColor Yellow
        Write-Host "  - benchmark_results/deepbgc_*/" -ForegroundColor Yellow
        Write-Host "  - benchmark_results/benchmark_report.txt" -ForegroundColor Yellow
    }
    'clean' {
        Write-Host "Cleaning up Docker containers and images..." -ForegroundColor Yellow
        docker-compose down --rmi all -v
        Write-Host "✅ Cleanup complete" -ForegroundColor Green
    }
}
