# Priority Fixes Implementation Guide

## Status: IN PROGRESS

This document tracks the implementation of critical bug fixes and enhancements based on the audit findings.

---

## 🔴 Priority 1: Critical Bug Fixes

### ✅ Task 1: Input QC Module - COMPLETED
**File:** `scripts/sequence_qc.py`

**Implemented:**
- ✅ Rejects contigs <500bp
- ✅ Rejects contigs with >10% N bases  
- ✅ Flags low-complexity sequences using entropy check
- ✅ Outputs comprehensive QC report dict
- ✅ **NEW:** Raises exception if >80% of contigs fail
- ✅ **NEW:** Added `overall_input_quality` field ("good"/"medium"/"poor")
- ✅ **NEW:** Added `fail_rate` to report

**Usage:**
```python
from sequence_qc import SequenceQC

qc = SequenceQC("sample.fasta")
try:
    report, passed_sequences = qc.run_qc()
    print(f"Quality: {report['overall_input_quality']}")
    print(f"Passed: {report['passed_sequences']}/{report['total_sequences']}")
except ValueError as e:
    print(f"QC FAILED: {e}")
    # Abort pipeline
```

---

### ✅ Task 2: Fix Novelty Caching Bug - COMPLETED
**File:** `backend/backend_api.py`

**Implemented:**
- ✅ Added MD5 hash calculation for FASTA files
- ✅ Created cache infrastructure (`cache/` folder)
- ✅ Added `get_cached_result()` and `save_cached_result()` functions
- ✅ Cache key based on file content hash
- ✅ Returns `cached: true` flag when using cached results
- ✅ `input_hash` included in all JSON outputs

**Functions Added:**
```python
def calculate_file_hash(file_path: Path) -> str:
    """Calculate MD5 hash of file content for cache key."""
    
def get_cached_result(cache_key: str, cache_type: str):
    """Get cached result if available."""
    
def save_cached_result(cache_key: str, cache_type: str, result: dict):
    """Save result to cache."""
```

**Next Step:** Update `/api/novelty` endpoint to use caching

---

### 🔄 Task 3: Domain Completeness Scoring - TODO
**File:** `scripts/classify_bgcs.py`

**Requirements:**
- Add `completeness_score` field (0.0-1.0) per BGC candidate
- Calculate based on: found_domains / required_domains
- Tag candidates as: complete (>0.8), partial (0.5-0.8), fragment (<0.5)
- Add `--min-completeness` CLI flag (default 0.5)
- Include completeness in output CSV and JSON

**Implementation Plan:**
```python
def calculate_completeness(domain_types: Set[str], rules: Dict) -> float:
    """
    Calculate domain completeness score.
    
    Returns:
        float: 0.0-1.0 score
    """
    required = set(rules['required'])
    recommended = set(rules['highly_recommended'])
    
    if not required and not recommended:
        return 1.0
    
    # Score based on required domains
    required_score = len(required & domain_types) / len(required) if required else 1.0
    
    # Bonus for recommended domains
    recommended_score = len(recommended & domain_types) / len(recommended) if recommended else 0.0
    
    # Weighted: 80% required, 20% recommended
    completeness = (required_score * 0.8) + (recommended_score * 0.2)
    
    return min(1.0, completeness)

def classify_completeness(score: float) -> str:
    """Classify completeness level."""
    if score > 0.8:
        return "complete"
    elif score >= 0.5:
        return "partial"
    else:
        return "fragment"
```

---

### 🔄 Task 4: Per-Contig Detection Logging - TODO
**Files:** `scripts/call_orfs.py`, `scripts/classify_bgcs.py`

**Requirements:**
- Write structured log file for each run
- Include: input file hash, contigs processed, ORFs per contig, BGCs per contig
- Confirms detection runs per-input (not cached)

**Log Format:**
```json
{
  "timestamp": "2026-05-09T10:30:00Z",
  "input_file": "sample.fasta",
  "input_hash": "a3f5c8d9e2b1f4a7",
  "total_contigs": 10,
  "per_contig_stats": [
    {
      "contig_id": "contig_001",
      "length": 12450,
      "orfs_predicted": 15,
      "bgcs_detected": 2,
      "bgc_classes": ["NRPS", "PKS"],
      "scores": [0.85, 0.72]
    }
  ],
  "summary": {
    "total_orfs": 150,
    "total_bgcs": 18,
    "processing_time_seconds": 45.2
  }
}
```

---

## 🟡 Priority 2: Detection Accuracy

### 🔄 Task 5: VQC Score Distribution + Percentile Rank - TODO
**File:** `backend/backend_api.py` - `/api/rank` endpoint

**Requirements:**
- Compute mean and std deviation of all candidate scores
- Add `percentile_rank` field to each candidate
- Add `score_distribution` object to JSON output
- Flag `Unknown` BGC classes with `requires_manual_review: true`

**Implementation:**
```python
import numpy as np

def calculate_score_distribution(candidates: List[Dict]) -> Dict:
    """Calculate score distribution statistics."""
    scores = [c['score'] for c in candidates]
    
    return {
        'min': round(min(scores), 3),
        'max': round(max(scores), 3),
        'mean': round(np.mean(scores), 3),
        'std': round(np.std(scores), 3),
        'median': round(np.median(scores), 3),
        'histogram_bins': np.histogram(scores, bins=10)[0].tolist()
    }

def add_percentile_ranks(candidates: List[Dict]) -> List[Dict]:
    """Add percentile rank to each candidate."""
    scores = [c['score'] for c in candidates]
    
    for candidate in candidates:
        # Calculate what % of candidates scored below this one
        below = sum(1 for s in scores if s < candidate['score'])
        percentile = (below / len(scores)) * 100
        candidate['percentile_rank'] = round(percentile, 1)
        
        # Flag Unknown classes
        if candidate['bgc_class'] == 'Unknown':
            candidate['requires_manual_review'] = True
    
    return candidates
```

---

### 🔄 Task 6: Sequence QC Block in Output JSON - TODO
**File:** `backend/backend_api.py` - Final results aggregation

**Requirements:**
- Add `sequence_qc` section to final JSON output
- Include per-contig stats with GC content, N%, complexity
- Add `overall_input_quality` assessment

**Output Format:**
```json
{
  "job_id": "job_1234567890",
  "sequence_qc": {
    "total_contigs_input": 10,
    "contigs_passed_qc": 7,
    "contigs_failed_qc": 3,
    "overall_input_quality": "good",
    "per_contig_stats": [
      {
        "id": "contig_001",
        "length": 12450,
        "gc_content": 58.3,
        "n_percentage": 2.1,
        "complexity_score": 0.847,
        "qc_status": "passed"
      }
    ]
  },
  "detection": {...},
  "novelty": {...},
  "ranking": {...}
}
```

---

## 🟢 Priority 3: Polish & Reliability

### 🔄 Task 7: API Cache-Busting Middleware - PARTIAL
**File:** `backend/backend_api.py`

**Status:** Cache infrastructure created, needs middleware decorator

**Requirements:**
- Compute SHA256 of POST body for all /api/* endpoints
- Check results cache keyed by hash
- Return cached result with `cached: true` flag
- Add `processing_time_seconds` to every response

**Implementation:**
```python
from functools import wraps
import time

def cached_endpoint(cache_type: str):
    """Decorator for caching API endpoints."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            start_time = time.time()
            
            # Calculate cache key from request
            if request.method == 'POST':
                if request.is_json:
                    cache_key = hashlib.sha256(
                        json.dumps(request.json, sort_keys=True).encode()
                    ).hexdigest()[:16]
                else:
                    # For file uploads, use file hash
                    cache_key = None
            else:
                cache_key = None
            
            # Check cache
            if cache_key:
                cached = get_cached_result(cache_key, cache_type)
                if cached:
                    cached['processing_time_seconds'] = time.time() - start_time
                    return jsonify(cached)
            
            # Run endpoint
            result = f(*args, **kwargs)
            
            # Add processing time
            if isinstance(result, tuple):
                data, status = result
            else:
                data = result
                status = 200
            
            if hasattr(data, 'json'):
                json_data = data.json
                json_data['processing_time_seconds'] = round(time.time() - start_time, 2)
                json_data['cached'] = False
                
                # Save to cache
                if cache_key:
                    save_cached_result(cache_key, cache_type, json_data)
                
                return jsonify(json_data), status
            
            return result
        
        return decorated_function
    return decorator

# Usage:
@app.route('/api/novelty', methods=['POST'])
@cached_endpoint('novelty')
def assess_novelty():
    ...
```

---

### 🔄 Task 8: Frontend QC Warning Display - TODO
**File:** `frontend/app.js`

**Requirements:**
- Show yellow warning banner if `overall_input_quality` is "poor"
- Highlight rows with `requires_manual_review: true` in orange
- Show `input_hash` below results
- Add score distribution sparkline

**Implementation:**
```javascript
function displayResults(data) {
  let warningHTML = '';
  
  // Check input quality
  if (data.sequence_qc && data.sequence_qc.overall_input_quality === 'poor') {
    warningHTML = `
      <div class="warning-banner">
        ⚠️ Input quality is poor. Results may be less reliable.
        ${data.sequence_qc.contigs_failed_qc}/${data.sequence_qc.total_contigs_input} contigs failed QC.
      </div>
    `;
  }
  
  // Generate table rows with highlighting
  const tableRows = data.top_candidates.map(candidate => {
    const rowClass = candidate.requires_manual_review ? 'manual-review-required' : '';
    const reviewBadge = candidate.requires_manual_review ? 
      '<span class="badge-warning">Manual Review Required</span>' : '';
    
    return `
      <tr class="${rowClass}">
        <td><code>${candidate.bgc_id}</code></td>
        <td>${candidate.bgc_class} ${reviewBadge}</td>
        <td>${candidate.score}</td>
        <td>${candidate.novelty}%</td>
        <td>${candidate.percentile_rank}%</td>
      </tr>
    `;
  }).join('');
  
  // Add input hash
  const hashHTML = `
    <div class="input-hash">
      Input Hash: <code>${data.input_hash || 'N/A'}</code>
      ${data.cached ? '<span class="badge-info">Cached Result</span>' : ''}
    </div>
  `;
  
  // ... rest of display logic
}
```

---

### 🔄 Task 9: Unified Pipeline Runner - TODO
**File:** `scripts/run_pipeline.py` (NEW)

**Requirements:**
- Chain all steps in order with validation
- Log start/end time and input hash for each step
- Add `--dry-run` flag
- Abort early if QC fails

**Implementation:**
```python
#!/usr/bin/env python3
"""
Unified Pipeline Runner
Chains all BGC-QDR pipeline steps with validation and logging.
"""

import argparse
import json
import time
from pathlib import Path
from datetime import datetime

from sequence_qc import SequenceQC
from call_orfs import run_prodigal
from classify_bgcs import BGCRuleEngine
from novelty_assessment import NoveltyAssessor, load_sequences_from_fasta


class PipelineRunner:
    """Unified pipeline runner with validation."""
    
    def __init__(self, input_fasta: str, output_dir: str, dry_run: bool = False):
        self.input_fasta = Path(input_fasta)
        self.output_dir = Path(output_dir)
        self.dry_run = dry_run
        self.log = []
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def log_step(self, step: str, status: str, details: dict):
        """Log pipeline step."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'step': step,
            'status': status,
            'details': details
        }
        self.log.append(entry)
        print(f"[{step}] {status}: {details}")
    
    def run(self):
        """Run complete pipeline."""
        print("=" * 60)
        print("BGC-QDR Unified Pipeline Runner")
        print("=" * 60)
        print(f"Input: {self.input_fasta}")
        print(f"Output: {self.output_dir}")
        print(f"Dry Run: {self.dry_run}")
        print()
        
        try:
            # Step 1: Input QC
            self.run_qc()
            
            # Step 2: ORF Calling
            self.run_orf_calling()
            
            # Step 3: BGC Classification
            self.run_classification()
            
            # Step 4: Novelty Assessment
            self.run_novelty()
            
            # Step 5: Write final results
            self.write_results()
            
            print("\n✅ Pipeline completed successfully!")
            
        except Exception as e:
            self.log_step("PIPELINE", "FAILED", {'error': str(e)})
            print(f"\n❌ Pipeline failed: {e}")
            raise
    
    def run_qc(self):
        """Step 1: Input QC."""
        start_time = time.time()
        self.log_step("QC", "STARTED", {'input': str(self.input_fasta)})
        
        if self.dry_run:
            self.log_step("QC", "SKIPPED", {'reason': 'dry-run'})
            return
        
        try:
            qc = SequenceQC(str(self.input_fasta))
            report, passed_sequences = qc.run_qc()
            
            # Write filtered FASTA
            filtered_fasta = self.output_dir / "filtered.fasta"
            qc.write_filtered_fasta(str(filtered_fasta), passed_sequences)
            
            elapsed = time.time() - start_time
            self.log_step("QC", "COMPLETED", {
                'input_hash': report['input_hash'],
                'total_sequences': report['total_sequences'],
                'passed': report['passed_sequences'],
                'failed': report['failed_sequences'],
                'quality': report['overall_input_quality'],
                'elapsed_seconds': round(elapsed, 2)
            })
            
            self.filtered_fasta = filtered_fasta
            self.input_hash = report['input_hash']
            
        except ValueError as e:
            # QC failed - abort pipeline
            self.log_step("QC", "FAILED", {'error': str(e)})
            raise
    
    def run_orf_calling(self):
        """Step 2: ORF Calling."""
        # Implementation similar to above
        pass
    
    def run_classification(self):
        """Step 3: BGC Classification."""
        # Implementation similar to above
        pass
    
    def run_novelty(self):
        """Step 4: Novelty Assessment."""
        # Implementation similar to above
        pass
    
    def write_results(self):
        """Write final results JSON."""
        results_file = self.output_dir / "results.json"
        
        results = {
            'input_file': str(self.input_fasta),
            'input_hash': self.input_hash,
            'pipeline_log': self.log,
            'results': {
                # Aggregate all results here
            }
        }
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n📄 Results written to: {results_file}")


def main():
    parser = argparse.ArgumentParser(description="Run complete BGC-QDR pipeline")
    parser.add_argument("--input", "-i", required=True, help="Input FASTA file")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Validate without executing")
    
    args = parser.parse_args()
    
    runner = PipelineRunner(args.input, args.output, args.dry_run)
    runner.run()


if __name__ == "__main__":
    main()
```

---

## Implementation Progress

| Task | Priority | Status | File | Completion |
|------|----------|--------|------|------------|
| Input QC Module | 🔴 P1 | ✅ DONE | `scripts/sequence_qc.py` | 100% |
| Novelty Caching Fix | 🔴 P1 | ✅ DONE | `backend/backend_api.py` | 100% |
| Domain Completeness | 🔴 P1 | 🔄 TODO | `scripts/classify_bgcs.py` | 0% |
| Detection Logging | 🔴 P1 | 🔄 TODO | `scripts/call_orfs.py` | 0% |
| VQC Distribution | 🟡 P2 | 🔄 TODO | `backend/backend_api.py` | 0% |
| QC Output Block | 🟡 P2 | 🔄 TODO | `backend/backend_api.py` | 0% |
| Cache Middleware | 🟢 P3 | 🔄 PARTIAL | `backend/backend_api.py` | 50% |
| Frontend Warnings | 🟢 P3 | 🔄 TODO | `frontend/app.js` | 0% |
| Pipeline Runner | 🟢 P3 | 🔄 TODO | `scripts/run_pipeline.py` | 0% |

---

## Next Steps

1. **Immediate:** Restart backend and test caching functionality
2. **Short-term:** Implement Tasks 3-6 (domain completeness, logging, VQC distribution)
3. **Medium-term:** Complete Tasks 7-9 (middleware, frontend, unified runner)
4. **Testing:** Create test suite for all new functionality
5. **Documentation:** Update README with new features

---

**Last Updated:** 2026-05-09  
**Status:** 2/9 tasks completed, 7 in progress
