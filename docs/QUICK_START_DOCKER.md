# Quick Start: Docker Testing for BGC-QDR

## 🚀 5-Minute Setup

### Step 1: Start Docker Desktop

1. Open **Docker Desktop** from your Start Menu
2. Wait for the whale icon to appear in your system tray
3. Verify it's running:
   ```powershell
   docker ps
   ```
   You should see a table (even if empty) - not an error

### Step 2: Run Tests

**Option A: Run everything (recommended for first time)**
```powershell
.\run_docker_tests.ps1 all
```

**Option B: Run DeepBGC comparison only (faster)**
```powershell
.\run_docker_tests.ps1 deepbgc
```

**Option C: Run BGC-QDR tests only**
```powershell
.\run_docker_tests.ps1 bgcqdr
```

### Step 3: View Results

```powershell
# View benchmark report
cat benchmark_results/benchmark_report.txt

# View DeepBGC comparison
cat benchmark_results/deepbgc_comparison.json
```

## 📊 What Gets Tested

### 1. BGC Detection (Phase 1-2)
- ✅ Sliding window CNN detection
- ✅ PyHMMER domain annotation
- ✅ 68 BGC regions from 588 windows

### 2. Virtual BGC Reconstruction (Phase 3)
- ✅ Graph-based fragment merging
- ✅ 14 virtual BGCs from 68 fragments
- ✅ Domain architecture validation

### 3. Novelty Assessment (Phase 4-5)
- ✅ MiBIG 4.0 Jaccard similarity
- ✅ 12 Gene Cluster Families (GCFs)
- ✅ 10 novel singletons identified

### 4. Quantum ML Ranking (Phase 6)
- ✅ VQC training (6 qubits, 54 params)
- ✅ Classical baselines (RF, XGBoost, MLP)
- ✅ Cross-validation (5-fold classical, 3-fold VQC)
- ✅ Drug-potential scoring

### 5. External Tool Comparison
- ✅ DeepBGC detection comparison
- ✅ antiSMASH concordance (optional)
- ✅ Runtime benchmarks

## 📈 Expected Results

### BGC Detection
```
BGC-QDR:   68 regions detected
DeepBGC:   ~50-80 regions (varies by threshold)
antiSMASH: ~70-90 regions (if run)
```

### ML Performance (from paper)
```
Model          Accuracy    ROC-AUC
─────────────────────────────────
VQC            0.804±0.031  0.768±0.034
Random Forest  0.782±0.018  0.879±0.014
XGBoost        0.803        0.892
MLP            0.851±0.021  0.875±0.017
```

### Novelty
```
Virtual BGCs:     14
Novel (Jaccard<0.3): 11 (78.6%)
Novel GCFs:       10/12 (83.3%)
```

## 🐛 Troubleshooting

### "Docker is not running"
```powershell
# Start Docker Desktop, then verify:
docker info
```

### "Cannot find file"
```powershell
# Make sure you're in the project root:
cd path\to\BGC-QDR
ls  # Should see: phase6_qml_training.py, docker-compose.yml, etc.
```

### "Out of memory"
1. Docker Desktop → Settings → Resources
2. Set Memory to 8GB+
3. Set CPUs to 4+
4. Click "Apply & Restart"

### "DeepBGC takes too long"
```powershell
# Skip DeepBGC and just run BGC-QDR tests:
.\run_docker_tests.ps1 bgcqdr

# Or use existing results:
python compare_with_deepbgc.py --skip-deepbgc
```

## 🎯 Next Steps

### For Paper Reviewers
1. Run `.\run_docker_tests.ps1 all`
2. Check `benchmark_results/benchmark_report.txt`
3. Verify metrics match paper Tables II-IV
4. Review `VALIDATION_REPORT.txt` for S. coelicolor validation

### For Developers
1. Run tests: `.\run_docker_tests.ps1 bgcqdr`
2. Modify code
3. Re-run tests to verify changes
4. Check `benchmark_results/` for updated metrics

### For Reproducibility
1. Run full pipeline: `.\run_docker_tests.ps1 all`
2. Save all outputs in `benchmark_results/`
3. Include in supplementary materials
4. Document Docker versions used

## 📚 Full Documentation

- **DOCKER_TESTING.md** - Complete Docker testing guide
- **PROJECT_COMPLETE_DOCUMENTATION.md** - Full pipeline documentation
- **BGC-QDR-Paper-v3.docx** - Research paper
- **VALIDATION_REPORT.txt** - Biological validation results

## ⏱️ Estimated Runtimes

| Test | Time | Resources |
|------|------|-----------|
| BGC-QDR tests | 2-5 min | 4GB RAM, 2 CPUs |
| DeepBGC comparison | 10-20 min | 8GB RAM, 4 CPUs |
| antiSMASH comparison | 30-60 min | 16GB RAM, 8 CPUs |
| Full suite | 15-30 min | 8GB RAM, 4 CPUs |

## 🎓 Understanding the Results

### Benchmark Report Structure
```
1. BGC Detection Comparison
   → BGC-QDR vs DeepBGC vs antiSMASH counts

2. Novel BGC Discovery
   → MiBIG similarity, GCF clustering

3. ML Model Comparison
   → VQC vs classical models (CV results)

4. Biological Validation
   → S. coelicolor ground truth

5. Sanity Checks
   → Cluster length, domain counts
```

### Key Metrics to Check
- ✅ VQC accuracy ≥ 0.80 (competitive with classical)
- ✅ Novel BGCs ≥ 70% (high novelty rate)
- ✅ S. coelicolor accuracy ≥ 60% (biological validation)
- ✅ Runtime < 5 min for full pipeline

## 💡 Tips

1. **First run takes longer** (Docker downloads images)
2. **Subsequent runs are faster** (cached layers)
3. **Use `clean` to free disk space** after testing
4. **Check Docker Desktop logs** if containers fail
5. **Increase resources** if you see OOM errors

## 🔗 Quick Links

- [Docker Desktop Download](https://www.docker.com/products/docker-desktop)
- [BGC-QDR GitHub](https://github.com/yourusername/BGC-QDR)
- [MiBIG Database](https://mibig.secondarymetabolites.org/)
- [PennyLane Docs](https://pennylane.ai/)

---

**Ready to start?**

```powershell
# Start Docker Desktop, then:
.\run_docker_tests.ps1 all
```

That's it! Results will be in `benchmark_results/` 🎉
