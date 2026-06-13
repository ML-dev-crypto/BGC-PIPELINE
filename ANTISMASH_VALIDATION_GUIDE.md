# antiSMASH Validation Guide for BGC-QDR Pipeline

## Overview

This document provides a comprehensive guide for validating the BGC-QDR pipeline against antiSMASH, the gold standard for biosynthetic gene cluster detection.

## Validation Methodology

### Test Dataset

**File**: `validation/validation_test_BGC0000037.fasta`
- **Source**: MIBiG database (Minimum Information about a Biosynthetic Gene cluster)
- **BGC ID**: BGC0000037
- **Product**: Erythromycin
- **Organism**: *Saccharopolyspora erythraea*
- **BGC Type**: Type I Polyketide Synthase (T1PKS)
- **Size**: ~50 kb
- **Genes**: 12 biosynthetic genes
- **Status**: Experimentally characterized, complete cluster

### Known antiSMASH Results for BGC0000037

Based on MIBiG database and antiSMASH documentation:

```json
{
  "regions": 1,
  "bgc_type": "T1PKS",
  "product": "erythromycin",
  "completeness": "complete",
  "genes": 12,
  "key_domains": [
    "PKS_KS (Ketosynthase)",
    "PKS_AT (Acyltransferase)",
    "PKS_DH (Dehydratase)",
    "PKS_ER (Enoylreductase)",
    "PKS_KR (Ketoreductase)",
    "ACP (Acyl Carrier Protein)"
  ],
  "confidence": "high"
}
```

## How to Run Validation

### Option 1: Using antiSMASH Web Interface (Recommended)

1. **Navigate to antiSMASH**:
   ```
   https://antismash.secondarymetabolites.org/
   ```

2. **Upload Test File**:
   - Upload: `validation/validation_test_BGC0000037.fasta`
   - Taxon: Bacteria
   - Detection strictness: Relaxed
   - Enable all extra features

3. **Wait for Results** (10-30 minutes)

4. **Download Results**:
   - Download JSON output
   - Save to: `antismash_results/BGC0000037_antismash.json`

5. **Run Our Pipeline**:
   ```bash
   python scripts/run_pipeline.py \
     --input validation/validation_test_BGC0000037.fasta \
     --output-dir our_results \
     --exclude-synthetic
   ```

6. **Compare Results**:
   ```bash
   python scripts/antismash_comparison.py \
     --input validation/validation_test_BGC0000037.fasta \
     --predictions our_results/ranking.json \
     --output comparison_results.json
   ```

### Option 2: Using antiSMASH REST API

```bash
# Submit job
python test_antismash_validation.py
```

**Note**: The REST API may experience downtime or rate limiting. If submission fails, use Option 1 (web interface).

### Option 3: Using antiSMASH Standalone (Local Installation)

If you have antiSMASH installed locally:

```bash
# Run antiSMASH locally
antismash \
  --taxon bacteria \
  --output-dir antismash_local_results \
  validation/validation_test_BGC0000037.fasta

# Run our pipeline
python scripts/run_pipeline.py \
  --input validation/validation_test_BGC0000037.fasta \
  --output-dir our_results \
  --exclude-synthetic

# Compare
python scripts/antismash_comparison.py \
  --input validation/validation_test_BGC0000037.fasta \
  --predictions our_results/ranking.json \
  --output comparison_results.json
```

## Expected Validation Results

### Perfect Match Scenario

If our pipeline is working correctly, we should detect:

```json
{
  "our_pipeline": {
    "bgc_count": 1,
    "bgc_type": "Type I PKS",
    "completeness": "complete",
    "score": ">0.80",
    "domains_detected": ["PKS_KS", "PKS_AT", "ACP", "PKS_KR", "PKS_DH", "PKS_ER"]
  },
  "antismash": {
    "bgc_count": 1,
    "bgc_type": "T1PKS",
    "completeness": "complete",
    "confidence": "high"
  },
  "agreement": {
    "count_match": true,
    "type_match": true,
    "completeness_match": true,
    "validation_status": "EXCELLENT"
  }
}
```

### Validation Metrics

**Sensitivity (Recall)**:
```
Sensitivity = True Positives / (True Positives + False Negatives)
Expected: 100% (we detect the BGC that antiSMASH detects)
```

**Precision**:
```
Precision = True Positives / (True Positives + False Positives)
Expected: 100% (we don't detect false BGCs)
```

**F1 Score**:
```
F1 = 2 × (Precision × Sensitivity) / (Precision + Sensitivity)
Expected: 1.0 (perfect score)
```

## Troubleshooting

### antiSMASH API Issues

**Problem**: Job submission fails or times out

**Solutions**:
1. Check antiSMASH service status: https://antismash.secondarymetabolites.org/
2. Try during off-peak hours (avoid Monday mornings, conference times)
3. Use the web interface instead of REST API
4. Install antiSMASH locally for offline validation

### Our Pipeline Issues

**Problem**: Pipeline fails on validation file

**Solutions**:
1. Check Prodigal installation:
   ```bash
   biotools/prodigal.exe -v
   ```

2. Check Python dependencies:
   ```bash
   python -c "from Bio import SeqIO; print('BioPython OK')"
   ```

3. Run with verbose logging:
   ```bash
   python scripts/run_pipeline.py \
     --input validation/validation_test_BGC0000037.fasta \
     --output-dir debug_output \
     --exclude-synthetic 2>&1 | tee pipeline_debug.log
   ```

### Comparison Script Issues

**Problem**: Comparison fails

**Solutions**:
1. Verify both result files exist:
   ```bash
   dir our_results\ranking.json
   dir antismash_results\BGC0000037_antismash.json
   ```

2. Check JSON format:
   ```bash
   python -m json.tool our_results\ranking.json
   ```

## Additional Test Cases

### Test Case 2: NRPS Cluster

**File**: `validation/validation_test_BGC0000001.fasta`
- **Product**: Actinorhodin
- **Type**: Type II PKS
- **Expected**: 1 BGC, Type II PKS

### Test Case 3: Environmental Sample

**File**: `uploads/job_1778159964.fasta`
- **Content**: Mixed environmental + synthetic sequences
- **Expected**: 3 environmental BGCs (with --exclude-synthetic)
- **Note**: Tests synthetic sequence filtering

## Validation Checklist

- [ ] antiSMASH results obtained for BGC0000037
- [ ] Our pipeline run successfully on BGC0000037
- [ ] BGC count matches (both detect 1 BGC)
- [ ] BGC type matches (both identify Type I PKS)
- [ ] Completeness assessment matches
- [ ] Domain detection overlaps significantly
- [ ] Sensitivity ≥ 90%
- [ ] Precision ≥ 90%
- [ ] F1 Score ≥ 0.90
- [ ] Results documented in validation report

## Validation Report Template

After running validation, create a report:

```markdown
# BGC-QDR Validation Report

## Test Information
- Date: [DATE]
- Test File: validation_test_BGC0000037.fasta
- antiSMASH Version: [VERSION]
- Our Pipeline Version: [VERSION]

## Results

### antiSMASH Results
- BGCs Detected: [COUNT]
- Types: [TYPES]
- Confidence: [CONFIDENCE]

### Our Pipeline Results
- BGCs Detected: [COUNT]
- Types: [TYPES]
- Scores: [SCORES]

### Comparison
- Sensitivity: [%]
- Precision: [%]
- F1 Score: [SCORE]
- Agreement Rate: [%]

### Validation Status
[PASS/FAIL] - [EXPLANATION]

## Recommendations
[ANY IMPROVEMENTS NEEDED]
```

## References

1. **antiSMASH**: Blin, K., et al. (2021). antiSMASH 6.0: improving cluster detection and comparison capabilities. *Nucleic Acids Research*, 49(W1), W29-W35.

2. **MIBiG**: Kautsar, S. A., et al. (2020). MIBiG 2.0: a repository for biosynthetic gene clusters of known function. *Nucleic Acids Research*, 48(D1), D454-D458.

3. **Erythromycin BGC**: Staunton, J., & Weissman, K. J. (2001). Polyketide biosynthesis: a millennium review. *Natural Product Reports*, 18(4), 380-416.

## Contact & Support

For validation questions or issues:
- Check pipeline documentation: `README.md`
- Review bug fix summary: `BUGFIX_SUMMARY.md`
- Check implementation status: `COMPLETION_SUMMARY.md`

---

**Last Updated**: May 16, 2026
**Status**: Ready for validation
**Priority**: High - Required for publication
