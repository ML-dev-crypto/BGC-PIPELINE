# Docker-Based Testing for BGC-QDR

This guide explains how to run containerized tests for BGC-QDR, including comparisons with DeepBGC and antiSMASH.

## Prerequisites

1. **Docker Desktop** must be installed and running
   - Download from: https://www.docker.com/products/docker-desktop
   - After installation, start Docker Desktop
   - Wait for the whale icon to appear in your system tray (Windows) or menu bar (Mac)

2. **Verify Docker is running:**
   ```bash
   docker --version
   docker ps
   ```

## Quick Start

### Windows (PowerShell)

```powershell
# Run all tests
.\run_docker_tests.ps1 all

# Run specific tests
.\run_docker_tests.ps1 deepbgc    # DeepBGC comparison only
.\run_docker_tests.ps1 bgcqdr     # BGC-QDR pipeline tests only
.\run_docker_tests.ps1 antismash  # antiSMASH comparison (requires more resources)

# Clean up
.\run_docker_tests.ps1 clean
```

### Linux/Mac (Bash)

```bash
# Make script executable
chmod +x run_docker_tests.sh

# Run all tests
./run_docker_tests.sh all

# Run specific tests
./run_docker_tests.sh deepbgc
./run_docker_tests.sh bgcqdr
./run_docker_tests.sh antismash

# Clean up
./run_docker_tests.sh clean
```

## Manual Docker Commands

### Build and run DeepBGC comparison

```bash
# Build the DeepBGC container
docker-compose build deepbgc

# Run DeepBGC analysis
docker-compose up deepbgc

# Results will be in: benchmark_results/deepbgc_*/
```

### Build and run BGC-QDR tests

```bash
# Build the BGC-QDR test container
docker-compose build bgc-qdr-test

# Run tests
docker-compose up bgc-qdr-test
```

### Run antiSMASH comparison

```bash
# Note: antiSMASH requires significant resources (8GB+ RAM, 30+ min runtime)
docker-compose up antismash
```

## Python-Based Comparison (Without Docker)

If you have DeepBGC installed locally:

```bash
# Install DeepBGC
pip install deepbgc
deepbgc download

# Run comparison
python compare_with_deepbgc.py

# Or skip running DeepBGC and use existing results
python compare_with_deepbgc.py --skip-deepbgc
```

## Output Files

After running tests, you'll find:

```
benchmark_results/
├── deepbgc_GCA_000205625.1/     # DeepBGC results per genome
│   ├── *.bgc.tsv                # BGC predictions
│   └── *.full.gbk               # Annotated GenBank
├── deepbgc_GCA_000565115.1/
├── deepbgc_GCA_030153465.1/
├── deepbgc_comparison.json      # Comparison summary
├── benchmark_report.txt         # Full benchmark report
└── benchmark_results.json       # Machine-readable results
```

## Troubleshooting

### Docker not running

**Error:** `Cannot connect to the Docker daemon`

**Solution:**
1. Open Docker Desktop
2. Wait for it to fully start (whale icon appears)
3. Run `docker ps` to verify
4. Try your command again

### Out of memory

**Error:** Container killed or OOM

**Solution:**
1. Open Docker Desktop → Settings → Resources
2. Increase Memory to at least 8GB
3. Increase CPUs to 4+
4. Click "Apply & Restart"

### DeepBGC not found

**Error:** `deepbgc: command not found`

**Solution:**
```bash
# Inside container
pip install deepbgc
deepbgc download

# Or rebuild container
docker-compose build --no-cache deepbgc
```

### Permission denied (Linux)

**Error:** `Permission denied` when running scripts

**Solution:**
```bash
chmod +x run_docker_tests.sh
chmod +x compare_with_deepbgc.py
```

## Benchmark Metrics

The Docker tests will generate comprehensive benchmarks:

1. **Detection Comparison**
   - BGC-QDR vs DeepBGC vs antiSMASH
   - Number of BGCs detected
   - BGC class distribution
   - Runtime performance

2. **Novelty Analysis**
   - MiBIG 4.0 similarity (Jaccard distance)
   - Novel BGC families (GCFs)
   - Domain architecture comparison

3. **ML Model Performance**
   - VQC vs Random Forest vs XGBoost vs MLP
   - Cross-validation results
   - ROC-AUC, accuracy, precision, recall

4. **Biological Validation**
   - S. coelicolor A3(2) ground truth
   - Per-class precision/recall
   - antiSMASH concordance

## Next Steps

After running Docker tests:

1. **Review results:**
   ```bash
   cat benchmark_results/benchmark_report.txt
   ```

2. **Compare with paper claims:**
   - Check if detected BGC counts match
   - Verify novelty percentages
   - Validate ML model performance

3. **Generate figures:**
   ```bash
   python phase6_qml_training.py  # Generates training curves
   ```

4. **Update paper:**
   - Use benchmark_report.txt for Tables II-IV
   - Include DeepBGC comparison in Discussion
   - Add Docker testing to Methods section

## Citation

If you use these Docker tests in your research, please cite:

```bibtex
@article{bgcqdr2026,
  title={BGC-QDR: A Quantum Machine Learning Pipeline for Biosynthetic Gene Cluster Discovery and Drug-Potential Ranking},
  author={[Your Name]},
  journal={IEEE Transactions on Computational Biology and Bioinformatics},
  year={2026}
}
```

## Support

For issues or questions:
- Check the main README.md
- Review PROJECT_COMPLETE_DOCUMENTATION.md
- Open an issue on GitHub
