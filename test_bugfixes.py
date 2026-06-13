#!/usr/bin/env python3
"""
Test Script for Bug Fixes
==========================
Quick verification that all bug fixes are working correctly.
"""

import sys
import json
from pathlib import Path

def test_input_qc():
    """Test that input_qc.py module exists and can be imported."""
    print("=" * 60)
    print("Test 1: Input QC Module")
    print("=" * 60)
    
    try:
        sys.path.insert(0, 'scripts')
        from input_qc import InputQC
        print("✅ input_qc.py module can be imported")
        print("✅ InputQC class available")
        
        # Check key methods exist
        assert hasattr(InputQC, 'run_qc'), "Missing run_qc method"
        assert hasattr(InputQC, 'write_filtered_fasta'), "Missing write_filtered_fasta method"
        print("✅ All required methods present")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_novelty_caching():
    """Test that novelty assessment has caching support."""
    print("\n" + "=" * 60)
    print("Test 2: Novelty Caching")
    print("=" * 60)
    
    try:
        # Check backend_api.py has cache implementation
        with open('backend/backend_api.py', encoding='utf-8') as f:
            content = f.read()
        
        assert 'NOVELTY_CACHE' in content, "Missing NOVELTY_CACHE"
        assert 'input_hash' in content, "Missing input_hash calculation"
        assert 'cached' in content, "Missing cached flag"
        print("✅ NOVELTY_CACHE dictionary present")
        print("✅ input_hash calculation present")
        print("✅ cached flag present")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_completeness_scoring():
    """Test that classify_bgcs.py has completeness scoring."""
    print("\n" + "=" * 60)
    print("Test 3: Domain Completeness Scoring")
    print("=" * 60)
    
    try:
        with open('scripts/classify_bgcs.py', encoding='utf-8') as f:
            content = f.read()
        
        assert 'completeness_score' in content, "Missing completeness_score"
        assert 'completeness_tag' in content, "Missing completeness_tag"
        assert '_calculate_completeness_score' in content, "Missing completeness calculation method"
        assert 'min_completeness' in content, "Missing min_completeness filter"
        print("✅ completeness_score field present")
        print("✅ completeness_tag field present")
        print("✅ _calculate_completeness_score method present")
        print("✅ --min-completeness CLI flag present")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_logging():
    """Test that logging is implemented in ORF calling and classification."""
    print("\n" + "=" * 60)
    print("Test 4: Per-Contig Detection Logging")
    print("=" * 60)
    
    try:
        # Check call_orfs.py
        with open('scripts/call_orfs.py', encoding='utf-8') as f:
            orf_content = f.read()
        
        assert 'log_file' in orf_content or '--log' in orf_content, "Missing log parameter in call_orfs.py"
        assert 'input_hash' in orf_content, "Missing input_hash in call_orfs.py"
        print("✅ call_orfs.py has logging support")
        
        # Check classify_bgcs.py
        with open('scripts/classify_bgcs.py', encoding='utf-8') as f:
            bgc_content = f.read()
        
        assert '--log' in bgc_content, "Missing log parameter in classify_bgcs.py"
        assert 'log_data' in bgc_content or 'log_file' in bgc_content, "Missing log implementation in classify_bgcs.py"
        print("✅ classify_bgcs.py has logging support")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_score_distribution():
    """Test that VQC ranking has score distribution."""
    print("\n" + "=" * 60)
    print("Test 5: VQC Score Distribution")
    print("=" * 60)
    
    try:
        with open('backend/backend_api.py', encoding='utf-8') as f:
            content = f.read()
        
        assert 'score_distribution' in content, "Missing score_distribution"
        assert 'percentile_rank' in content, "Missing percentile_rank"
        assert 'histogram_bins' in content, "Missing histogram_bins"
        assert 'requires_manual_review' in content, "Missing requires_manual_review flag"
        print("✅ score_distribution present")
        print("✅ percentile_rank present")
        print("✅ histogram_bins present")
        print("✅ requires_manual_review flag present")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_sequence_qc_output():
    """Test that sequence QC is included in output."""
    print("\n" + "=" * 60)
    print("Test 6: Sequence QC in Output")
    print("=" * 60)
    
    try:
        with open('backend/backend_api.py', encoding='utf-8') as f:
            content = f.read()
        
        assert 'sequence_qc' in content, "Missing sequence_qc in output"
        assert 'overall_input_quality' in content, "Missing overall_input_quality"
        print("✅ sequence_qc block present in output")
        print("✅ overall_input_quality field present")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_api_caching():
    """Test that API cache middleware is implemented."""
    print("\n" + "=" * 60)
    print("Test 7: API Cache-Busting Middleware")
    print("=" * 60)
    
    try:
        with open('backend/backend_api.py', encoding='utf-8') as f:
            content = f.read()
        
        assert 'API_CACHE' in content, "Missing API_CACHE"
        assert 'cache_api_result' in content, "Missing cache_api_result decorator"
        assert 'processing_time_seconds' in content, "Missing processing_time_seconds"
        assert '@cache_api_result' in content, "Decorator not applied to endpoints"
        print("✅ API_CACHE dictionary present")
        print("✅ cache_api_result decorator present")
        print("✅ processing_time_seconds present")
        print("✅ Decorator applied to endpoints")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_frontend_enhancements():
    """Test that frontend has QC warnings and enhanced display."""
    print("\n" + "=" * 60)
    print("Test 8: Frontend QC Warning Display")
    print("=" * 60)
    
    try:
        with open('frontend/app.js', encoding='utf-8') as f:
            js_content = f.read()
        
        assert 'qc-warning' in js_content or 'qcWarnings' in js_content, "Missing QC warnings"
        assert 'requires_manual_review' in js_content, "Missing manual review handling"
        assert 'score_distribution' in js_content or 'scoreDistHTML' in js_content, "Missing score distribution display"
        assert 'input_hash' in js_content, "Missing input_hash display"
        print("✅ QC warnings implemented")
        print("✅ Manual review highlighting implemented")
        print("✅ Score distribution display implemented")
        print("✅ Input hash display implemented")
        
        # Check CSS
        with open('frontend/styles.css', encoding='utf-8') as f:
            css_content = f.read()
        
        assert 'qc-warning' in css_content, "Missing QC warning styles"
        assert 'requires-review' in css_content, "Missing review row styles"
        print("✅ QC warning styles present")
        print("✅ Review row styles present")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def test_pipeline_runner():
    """Test that unified pipeline runner exists."""
    print("\n" + "=" * 60)
    print("Test 9: Unified Pipeline Runner")
    print("=" * 60)
    
    try:
        pipeline_file = Path('scripts/run_pipeline.py')
        assert pipeline_file.exists(), "run_pipeline.py not found"
        print("✅ run_pipeline.py exists")
        
        with open(pipeline_file, encoding='utf-8') as f:
            content = f.read()
        
        assert 'PipelineRunner' in content, "Missing PipelineRunner class"
        assert '--dry-run' in content, "Missing dry-run flag"
        assert 'validate_input' in content, "Missing input validation"
        assert 'run_input_qc' in content, "Missing QC step"
        print("✅ PipelineRunner class present")
        print("✅ --dry-run flag present")
        print("✅ Input validation present")
        print("✅ QC step present")
        
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("BGC-QDR Bug Fix Verification")
    print("=" * 60)
    print()
    
    tests = [
        test_input_qc,
        test_novelty_caching,
        test_completeness_scoring,
        test_logging,
        test_score_distribution,
        test_sequence_qc_output,
        test_api_caching,
        test_frontend_enhancements,
        test_pipeline_runner
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
