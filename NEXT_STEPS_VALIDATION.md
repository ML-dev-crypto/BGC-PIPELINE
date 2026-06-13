# Next Steps: antiSMASH Validation

## Current Situation

✅ **All validation code is complete and ready**  
⏳ **antiSMASH REST API is unavailable (service issues)**  
🎯 **Need to complete validation using alternative method**

---

## Quick Start: Choose Your Path

### Path A: Manual Validation (30 minutes) ⭐ RECOMMENDED

**Best for**: Getting definitive results quickly

**Steps**:

1. **Submit to antiSMASH Web Interface**
   - Go to: https://antismash.secondarymetabolites.org/
   - Click "Upload" or "Submit"
   - Upload file: `validation/validation_test_BGC0000037.fasta`
   - Settings:
     * Taxon: **Bacteria**
     * Detection strictness: **Relaxed**
     * Check all extra features
   - Click "Submit"
   - **Wait 10-30 minutes** (grab coffee ☕)

2. **Download antiSMASH Results**
   - When job completes, click "Download"
   - Download the **JSON** format results
   - Save as: `antismash_results/BGC0000037_antismash.json`

3. **Run Our Pipeline**
   ```bash
   python scripts/run_pipeline.py \
     --input validation/validation_test_BGC0000037.fasta \
     --output-dir our_pipeline_results \
     --exclude-synthetic
   ```

4. **Compare Results**
   ```bash
   python scripts/antismash_comparison.py \
     --input validation/validation_test_BGC0000037.fasta \
     --predictions our_pipeline_results/ranking.json \
     --output final_validation_results.json
   ```

5. **Review Results**
   ```bash
   python -m json.tool final_validation_results.json
   ```

**Done!** You now have quantitative validation metrics.

---

### Path B: Quick Validation (15 minutes)

**Best for**: Fast initial validation using known results

**Steps**:

1. **Run Our Pipeline**
   ```bash
   python scripts/run_pipeline.py \
     --input validation/validation_test_BGC0000037.fasta \
     --output-dir quick_validation_results \
     --exclude-synthetic
   ```

2. **Check Results**
   ```bash
   python -m json.tool quick_validation_results/ranking.json
   ```

3. **Manual Comparison**
   
   **Known antiSMASH Results for BGC0000037**:
   - BGCs detected: **1**
   - Type: **Type I PKS (T1PKS)**
   - Product: **Erythromycin**
   - Completeness: **Complete**
   - Key domains: **KS, AT, DH, ER, KR, ACP**

   **Check Our Results**:
   - Did we detect **1 BGC**? ✅ / ❌
   - Did we classify as **Type I PKS**? ✅ / ❌
   - Did we mark as **complete**? ✅ / ❌
   - Did we find **PKS domains**? ✅ / ❌

4. **Calculate Metrics**
   - If all ✅: **100% agreement** → VALIDATED ✅
   - If any ❌: **Needs investigation** → Review detection rules

**Done!** You have initial validation results.

---

### Path C: Local antiSMASH (2 hours)

**Best for**: Long-term validation infrastructure

**Prerequisites**:
- Docker installed
- 10 GB free disk space
- 8 GB RAM

**Steps**:

1. **Install antiSMASH**
   ```bash
   docker pull antismash/standalone:latest
   ```

2. **Run antiSMASH Locally**
   ```bash
   docker run -v $(pwd):/data antismash/standalone:latest \
     /data/validation/validation_test_BGC0000037.fasta \
     --output-dir /data/local_antismash_results \
     --taxon bacteria
   ```

3. **Run Our Pipeline**
   ```bash
   python scripts/run_pipeline.py \
     --input validation/validation_test_BGC0000037.fasta \
     --output-dir our_pipeline_results \
     --exclude-synthetic
   ```

4. **Compare Results**
   ```bash
   python scripts/antismash_comparison.py \
     --input validation/validation_test_BGC0000037.fasta \
     --predictions our_pipeline_results/ranking.json \
     --output local_validation_results.json
   ```

**Done!** You have local validation capability for future tests.

---

## What Success Looks Like

### Expected Output

After running validation, you should see:

```json
{
  "status": "completed",
  "validation_summary": {
    "our_bgc_count": 1,
    "antismash_bgc_count": 1,
    "agreement_rate": 100.0,
    "validation_status": "excellent"
  },
  "comparison": {
    "our_count": 1,
    "antismash_count": 1,
    "type_comparison": {
      "our_types": {"Type I PKS": 1},
      "antismash_types": {"T1PKS": 1}
    }
  }
}
```

### Success Criteria

✅ **BGC Count Match**: Both detect 1 BGC  
✅ **Type Match**: Both identify as Type I PKS  
✅ **Completeness Match**: Both assess as complete  
✅ **Agreement Rate**: ≥ 90%  
✅ **Validation Status**: "excellent" or "good"

### If Something Doesn't Match

**Don't panic!** This is why we validate. Possible reasons:

1. **Different domain thresholds**: Adjust our E-value cutoffs
2. **Different classification rules**: Review our BGC_RULES
3. **Edge case handling**: May need special logic
4. **False positive**: Check if our detection is too sensitive
5. **False negative**: Check if our detection is too strict

**Action**: Document the discrepancy and investigate the cause.

---

## Troubleshooting

### Problem: Pipeline fails on validation file

**Solution**:
```bash
# Check Prodigal
biotools\prodigal.exe -v

# Check BioPython
python -c "from Bio import SeqIO; print('OK')"

# Run with debug
python scripts/run_pipeline.py \
  --input validation/validation_test_BGC0000037.fasta \
  --output-dir debug_output \
  --exclude-synthetic 2>&1 | tee debug.log
```

### Problem: antiSMASH web submission fails

**Solution**:
- Try during off-peak hours (evenings, weekends)
- Check service status: https://antismash.secondarymetabolites.org/
- Try again in a few hours
- Use Path B (known results) instead

### Problem: Comparison script fails

**Solution**:
```bash
# Verify files exist
dir our_pipeline_results\ranking.json
dir antismash_results\BGC0000037_antismash.json

# Check JSON format
python -m json.tool our_pipeline_results\ranking.json

# Check for errors
python scripts/antismash_comparison.py --help
```

### Problem: Results don't match

**Solution**:
1. Review both outputs carefully
2. Check if it's a naming difference (T1PKS vs Type I PKS)
3. Look at domain-level details
4. Document the discrepancy
5. Investigate the cause
6. Adjust detection rules if needed

---

## After Validation

### Document Results

Create a validation report:

```markdown
# BGC-QDR Validation Report

## Test Information
- Date: [TODAY'S DATE]
- Test File: validation_test_BGC0000037.fasta
- antiSMASH Version: 6.0 (or 7.0)
- Our Pipeline Version: 2.1.0

## Results

### antiSMASH
- BGCs: 1
- Type: T1PKS
- Completeness: Complete

### Our Pipeline
- BGCs: [YOUR RESULT]
- Type: [YOUR RESULT]
- Completeness: [YOUR RESULT]

## Metrics
- Sensitivity: [%]
- Precision: [%]
- F1 Score: [SCORE]
- Agreement: [%]

## Conclusion
[PASS/FAIL] - [EXPLANATION]
```

### Update Documentation

Update these files with actual results:
- `ANTISMASH_VALIDATION_RESULTS.md`
- `VALIDATION_STATUS.md`
- `README.md` (add validation badge)

### Share Results

- Commit validation results to git
- Share with team/collaborators
- Include in publications
- Add to project documentation

---

## Timeline

### Today (15-45 minutes)
- [ ] Choose validation path (A, B, or C)
- [ ] Run validation
- [ ] Review results
- [ ] Document findings

### This Week
- [ ] Complete any additional test cases
- [ ] Update all documentation
- [ ] Fix any issues found
- [ ] Re-validate if changes made

### This Month
- [ ] Expand validation to more BGC types
- [ ] Benchmark against other tools
- [ ] Prepare validation manuscript
- [ ] Submit for publication

---

## Quick Reference

### Key Files

**Validation Scripts**:
- `scripts/antismash_comparison.py` - Comparison module
- `test_antismash_validation.py` - Automated test
- `scripts/run_pipeline.py` - Our pipeline

**Test Data**:
- `validation/validation_test_BGC0000037.fasta` - Erythromycin
- `validation/validation_test_BGC0000001.fasta` - Actinorhodin

**Documentation**:
- `ANTISMASH_VALIDATION_GUIDE.md` - Detailed guide
- `ANTISMASH_VALIDATION_SUMMARY.md` - Overview
- `VALIDATION_STATUS.md` - Current status
- `NEXT_STEPS_VALIDATION.md` - This file

### Key Commands

**Run our pipeline**:
```bash
python scripts/run_pipeline.py --input [FILE] --output-dir [DIR] --exclude-synthetic
```

**Compare with antiSMASH**:
```bash
python scripts/antismash_comparison.py --input [FILE] --predictions [JSON] --output [JSON]
```

**View results**:
```bash
python -m json.tool [RESULTS.json]
```

---

## Need Help?

**Check these first**:
1. `ANTISMASH_VALIDATION_GUIDE.md` - Comprehensive guide
2. `VALIDATION_STATUS.md` - Current status and options
3. `BUGFIX_SUMMARY.md` - Recent changes
4. `README.md` - General documentation

**Still stuck?**
- Review error messages carefully
- Check file paths and permissions
- Verify all dependencies installed
- Try the simpler Path B first

---

## Bottom Line

🎯 **Goal**: Validate our pipeline against antiSMASH  
✅ **Status**: Ready to validate  
⏱️ **Time**: 15-45 minutes  
🚀 **Action**: Choose a path and start!

**Recommended**: Start with **Path A** (manual submission) for best results, or **Path B** (quick validation) if you need results immediately.

---

**Created**: May 16, 2026  
**Last Updated**: May 16, 2026  
**Priority**: HIGH  
**Status**: READY TO PROCEED

**👉 Choose your path above and start validating!**
