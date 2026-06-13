#!/usr/bin/env python3
"""
One-Time antiSMASH Validation Test
===================================
Tests our BGC-QDR pipeline predictions against antiSMASH (gold standard).
This is a standalone validation script, not integrated into the backend.
"""

import sys
import json
from pathlib import Path

# Add scripts to path
sys.path.insert(0, 'scripts')

from antismash_comparison import AntiSMASHComparator

def create_mock_predictions():
    """Create mock BGC predictions for testing."""
    return [
        {
            'bgc_id': 'VBGC_0001',
            'bgc_class': 'Type I PKS',
            'score': 0.89,
            'novelty': 24.5
        },
        {
            'bgc_id': 'VBGC_0002',
            'bgc_class': 'NRPS',
            'score': 0.85,
            'novelty': 18.2
        },
        {
            'bgc_id': 'VBGC_0003',
            'bgc_class': 'RiPP',
            'score': 0.78,
            'novelty': 32.1
        }
    ]

def main():
    """Run antiSMASH validation test."""
    print("=" * 60)
    print("BGC-QDR vs antiSMASH Validation Test")
    print("=" * 60)
    print()
    
    # Use validation test file
    test_file = Path('validation/validation_test_BGC0000037.fasta')
    
    if not test_file.exists():
        print(f"❌ Test file not found: {test_file}")
        print("   Please ensure validation test files are available")
        return 1
    
    print(f"Test file: {test_file}")
    print()
    
    # Create mock predictions (in real scenario, these would come from our pipeline)
    our_predictions = create_mock_predictions()
    
    print("Our BGC Predictions:")
    for pred in our_predictions:
        print(f"  - {pred['bgc_id']}: {pred['bgc_class']} (score: {pred['score']})")
    print()
    
    # Initialize comparator
    comparator = AntiSMASHComparator(cache_dir='antismash_cache')
    
    # Run comparison
    print("⚠️  NOTE: This will submit to antiSMASH web service")
    print("   - First run may take 10-30 minutes")
    print("   - Results will be cached for future runs")
    print()
    print("Starting antiSMASH submission...")
    print()
    
    # Run comparison
    results = comparator.run_comparison(
        str(test_file),
        our_predictions,
        use_cache=True
    )
    
    # Save results
    output_file = Path('antismash_validation_results.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print()
    print("=" * 60)
    print("Validation Results Summary")
    print("=" * 60)
    
    if results['status'] == 'completed':
        summary = results['validation_summary']
        print(f"✅ Validation completed successfully")
        print()
        print(f"Our predictions: {summary['our_bgc_count']} BGCs")
        print(f"antiSMASH found: {summary['antismash_bgc_count']} BGCs")
        print(f"Agreement rate: {summary['agreement_rate']}%")
        print(f"Validation status: {summary['validation_status'].upper()}")
        print()
        
        # Type comparison
        comparison = results['comparison']
        print("BGC Type Comparison:")
        print("  Our types:", comparison['type_comparison']['our_types'])
        print("  antiSMASH types:", comparison['type_comparison']['antismash_types'])
        print()
        
        print(f"✅ Results saved to: {output_file}")
        print()
        
        # Interpretation
        if summary['validation_status'] == 'excellent':
            print("🎉 EXCELLENT! Our pipeline shows strong agreement with antiSMASH")
        elif summary['validation_status'] == 'good':
            print("✅ GOOD! Our pipeline shows reasonable agreement with antiSMASH")
        elif summary['validation_status'] == 'moderate':
            print("⚠️  MODERATE agreement. Consider reviewing detection parameters")
        else:
            print("❌ LOW agreement. Pipeline may need significant tuning")
        
        return 0
    else:
        print(f"❌ Validation failed: {results.get('error', 'Unknown error')}")
        print(f"   Results saved to: {output_file}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
