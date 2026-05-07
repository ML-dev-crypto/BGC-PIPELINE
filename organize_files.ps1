# BGC-QDR File Organization Script

Write-Host "Creating directory structure..." -ForegroundColor Green

# Create directories
$dirs = @('pipeline', 'scripts', 'stage2', 'validation', 'benchmarking', 'docker', 'setup', 'tests', 'docs', 'backend')
foreach ($dir in $dirs) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "Created: $dir" -ForegroundColor Cyan
    }
}

Write-Host "`nMoving files to organized structure..." -ForegroundColor Green

# Move pipeline files
$pipelineFiles = @(
    'phase1_model.py',
    'phase3_architecture.py',
    'phase4_metabolite.py',
    'phase5_bigscape.py',
    'phase6_qml_training.py',
    'preprocess_phase1.py',
    'train_phase1.py',
    'train_final_fix.py',
    'retrain_recall.py'
)
foreach ($file in $pipelineFiles) {
    if (Test-Path $file) {
        Move-Item $file pipeline/ -Force
        Write-Host "Moved: $file -> pipeline/" -ForegroundColor Yellow
    }
}

# Move script files
$scriptFiles = @(
    'call_orfs.py',
    'classify_bgcs.py',
    'extract_regions.py',
    'parse_domains.py',
    'scan_genome.py',
    'create_website.py',
    'deployment_calibration.py'
)
foreach ($file in $scriptFiles) {
    if (Test-Path $file) {
        Move-Item $file scripts/ -Force
        Write-Host "Moved: $file -> scripts/" -ForegroundColor Yellow
    }
}

# Move stage2 files
$stage2Files = @(
    'stage2_pipeline.py',
    'stage2_production.py',
    'stage2_pyhmmer_fixed.py',
    'stage2_simple.py',
    'stage2_simplified.py',
    'stage2_windows_production.py',
    'stage2_windows_setup.py',
    'run_stage2_production.sh'
)
foreach ($file in $stage2Files) {
    if (Test-Path $file) {
        Move-Item $file stage2/ -Force
        Write-Host "Moved: $file -> stage2/" -ForegroundColor Yellow
    }
}

# Move validation files
$validationFiles = @(
    'validate_bgc_pipeline.py',
    'validate_sco_genome.py',
    'validate_signatures.py',
    'validation_test_BGC0000001.fasta',
    'validation_test_BGC0000037.fasta'
)
foreach ($file in $validationFiles) {
    if (Test-Path $file) {
        Move-Item $file validation/ -Force
        Write-Host "Moved: $file -> validation/" -ForegroundColor Yellow
    }
}

# Move benchmarking files
$benchmarkFiles = @(
    'benchmark_bgcqdr.py',
    'compare_with_deepbgc.py'
)
foreach ($file in $benchmarkFiles) {
    if (Test-Path $file) {
        Move-Item $file benchmarking/ -Force
        Write-Host "Moved: $file -> benchmarking/" -ForegroundColor Yellow
    }
}

# Move Docker files
$dockerFiles = @(
    'Dockerfile.bgcqdr',
    'Dockerfile.deepbgc',
    'docker-compose.yml',
    'run_docker_tests.ps1',
    'run_docker_tests.sh'
)
foreach ($file in $dockerFiles) {
    if (Test-Path $file) {
        Move-Item $file docker/ -Force
        Write-Host "Moved: $file -> docker/" -ForegroundColor Yellow
    }
}

# Move setup files
$setupFiles = @(
    'setup_integration.bat',
    'setup_integration.ps1',
    'setup_stage2.sh',
    'setup_stage2_wsl.py',
    'verify_setup.bat',
    'wsl_setup_guide.py'
)
foreach ($file in $setupFiles) {
    if (Test-Path $file) {
        Move-Item $file setup/ -Force
        Write-Host "Moved: $file -> setup/" -ForegroundColor Yellow
    }
}

# Move test files
$testFiles = @(
    'test_backend.py',
    'test_stage2_wsl.py',
    'test_threshold.py',
    'test_integration.py'
)
foreach ($file in $testFiles) {
    if (Test-Path $file) {
        Move-Item $file tests/ -Force
        Write-Host "Moved: $file -> tests/" -ForegroundColor Yellow
    }
}

# Move documentation files
$docFiles = @(
    'START_HERE.md',
    'ITERATION_COMPLETE.md',
    'PIPELINE_SUMMARY.md',
    'CURRENT_STATUS.md',
    'DOCKER_SETUP_COMPLETE.md',
    'DOCKER_TESTING.md',
    'QUICK_START_DOCKER.md',
    'README_DOCKER.md',
    'FULLSTACK_README.md',
    'PROJECT_STRUCTURE.md'
)
foreach ($file in $docFiles) {
    if (Test-Path $file) {
        Move-Item $file docs/ -Force
        Write-Host "Moved: $file -> docs/" -ForegroundColor Yellow
    }
}

# Move backend files
$backendFiles = @(
    'backend_api.py',
    'backend_requirements.txt'
)
foreach ($file in $backendFiles) {
    if (Test-Path $file) {
        Move-Item $file backend/ -Force
        Write-Host "Moved: $file -> backend/" -ForegroundColor Yellow
    }
}

Write-Host "`nFile organization complete!" -ForegroundColor Green
Write-Host "Run 'git status' to see the changes." -ForegroundColor Cyan
