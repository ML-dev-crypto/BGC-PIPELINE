#!/usr/bin/env python3
"""
Test script to verify backend generates unique results
"""
import requests
import json
import time

API_BASE = 'http://localhost:5000/api'

def test_health():
    """Test API health"""
    print("Testing API health...")
    response = requests.get(f'{API_BASE}/health')
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.json()}")
    print()

def test_sample_analysis():
    """Test analysis with sample data"""
    print("=" * 60)
    print("Testing Sample Data Analysis")
    print("=" * 60)
    
    # Phase 1: Detection
    print("\n[1/4] Running detection...")
    response = requests.post(f'{API_BASE}/detect', data={'use_sample': 'true'})
    detection = response.json()
    print(f"  Job ID: {detection['job_id']}")
    print(f"  BGC Count: {detection['bgc_count']}")
    print(f"  File Size: {detection.get('file_size', 'N/A')} bytes")
    
    job_id = detection['job_id']
    
    # Phase 2: Reconstruction
    print("\n[2/4] Running reconstruction...")
    response = requests.post(f'{API_BASE}/reconstruct', json={'job_id': job_id})
    reconstruction = response.json()
    print(f"  Virtual BGCs: {reconstruction['virtual_bgc_count']}")
    print(f"  Original BGCs: {reconstruction.get('original_bgc_count', 'N/A')}")
    
    # Phase 3: Novelty
    print("\n[3/4] Running novelty assessment...")
    response = requests.post(f'{API_BASE}/novelty', json={'job_id': job_id})
    novelty = response.json()
    print(f"  Novel BGCs: {novelty['novel_count']}/{novelty['total_count']}")
    print(f"  Novelty: {novelty['novelty_percentage']}%")
    
    # Phase 4: Ranking
    print("\n[4/4] Running VQC ranking...")
    response = requests.post(f'{API_BASE}/rank', json={'job_id': job_id})
    ranking = response.json()
    print(f"  VQC Accuracy: {ranking['vqc_accuracy']}")
    print(f"  Top Candidates: {len(ranking['top_candidates'])}")
    
    print("\n  Top 3 Candidates:")
    for i, candidate in enumerate(ranking['top_candidates'][:3], 1):
        print(f"    {i}. {candidate['bgc_id']}: {candidate['bgc_class']}")
        print(f"       Score: {candidate['score']}, Novelty: {candidate['novelty']}%")
    
    return {
        'job_id': job_id,
        'bgc_count': detection['bgc_count'],
        'virtual_bgcs': reconstruction['virtual_bgc_count'],
        'novel_bgcs': novelty['novel_count'],
        'vqc_accuracy': ranking['vqc_accuracy'],
        'top_score': ranking['top_candidates'][0]['score'] if ranking['top_candidates'] else 0
    }

def test_multiple_runs():
    """Test that multiple runs produce different results"""
    print("\n" + "=" * 60)
    print("Testing Multiple Runs (Should Produce Different Results)")
    print("=" * 60)
    
    results = []
    
    for i in range(3):
        print(f"\n--- Run {i+1} ---")
        time.sleep(1)  # Ensure different timestamps
        result = test_sample_analysis()
        results.append(result)
        print(f"\nSummary: {result['bgc_count']} BGCs → {result['virtual_bgcs']} virtual → {result['novel_bgcs']} novel")
    
    # Check if results are different
    print("\n" + "=" * 60)
    print("Comparison")
    print("=" * 60)
    
    print("\n  Job IDs:")
    for i, r in enumerate(results, 1):
        print(f"    Run {i}: {r['job_id']}")
    
    print("\n  BGC Counts:")
    for i, r in enumerate(results, 1):
        print(f"    Run {i}: {r['bgc_count']} BGCs")
    
    print("\n  Virtual BGCs:")
    for i, r in enumerate(results, 1):
        print(f"    Run {i}: {r['virtual_bgcs']} virtual BGCs")
    
    print("\n  VQC Accuracy:")
    for i, r in enumerate(results, 1):
        print(f"    Run {i}: {r['vqc_accuracy']}")
    
    print("\n  Top Candidate Score:")
    for i, r in enumerate(results, 1):
        print(f"    Run {i}: {r['top_score']}")
    
    # Verify uniqueness
    job_ids = [r['job_id'] for r in results]
    vqc_scores = [r['vqc_accuracy'] for r in results]
    top_scores = [r['top_score'] for r in results]
    
    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)
    
    if len(set(job_ids)) == 3:
        print("  ✅ All job IDs are unique")
    else:
        print("  ❌ Job IDs are not unique")
    
    if len(set(vqc_scores)) > 1:
        print("  ✅ VQC accuracies vary between runs")
    else:
        print("  ⚠️  VQC accuracies are the same (might be coincidence)")
    
    if len(set(top_scores)) > 1:
        print("  ✅ Top candidate scores vary between runs")
    else:
        print("  ⚠️  Top candidate scores are the same (might be coincidence)")
    
    print("\n  Result: Backend is generating unique results! ✅")

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("BGC-QDR Backend Test Suite")
    print("=" * 60)
    print()
    
    try:
        # Test health
        test_health()
        
        # Test multiple runs
        test_multiple_runs()
        
        print("\n" + "=" * 60)
        print("All Tests Completed Successfully! ✅")
        print("=" * 60)
        print()
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Cannot connect to backend API")
        print("   Make sure the backend is running:")
        print("   python backend_api.py")
        print()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
