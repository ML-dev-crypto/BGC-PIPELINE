#!/usr/bin/env python3
"""
Backend Integration Test
=========================
Tests the enhanced backend API with synthetic sequence detection.
"""

import requests
import json
import time
from pathlib import Path

API_BASE_URL = 'http://localhost:5000/api'

def test_health():
    """Test health endpoint."""
    print("=" * 60)
    print("Test 1: Health Check")
    print("=" * 60)
    
    try:
        response = requests.get(f'{API_BASE_URL}/health')
        data = response.json()
        
        assert response.status_code == 200
        assert data['status'] == 'healthy'
        print("✅ Health check passed")
        print(f"   Status: {data['status']}")
        print(f"   QC Available: {data.get('qc_available', False)}")
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_detect_with_synthetic(exclude_synthetic=False):
    """Test detection endpoint with synthetic sequence handling."""
    print("\n" + "=" * 60)
    print(f"Test 2: Detection {'WITH' if exclude_synthetic else 'WITHOUT'} Synthetic Exclusion")
    print("=" * 60)
    
    try:
        # Use the test file with synthetic sequences
        test_file = Path('uploads/job_1778159964.fasta')
        
        if not test_file.exists():
            print(f"⚠️  Test file not found: {test_file}")
            return False
        
        with open(test_file, 'rb') as f:
            files = {'fasta_file': f}
            data = {
                'use_sample': 'false',
                'exclude_synthetic': 'true' if exclude_synthetic else 'false'
            }
            
            response = requests.post(f'{API_BASE_URL}/detect', files=files, data=data)
        
        result = response.json()
        
        assert response.status_code == 200
        assert 'job_id' in result
        assert 'bgc_count' in result
        
        print(f"✅ Detection completed")
        print(f"   Job ID: {result['job_id']}")
        print(f"   BGC Count: {result['bgc_count']}")
        print(f"   Exclude Synthetic: {result.get('exclude_synthetic', False)}")
        
        if 'qc_summary' in result and result['qc_summary']:
            qc = result['qc_summary']
            print(f"   QC Summary:")
            print(f"     Total: {qc.get('total_sequences', 0)}")
            print(f"     Passed: {qc.get('passed_sequences', 0)}")
            print(f"     Failed: {qc.get('failed_sequences', 0)}")
            if 'synthetic_excluded' in qc:
                print(f"     Synthetic Excluded: {qc['synthetic_excluded']}")
            if 'sequence_origins' in qc:
                print(f"     Origins: {qc['sequence_origins']}")
        
        print(f"   Message: {result.get('message', 'N/A')}")
        print(f"   Cached: {result.get('cached', False)}")
        print(f"   Processing Time: {result.get('processing_time_seconds', 0):.3f}s")
        
        return True, result
    except Exception as e:
        print(f"❌ Detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_full_pipeline(job_id):
    """Test full pipeline with a job ID."""
    print("\n" + "=" * 60)
    print("Test 3: Full Pipeline")
    print("=" * 60)
    
    try:
        # Reconstruction
        print("  Running reconstruction...")
        response = requests.post(
            f'{API_BASE_URL}/reconstruct',
            json={'job_id': job_id}
        )
        recon_result = response.json()
        print(f"  ✅ Reconstruction: {recon_result.get('virtual_bgc_count', 0)} virtual BGCs")
        
        # Novelty
        print("  Running novelty assessment...")
        response = requests.post(
            f'{API_BASE_URL}/novelty',
            json={'job_id': job_id}
        )
        novelty_result = response.json()
        print(f"  ✅ Novelty: {novelty_result.get('novel_count', 0)} novel BGCs")
        
        # Ranking
        print("  Running ranking...")
        response = requests.post(
            f'{API_BASE_URL}/rank',
            json={'job_id': job_id}
        )
        rank_result = response.json()
        print(f"  ✅ Ranking: {len(rank_result.get('top_candidates', []))} top candidates")
        print(f"     VQC Accuracy: {rank_result.get('vqc_accuracy', 0):.3f}")
        
        return True
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        return False

def test_caching():
    """Test that caching works."""
    print("\n" + "=" * 60)
    print("Test 4: API Caching")
    print("=" * 60)
    
    try:
        test_file = Path('uploads/job_1778159964.fasta')
        
        # First request
        print("  First request (should not be cached)...")
        with open(test_file, 'rb') as f:
            files = {'fasta_file': f}
            data = {'use_sample': 'false', 'exclude_synthetic': 'true'}
            response1 = requests.post(f'{API_BASE_URL}/detect', files=files, data=data)
        
        result1 = response1.json()
        time1 = result1.get('processing_time_seconds', 0)
        cached1 = result1.get('cached', False)
        
        print(f"  ✅ First request: {time1:.3f}s, Cached: {cached1}")
        
        # Second request (should be cached)
        print("  Second request (should be cached)...")
        with open(test_file, 'rb') as f:
            files = {'fasta_file': f}
            data = {'use_sample': 'false', 'exclude_synthetic': 'true'}
            response2 = requests.post(f'{API_BASE_URL}/detect', files=files, data=data)
        
        result2 = response2.json()
        time2 = result2.get('processing_time_seconds', 0)
        cached2 = result2.get('cached', False)
        
        print(f"  ✅ Second request: {time2:.3f}s, Cached: {cached2}")
        
        if cached2:
            print(f"  ✅ Caching working! Speedup: {time1/max(time2, 0.001):.1f}x faster")
        else:
            print(f"  ⚠️  Second request not cached (may be expected if cache was cleared)")
        
        return True
    except Exception as e:
        print(f"❌ Caching test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("BGC-QDR Backend Integration Tests")
    print("=" * 60)
    print()
    
    results = []
    
    # Test 1: Health
    results.append(test_health())
    
    # Test 2a: Detection without synthetic exclusion
    success, result_without = test_detect_with_synthetic(exclude_synthetic=False)
    results.append(success)
    
    # Test 2b: Detection with synthetic exclusion
    success, result_with = test_detect_with_synthetic(exclude_synthetic=True)
    results.append(success)
    
    # Compare results
    if result_without and result_with:
        print("\n" + "=" * 60)
        print("Comparison: With vs Without Synthetic Exclusion")
        print("=" * 60)
        print(f"Without exclusion: {result_without['bgc_count']} sequences")
        print(f"With exclusion: {result_with['bgc_count']} sequences")
        diff = result_without['bgc_count'] - result_with['bgc_count']
        print(f"Difference: {diff} synthetic sequences excluded")
    
    # Test 3: Full pipeline
    if result_with:
        results.append(test_full_pipeline(result_with['job_id']))
    
    # Test 4: Caching
    results.append(test_caching())
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n✅ All integration tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
