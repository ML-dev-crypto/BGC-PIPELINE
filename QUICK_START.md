# BGC-QDR Quick Start Guide

## New Features Overview

This guide covers the 9 new bug fixes and enhancements to the BGC-QDR pipeline.

---

## 1. Input Quality Control

### What It Does
Validates FASTA input files before running the pipeline, rejecting low-quality sequences.

### Usage

```bash
# Run QC on a FASTA file
python scripts/input_qc.py --input sample.fasta --output filtered.fasta --report qc_report.json

# QC will check:
# - Contig length (min 500bp)
# - N content (max 10%)
# - Sequence complexity (sliding window entropy)
```

### Output
```json
{
  "total_contigs": 100,
  "passed": 85,
  "failed": 15,
  "pass_rate": 85.0,
  "fail_rate": 15.0,
  "failure_reasons": {
    "too_short": 8,
    "high_n_content": 5,
    "low_complexity": 2
  }
}
```

### Pipeline Integration
The unified pipeline runner automatically runs QC first and aborts if >80% of contigs fail.

---

## 2. Novelty Caching

### What It Does
Caches novelty assessment results based on input FASTA content hash, avoiding redundant computation.

### How It Works
- Calculates MD5 hash of input FASTA content
- Checks cache for existing results
- Returns cached results instantly if found
- Computes and caches new results if not found

### API Response
```json
{
  "job_id": "job_1234567890",
  "input_hash": "a1b2c3d4e5f6...",
  "cached": true,
  "processing_time_seconds": 0.05,
  "novelty_results": { ... }
}
```

### Cache Location
- In-memory: `NOVELTY_CACHE` dictionary in backend_api.py
- Disk: `cache/` directory (persistent across restarts)

---

## 3. Domain Completeness Scoring

### What It Does
Scores each BGC candidate based on how many expected domains are present.

### Scoring
- **Complete** (>0.8): Has most/all expected domains
- **Partial** (0.5-0.8): Has some expected domains
- **Fragment** (<0.5): Missing many expected domains

### Usage

```bash
# Run classification with completeness scoring
python scripts/classify_bgcs.py --input orfs.faa --output bgcs.json --min-completeness 0.5

# Filter out fragments (keep only partial and complete)
python scripts/classify_bgcs.py --input orfs.faa --output bgcs.json --min-completeness 0.5
```

### Output
```json
{
  "bgc_id": "VBGC_0001",
  "bgc_class": "Type I PKS",
  "completeness_score": 0.85,
  "completeness_tag": "complete",
  "domains_found": ["KS", "AT", "ACP", "KR"],
  "domains_expected": ["KS", "AT", "ACP"]
}
```

---

## 4. Per-Contig Detection Logging

### What It Does
Logs detailed information about ORF calling and BGC detection per contig.

### Usage

```bash
# ORF calling with logging
python scripts/call_orfs.py --input sample.fasta --output orfs.faa --log orf_log.json

# BGC classification with logging
python scripts/classify_bgcs.py --input orfs.faa --output bgcs.json --log bgc_log.json
```

### Log Format
```json
{
  "input_file": "sample.fasta",
  "input_hash": "a1b2c3d4e5f6...",
  "timestamp": "2026-05-12T10:30:00",
  "total_contigs": 50,
  "orfs_per_contig": {
    "contig_1": 25,
    "contig_2": 18,
    "contig_3": 32
  },
  "bgcs_per_contig": {
    "contig_1": [
      {"bgc_id": "VBGC_0001", "class": "PKS", "score": 0.85}
    ]
  }
}
```

---

## 5. VQC Score Distribution

### What It Does
Provides statistical analysis of VQC scores across all candidates.

### Output
```json
{
  "score_distribution": {
    "min": 0.55,
    "max": 0.95,
    "mean": 0.75,
    "std": 0.12,
    "histogram_bins": [
      {"range": "0.5-0.6", "count": 2},
      {"range": "0.6-0.7", "count": 5},
      {"range": "0.7-0.8", "count": 8},
      {"range": "0.8-0.9", "count": 4},
      {"range": "0.9-1.0", "count": 1}
    ],
    "high_confidence_85plus": 5,
    "medium_confidence_70to85": 10,
    "low_confidence_below70": 5
  },
  "top_candidates": [
    {
      "bgc_id": "VBGC_0001",
      "score": 0.95,
      "percentile_rank": 95.0,
      "bgc_class": "Type I PKS"
    }
  ]
}
```

---

## 6. Sequence QC in Output

### What It Does
Includes comprehensive QC information in the final ranking output.

### Output
```json
{
  "sequence_qc": {
    "total_contigs_input": 100,
    "contigs_passed_qc": 85,
    "contigs_failed_qc": 15,
    "overall_input_quality": "good",
    "per_contig_stats": [
      {
        "id": "contig_1",
        "length": 5000,
        "gc_content": 45.2,
        "n_percentage": 0.5,
        "complexity_score": 3.8,
        "qc_status": "passed"
      }
    ]
  }
}
```

### Quality Levels
- **good**: <10% failure rate
- **medium**: 10-30% failure rate
- **poor**: >30% failure rate

---

## 7. API Cache-Busting Middleware

### What It Does
Caches API responses based on request body hash for instant repeated queries.

### How It Works
1. Computes SHA256 hash of POST request body
2. Checks `API_CACHE` for existing result
3. Returns cached result with `cached: true` flag
4. Computes fresh result if not cached

### Response
```json
{
  "job_id": "job_1234567890",
  "cached": true,
  "processing_time_seconds": 0.02,
  "results": { ... }
}
```

### Cache Decorator
```python
@cache_api_result
def rank_bgcs():
    # This endpoint is automatically cached
    pass
```

---

## 8. Frontend QC Warning Display

### What It Does
Displays visual warnings in the web interface for quality issues.

### Features

1. **Yellow Warning Banner**
   - Appears when `overall_input_quality` is "poor"
   - Shows QC statistics and failure reasons

2. **Orange Row Highlighting**
   - Highlights candidates with `requires_manual_review: true`
   - Indicates Unknown BGC classes needing expert review

3. **Score Distribution Sparkline**
   - Visual representation of score distribution
   - Shows histogram bins as mini bar chart

4. **Input Hash Display**
   - Shows input hash below results
   - Confirms different runs used different inputs

### Example
```
⚠️ Warning: Input quality is poor (65% of contigs failed QC)
   - 20 contigs too short
   - 10 contigs high N content
   - 5 contigs low complexity
```

---

## 9. Unified Pipeline Runner

### What It Does
Chains all pipeline steps in the correct order with validation and logging.

### Usage

```bash
# Dry-run (validate without executing)
python scripts/run_pipeline.py --input sample.fasta --output results/ --dry-run

# Full pipeline execution
python scripts/run_pipeline.py --input sample.fasta --output results/

# With custom parameters
python scripts/run_pipeline.py \
  --input sample.fasta \
  --output results/ \
  --min-completeness 0.6 \
  --score-threshold 0.75
```

### Pipeline Steps
1. **Input Validation** - Check file exists and is valid FASTA
2. **Input QC** - Quality control (aborts if >80% fail)
3. **ORF Calling** - Predict protein-coding genes
4. **BGC Classification** - Identify BGC candidates
5. **Sequence Reconstruction** - Reconstruct BGC sequences
6. **Novelty Assessment** - Compare to known BGCs
7. **VQC Ranking** - Rank candidates by quality score

### Output
```
============================================================
BGC-QDR Pipeline Runner
============================================================

Step 0: Input Validation
✅ Input file valid
   Path: sample.fasta
   Hash: a1b2c3d4e5f6
   Sequences: 100

Step 1: Input QC
✅ QC passed
   Passed: 85/100 (85.0%)
   Failed: 15/100 (15.0%)

Step 2: ORF Calling
✅ ORFs predicted: 2,450

Step 3: BGC Classification
✅ BGCs detected: 25

Step 4: Novelty Assessment
✅ Novel BGCs: 12

Step 5: VQC Ranking
✅ Top candidates: 10

============================================================
Pipeline Complete
============================================================
Total time: 45.2 seconds
Output: results/
```

---

## Running Tests

### Unit Tests
```bash
python test_bugfixes.py
```

### Integration Tests
```bash
python test_integration.py
```

### Expected Output
```
============================================================
Test Summary
============================================================
Passed: 9/9
Failed: 0/9

✅ All tests passed!
```

---

## Troubleshooting

### BioPython Import Error
```bash
# Install BioPython in the correct Python environment
python -m pip install biopython
```

### Cache Not Working
```bash
# Check cache directory exists
mkdir cache

# Clear cache if needed
rm -rf cache/*
```

### QC Aborting Pipeline
```bash
# Check QC report to see why contigs are failing
python scripts/input_qc.py --input sample.fasta --report qc_report.json

# Adjust thresholds if needed (edit input_qc.py)
MIN_LENGTH = 500  # Reduce if needed
MAX_N_PERCENT = 10.0  # Increase if needed
```

### Frontend Not Showing Warnings
```bash
# Check browser console for errors
# Verify sequence_qc is in API response
# Clear browser cache and reload
```

---

## Configuration

### Input QC Thresholds
Edit `scripts/input_qc.py`:
```python
MIN_LENGTH = 500  # Minimum contig length (bp)
MAX_N_PERCENT = 10.0  # Maximum N content (%)
MIN_ENTROPY = 1.5  # Minimum complexity (bits)
WINDOW_SIZE = 100  # Entropy window size (bp)
ABORT_THRESHOLD = 80  # Abort if >80% fail
```

### Completeness Thresholds
Edit `scripts/classify_bgcs.py`:
```python
# Completeness tags
if score > 0.8:
    tag = "complete"
elif score > 0.5:
    tag = "partial"
else:
    tag = "fragment"
```

### VQC Score Threshold
Edit `backend/backend_api.py`:
```python
score_threshold = 0.70  # Minimum score for ranking
```

---

## Best Practices

1. **Always run QC first** - Use the unified pipeline runner or run input_qc.py manually
2. **Check cache hits** - Monitor `cached: true` in API responses for performance
3. **Review Unknown classes** - Manually inspect candidates with `requires_manual_review: true`
4. **Monitor completeness** - Filter out fragments with `--min-completeness 0.5`
5. **Use logging** - Enable `--log` flags for debugging and auditing
6. **Validate inputs** - Use `--dry-run` to check inputs before full pipeline execution

---

## Support

For issues or questions:
1. Check `TEST_RESULTS.md` for test status
2. Review `BUGFIX_SUMMARY.md` for detailed implementation notes
3. Check `IMPLEMENTATION_COMPLETE.md` for architecture overview
4. Run tests to verify installation: `python test_bugfixes.py`

---

**Last Updated**: May 12, 2026  
**Version**: 1.0  
**Status**: Production Ready ✅
