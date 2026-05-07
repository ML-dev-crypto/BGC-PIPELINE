#!/usr/bin/env python3
"""
BGC-QDR Integration Test Script
Tests the complete full-stack integration
"""

import requests
import json
import time
from pathlib import Path

# Configuration
API_BASE_URL = 'http://localhost:5000/api'
FRONTEND_URL = 'http://localhost:3000'

def print_header(text):
    """Print a formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def print_success(text):
    """Print success message"""
    print(f"✅ {text}")

def print_error(text):
    """Print error message"""
    print(f"❌ {text}")

def print_info(text):
    """Print info message"""
    print(f"ℹ️  {text}")

def test_backend_health():
    """Test if backend is running"""
    print_header("Testing Backend Health")
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success("Backend is running!")
            print_info(f"Status: {data.get('status')}")
            print_info(f"Version: {data.get('version')}")
            print_info(f"Pipeline: {data.get('pipeline')}")
            print_info(f"Phases: {data.get('phases')}")
            return True
        else:
            print_error(f"Backend returned status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error("Cannot connect to backend!")
        print_info("Make sure backend is running: python backend_api.py")
        return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_backend_stats():
    """Test stats endpoint"""
    print_header("Testing Stats Endpoint")
    try:
        response = requests.get(f"{API_BASE_URL}/stats", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print_success("Stats endpoint working!")
            print_info(f"Total BGCs: {data.get('total_bgcs')}")
            print_info(f"Virtual BGCs: {data.get('virtual_bgcs')}")
            print_info(f"VQC Accuracy: {data.get('vqc_accuracy')}")
            print_info(f"MIBiG Size: {data.get('mibig_size')}")
            return True
        else:
            print_error(f"Stats endpoint returned status code: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Error: {e}")
        return False

def test_complete_pipeline():
    """Test complete pipeline execution"""
    print_header("Testing Complete Pipeline")
    
    try:
        # Phase 1-2: Detection
        print_info("Phase 1-2: Running BGC detection...")
        response = requests.post(
            f"{API_BASE_URL}/detect",
            data={'use_sample': 'true'},
            timeout=10
        )
        
        if response.status_code != 200:
            print_error(f"Detection failed with status code: {response.status_code}")
            return False
        
        detection_data = response.json()
        job_id = detection_data.get('job_id')
        bgc_count = detection_data.get('bgc_count')
        
        print_success(f"Detection complete! Job ID: {job_id}")
        print_info(f"BGCs detected: {bgc_count}")
        
        time.sleep(0.5)
        
        # Phase 3: Reconstruction
        print_info("Phase 3: Running graph reconstruction...")
        response = requests.post(
            f"{API_BASE_URL}/reconstruct",
            json={'job_id': job_id},
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code != 200:
            print_error(f"Reconstruction failed with status code: {response.status_code}")
            return False
        
        reconstruction_data = response.json()
        virtual_bgc_count = reconstruction_data.get('virtual_bgc_count')
        
        print_success(f"Reconstruction complete!")
        print_info(f"Virtual BGCs: {virtual_bgc_count}")
        
        time.sleep(0.5)
        
        # Phase 4-5: Novelty
        print_info("Phase 4-5: Running novelty assessment...")
        response = requests.post(
            f"{API_BASE_URL}/novelty",
            json={'job_id': job_id},
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code != 200:
            print_error(f"Novelty assessment failed with status code: {response.status_code}")
            return False
        
        novelty_data = response.json()
        novel_count = novelty_data.get('novel_count')
        novelty_percentage = novelty_data.get('novelty_percentage')
        
        print_success(f"Novelty assessment complete!")
        print_info(f"Novel BGCs: {novel_count}/{novelty_data.get('total_count')}")
        print_info(f"Novelty: {novelty_percentage}%")
        
        time.sleep(0.5)
        
        # Phase 6: Ranking
        print_info("Phase 6: Running VQC ranking...")
        response = requests.post(
            f"{API_BASE_URL}/rank",
            json={'job_id': job_id},
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code != 200:
            print_error(f"Ranking failed with status code: {response.status_code}")
            return False
        
        ranking_data = response.json()
        vqc_accuracy = ranking_data.get('vqc_accuracy')
        top_candidates = ranking_data.get('top_candidates', [])
        
        print_success(f"VQC ranking complete!")
        print_info(f"VQC Accuracy: {vqc_accuracy:.1%}")
        print_info(f"Top candidates: {len(top_candidates)}")
        
        # Display top candidates
        print("\n📊 Top BGC Candidates:")
        print("-" * 60)
        for i, candidate in enumerate(top_candidates[:3], 1):
            print(f"{i}. {candidate['bgc_id']}")
            print(f"   Class: {candidate['bgc_class']}")
            print(f"   Score: {candidate['score']:.1%}")
            print(f"   Novelty: {candidate['novelty']:.2f}%")
            print()
        
        return True
        
    except Exception as e:
        print_error(f"Pipeline error: {e}")
        return False

def test_frontend_files():
    """Test if frontend files exist"""
    print_header("Testing Frontend Files")
    
    files_to_check = [
        'frontend/index.html',
        'frontend/app.js',
        'frontend/styles.css',
        'frontend/assets/DNA.mp4'
    ]
    
    all_exist = True
    for file_path in files_to_check:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size
            print_success(f"{file_path} exists ({size:,} bytes)")
        else:
            print_error(f"{file_path} NOT FOUND!")
            all_exist = False
    
    return all_exist

def test_sample_data():
    """Test if sample data exists"""
    print_header("Testing Sample Data")
    
    sample_files = [
        'edna_fasta/GCA_000205625.1.fasta',
        'edna_fasta/GCA_000565115.1.fasta',
        'edna_fasta/GCA_030153465.1.fasta'
    ]
    
    all_exist = True
    for file_path in sample_files:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size
            print_success(f"{file_path} exists ({size:,} bytes)")
        else:
            print_error(f"{file_path} NOT FOUND!")
            all_exist = False
    
    return all_exist

def main():
    """Run all tests"""
    print_header("BGC-QDR Integration Test Suite")
    print_info("Testing full-stack integration...")
    
    results = {
        'Frontend Files': test_frontend_files(),
        'Sample Data': test_sample_data(),
        'Backend Health': test_backend_health(),
        'Backend Stats': test_backend_stats(),
        'Complete Pipeline': test_complete_pipeline()
    }
    
    # Summary
    print_header("Test Summary")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print_success("All tests passed! 🎉")
        print_info("Your BGC-QDR full-stack application is working correctly!")
        print_info("Open http://localhost:3000 in your browser to use it.")
    else:
        print_error(f"{total - passed} test(s) failed")
        print_info("Check the errors above and fix them before proceeding.")
    
    return passed == total

if __name__ == '__main__':
    try:
        success = main()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        exit(1)
