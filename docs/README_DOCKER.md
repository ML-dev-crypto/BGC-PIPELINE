# BGC-QDR: Docker Testing Guide

## 🎯 Quick Start (5 Minutes)

### Prerequisites
- Docker Desktop installed and running
- 8GB RAM available
- 20GB disk space

### Run Tests

```powershell
# Windows PowerShell
.\run_docker_tests.ps1 deepbgc

# Linux/Mac
./run_docker_tests.sh deepbgc
```

## 📊 What This Does

Runs DeepBGC on the same eDNA samples as BGC-QDR and generates a comparison report showing:

- BGC detection counts (BGC-QDR: 68, DeepBGC: ?)
- BGC class distribution comparison
- Runtime benchmarks
- Genomic overlap analysis

## 📁 Output Files

```
benchmark_results/
├── deepbgc_GCA_000205625.1/     # DeepBGC results per genome
├── deepbgc_GCA_000565115.1/
├── deepbgc_GCA_030153465.1/
├── deepbgc_comparison.json      # Comparison summary
└── benchmark_report.txt         # Updated with DeepBGC data
```

## 🔍 Current Results

### BGC-QDR Performance (Already Complete)
```
Detection:     68 BGC regions → 14 virtual BGCs
Novelty:       14/14 novel (100%, Jaccard<0.3)
GCF Families:  12 total (10 novel singletons)
Validation:    11/17 correct on S. coelicolor (64.7%)
```

### ML Performance (Cross-Validation)
```
Model          Accuracy      ROC-AUC
─────────────────────────────────────
VQC            0.579±0.043   0.712±0.026
Random Forest  0.764±0.014   0.870±0.027
XGBoost        0.778±0.009   0.879±0.023
MLP            0.859±0.009   0.855±0.011
```

## 🐛 Troubleshooting

### Docker not running
```powershell
# Start Docker Desktop
# Wait for whale icon in system tray
docker ps  # Should show table, not error
```

### Out of memory
```
Docker Desktop → Settings → Resources
Set Memory to 8GB+, CPUs to 4+
```

### Script won't run
```powershell
# Windows: Run as Administrator
# Linux/Mac: chmod +x run_docker_tests.sh
```

## 📚 Full Documentation

- **QUICK_START_DOCKER.md** - 5-minute guide
- **DOCKER_TESTING.md** - Complete reference
- **CURRENT_STATUS.md** - Project status
- **PROJECT_COMPLETE_DOCUMENTATION.md** - Pipeline docs

## 🎓 For Paper Reviewers

To reproduce results:

1. Start Docker Desktop
2. Run: `.\run_docker_tests.ps1 all`
3. Check: `benchmark_results/benchmark_report.txt`
4. Compare with paper Tables II-IV

## 💻 System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 4GB | 8GB |
| CPU | 2 cores | 4 cores |
| Disk | 10GB | 20GB |
| Docker | 20.10+ | Latest |

## 🚀 Commands Reference

```powershell
# DeepBGC comparison only (10-20 min)
.\run_docker_tests.ps1 deepbgc

# BGC-QDR tests only (2-5 min)
.\run_docker_tests.ps1 bgcqdr

# Full suite (15-30 min)
.\run_docker_tests.ps1 all

# Clean up
.\run_docker_tests.ps1 clean
```

## 📞 Support

Issues? Check:
1. DOCKER_TESTING.md (troubleshooting)
2. Docker Desktop logs
3. System resources (RAM/CPU/disk)

---

**Ready?** Start Docker Desktop, then run:
```powershell
.\run_docker_tests.ps1 deepbgc
```
