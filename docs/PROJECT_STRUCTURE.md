# BGC-QDR Project Structure

## Directory Organization

```
BGC-QDR/
├── frontend/                    # Web interface
│   ├── index.html              # Main web page
│   ├── app.js                  # Frontend JavaScript
│   ├── styles.css              # Styling
│   └── assets/                 # Static assets (DNA.mp4)
│
├── backend/                     # Backend API (to be organized)
│   └── backend_api.py          # Flask REST API
│
├── pipeline/                    # Core BGC detection pipeline
│   ├── phase1_model.py         # Phase 1: Initial detection
│   ├── phase3_architecture.py  # Phase 3: Architecture analysis
│   ├── phase4_metabolite.py    # Phase 4: Metabolite prediction
│   ├── phase5_bigscape.py      # Phase 5: BiG-SCAPE analysis
│   ├── phase6_qml_training.py  # Phase 6: QML training
│   ├── preprocess_phase1.py    # Preprocessing
│   ├── train_phase1.py         # Training scripts
│   ├── train_final_fix.py      # Training fixes
│   └── retrain_recall.py       # Retraining utilities
│
├── scripts/                     # Utility scripts
│   ├── call_orfs.py            # ORF calling
│   ├── classify_bgcs.py        # BGC classification
│   ├── extract_regions.py      # Region extraction
│   ├── parse_domains.py        # Domain parsing
│   ├── scan_genome.py          # Genome scanning
│   ├── create_website.py       # Website generation
│   └── deployment_calibration.py # Deployment calibration
│
├── stage2/                      # Stage 2 pipeline variants
│   ├── stage2_pipeline.py
│   ├── stage2_production.py
│   ├── stage2_pyhmmer_fixed.py
│   ├── stage2_simple.py
│   ├── stage2_simplified.py
│   ├── stage2_windows_production.py
│   └── stage2_windows_setup.py
│
├── validation/                  # Validation scripts
│   ├── validate_bgc_pipeline.py
│   ├── validate_sco_genome.py
│   ├── validate_signatures.py
│   └── validation_test_*.fasta
│
├── benchmarking/               # Benchmarking and comparison
│   ├── benchmark_bgcqdr.py
│   └── compare_with_deepbgc.py
│
├── docker/                      # Docker configuration
│   ├── Dockerfile.bgcqdr
│   ├── Dockerfile.deepbgc
│   ├── docker-compose.yml
│   ├── run_docker_tests.ps1
│   └── run_docker_tests.sh
│
├── setup/                       # Setup scripts
│   ├── setup_integration.bat
│   ├── setup_integration.ps1
│   ├── setup_stage2.sh
│   ├── setup_stage2_wsl.py
│   ├── verify_setup.bat
│   └── wsl_setup_guide.py
│
├── tests/                       # Test scripts
│   ├── test_backend.py
│   ├── test_stage2_wsl.py
│   └── test_threshold.py
│
├── docs/                        # Documentation
│   ├── README.md               # Main documentation
│   ├── START_HERE.md           # Quick start guide
│   ├── ITERATION_COMPLETE.md   # Iteration summary
│   ├── PIPELINE_SUMMARY.md     # Pipeline explanation
│   ├── CURRENT_STATUS.md       # Current status
│   ├── DOCKER_SETUP_COMPLETE.md
│   ├── DOCKER_TESTING.md
│   ├── QUICK_START_DOCKER.md
│   ├── README_DOCKER.md
│   └── FULLSTACK_README.md
│
├── data/                        # Data files (gitignored)
│   ├── edna_fasta/
│   ├── preprocessed_data/
│   └── *.fasta.gz
│
├── results/                     # Results (gitignored)
│   ├── benchmark_results/
│   ├── phase*_results/
│   ├── stage2_*_results/
│   └── validation_sco/
│
├── tools/                       # External tools
│   └── biotools/
│
├── .gitignore                   # Git ignore rules
├── backend_requirements.txt     # Python dependencies
└── start_fullstack.ps1         # Startup script
```

## File Categories

### Essential Files (Must Commit)
- All Python pipeline scripts
- Docker configuration files
- Documentation files
- Frontend files
- Backend API
- Setup scripts
- Requirements files

### Excluded Files (In .gitignore)
- Large data files (*.fasta.gz, *.tar.gz)
- Results directories
- Python cache (__pycache__)
- Virtual environments (.venv)
- IDE settings (.vscode)
- Temporary files

## Next Steps

1. Create organized directory structure
2. Move files to appropriate directories
3. Update import paths if needed
4. Commit organized structure
