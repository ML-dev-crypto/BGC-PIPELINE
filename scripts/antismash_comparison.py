#!/usr/bin/env python3
"""
antiSMASH Comparison Module
============================
Validates BGC predictions against antiSMASH (the gold standard).

Uses antiSMASH REST API to analyze top candidates and compare results.
"""

import requests
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from Bio import SeqIO
import argparse


class AntiSMASHComparator:
    """Compare BGC predictions with antiSMASH results."""
    
    # antiSMASH REST API endpoints
    ANTISMASH_API_URL = "https://antismash.secondarymetabolites.org/api/v1.0"
    UPLOAD_ENDPOINT = f"{ANTISMASH_API_URL}/submit"
    STATUS_ENDPOINT = f"{ANTISMASH_API_URL}/status"
    DOWNLOAD_ENDPOINT = f"{ANTISMASH_API_URL}/download"
    
    # Job status polling
    MAX_POLL_ATTEMPTS = 60  # 60 attempts
    POLL_INTERVAL = 30  # 30 seconds between polls
    
    def __init__(self, cache_dir: str = "antismash_cache"):
        """Initialize comparator with cache directory."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "antismash_cache.json"
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """Load cached antiSMASH results."""
        if self.cache_file.exists():
            with open(self.cache_file) as f:
                return json.load(f)
        return {}
    
    def _save_cache(self):
        """Save cache to disk."""
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)
    
    def _calculate_sequence_hash(self, sequence: str) -> str:
        """Calculate MD5 hash of sequence for caching."""
        return hashlib.md5(sequence.encode()).hexdigest()
    
    def submit_to_antismash(self, fasta_file: str, email: str = "bgcqdr@example.com") -> Optional[str]:
        """
        Submit sequence to antiSMASH for analysis.
        
        Args:
            fasta_file: Path to FASTA file
            email: Email for job notification
        
        Returns:
            Job ID if successful, None otherwise
        """
        print(f"  Submitting to antiSMASH: {fasta_file}")
        
        try:
            with open(fasta_file, 'rb') as f:
                files = {'seq': f}
                data = {
                    'email': email,
                    'jobtype': 'antismash6',
                    'taxon': 'bacteria',
                    'all_orfs': 'on',
                    'smcogs': 'on',
                    'clusterblast': 'on',
                    'knownclusterblast': 'on',
                    'subclusterblast': 'on'
                }
                
                response = requests.post(self.UPLOAD_ENDPOINT, files=files, data=data, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    job_id = result.get('id')
                    print(f"  [OK] Submitted to antiSMASH: Job ID {job_id}")
                    return job_id
                else:
                    print(f"  [ERROR] antiSMASH submission failed: {response.status_code}")
                    print(f"     Response: {response.text}")
                    return None
                    
        except Exception as e:
            print(f"  [ERROR] Error submitting to antiSMASH: {e}")
            return None
    
    def check_job_status(self, job_id: str) -> Dict:
        """
        Check status of antiSMASH job.
        
        Args:
            job_id: antiSMASH job ID
        
        Returns:
            Status dict with 'state' and other info
        """
        try:
            response = requests.get(f"{self.STATUS_ENDPOINT}/{job_id}", timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"  [WARN]  Status check returned {response.status_code}: {response.text}")
                return {'state': 'error', 'message': f'HTTP {response.status_code}'}
        except Exception as e:
            print(f"  [WARN]  Status check exception: {e}")
            return {'state': 'error', 'message': str(e)}
    
    def wait_for_completion(self, job_id: str) -> bool:
        """
        Wait for antiSMASH job to complete.
        
        Args:
            job_id: antiSMASH job ID
        
        Returns:
            True if completed successfully, False otherwise
        """
        print(f"  Waiting for antiSMASH job {job_id} to complete...")
        
        for attempt in range(self.MAX_POLL_ATTEMPTS):
            status = self.check_job_status(job_id)
            state = status.get('state', 'unknown')
            
            if state == 'done':
                print(f"  [OK] antiSMASH job completed!")
                return True
            elif state == 'failed' or state == 'error':
                print(f"  [ERROR] antiSMASH job failed: {status.get('message', 'Unknown error')}")
                return False
            elif state == 'running' or state == 'queued':
                print(f"  ⏳ Job status: {state} (attempt {attempt + 1}/{self.MAX_POLL_ATTEMPTS})")
                time.sleep(self.POLL_INTERVAL)
            else:
                print(f"  [WARN]  Unknown status: {state}")
                time.sleep(self.POLL_INTERVAL)
        
        print(f"  [ERROR] Timeout waiting for antiSMASH job")
        return False
    
    def download_results(self, job_id: str) -> Optional[Dict]:
        """
        Download antiSMASH results.
        
        Args:
            job_id: antiSMASH job ID
        
        Returns:
            Results dict or None if failed
        """
        try:
            # Download JSON results
            response = requests.get(f"{self.DOWNLOAD_ENDPOINT}/{job_id}/json", timeout=60)
            
            if response.status_code == 200:
                results = response.json()
                print(f"  [OK] Downloaded antiSMASH results")
                return results
            else:
                print(f"  [ERROR] Failed to download results: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"  [ERROR] Error downloading results: {e}")
            return None
    
    def parse_antismash_results(self, results: Dict) -> Dict:
        """
        Parse antiSMASH results into simplified format.
        
        Args:
            results: Raw antiSMASH JSON results
        
        Returns:
            Simplified results dict
        """
        parsed = {
            'total_regions': 0,
            'bgc_types': {},
            'regions': []
        }
        
        try:
            records = results.get('records', [])
            
            for record in records:
                regions = record.get('areas', []) or record.get('regions', [])
                
                for region in regions:
                    parsed['total_regions'] += 1
                    
                    # Get BGC type
                    bgc_type = region.get('product', 'Unknown')
                    if isinstance(bgc_type, list):
                        bgc_type = ', '.join(bgc_type)
                    
                    # Count types
                    parsed['bgc_types'][bgc_type] = parsed['bgc_types'].get(bgc_type, 0) + 1
                    
                    # Store region info
                    region_info = {
                        'region_number': region.get('idx', 0),
                        'bgc_type': bgc_type,
                        'start': region.get('start', 0),
                        'end': region.get('end', 0),
                        'length': region.get('end', 0) - region.get('start', 0),
                        'genes': len(region.get('orfs', [])),
                        'similarity': region.get('similarity', {})
                    }
                    
                    parsed['regions'].append(region_info)
            
        except Exception as e:
            print(f"  [WARN]  Error parsing antiSMASH results: {e}")
        
        return parsed
    
    def compare_predictions(self, our_predictions: List[Dict], antismash_results: Dict) -> Dict:
        """
        Compare our BGC predictions with antiSMASH results.
        
        Args:
            our_predictions: List of our BGC predictions
            antismash_results: Parsed antiSMASH results
        
        Returns:
            Comparison metrics
        """
        comparison = {
            'our_count': len(our_predictions),
            'antismash_count': antismash_results['total_regions'],
            'agreement_rate': 0.0,
            'type_comparison': {},
            'validation_status': 'unknown'
        }
        
        # Count our BGC types
        our_types = {}
        for pred in our_predictions:
            bgc_type = pred.get('bgc_class', 'Unknown')
            our_types[bgc_type] = our_types.get(bgc_type, 0) + 1
        
        # Compare types
        antismash_types = antismash_results['bgc_types']
        
        comparison['type_comparison'] = {
            'our_types': our_types,
            'antismash_types': antismash_types
        }
        
        # Calculate agreement
        if comparison['antismash_count'] > 0:
            # Simple agreement: how close are the counts?
            count_diff = abs(comparison['our_count'] - comparison['antismash_count'])
            max_count = max(comparison['our_count'], comparison['antismash_count'])
            comparison['agreement_rate'] = round((1 - count_diff / max_count) * 100, 1)
            
            # Validation status
            if comparison['agreement_rate'] >= 80:
                comparison['validation_status'] = 'excellent'
            elif comparison['agreement_rate'] >= 60:
                comparison['validation_status'] = 'good'
            elif comparison['agreement_rate'] >= 40:
                comparison['validation_status'] = 'moderate'
            else:
                comparison['validation_status'] = 'poor'
        
        return comparison
    
    def run_comparison(self, fasta_file: str, our_predictions: List[Dict], 
                      use_cache: bool = True) -> Dict:
        """
        Run complete comparison workflow.
        
        Args:
            fasta_file: Path to FASTA file
            our_predictions: List of our BGC predictions
            use_cache: Whether to use cached results
        
        Returns:
            Complete comparison results
        """
        print("=" * 60)
        print("antiSMASH Comparison")
        print("=" * 60)
        
        # Calculate sequence hash for caching
        with open(fasta_file) as f:
            sequence = f.read()
        seq_hash = self._calculate_sequence_hash(sequence)
        
        # Check cache
        if use_cache and seq_hash in self.cache:
            print("  [OK] Using cached antiSMASH results")
            antismash_results = self.cache[seq_hash]['antismash_results']
            job_id = self.cache[seq_hash].get('job_id', 'cached')
        else:
            # Submit to antiSMASH
            job_id = self.submit_to_antismash(fasta_file)
            
            if not job_id:
                return {
                    'status': 'failed',
                    'error': 'Failed to submit to antiSMASH',
                    'our_predictions': our_predictions
                }
            
            # Wait for completion
            if not self.wait_for_completion(job_id):
                return {
                    'status': 'failed',
                    'error': 'antiSMASH job failed or timed out',
                    'job_id': job_id,
                    'our_predictions': our_predictions
                }
            
            # Download results
            raw_results = self.download_results(job_id)
            
            if not raw_results:
                return {
                    'status': 'failed',
                    'error': 'Failed to download antiSMASH results',
                    'job_id': job_id,
                    'our_predictions': our_predictions
                }
            
            # Parse results
            antismash_results = self.parse_antismash_results(raw_results)
            
            # Cache results
            self.cache[seq_hash] = {
                'job_id': job_id,
                'antismash_results': antismash_results,
                'timestamp': time.time()
            }
            self._save_cache()
        
        # Compare predictions
        comparison = self.compare_predictions(our_predictions, antismash_results)
        
        # Build final result
        result = {
            'status': 'completed',
            'job_id': job_id,
            'sequence_hash': seq_hash,
            'our_predictions': our_predictions,
            'antismash_results': antismash_results,
            'comparison': comparison,
            'validation_summary': {
                'our_bgc_count': comparison['our_count'],
                'antismash_bgc_count': comparison['antismash_count'],
                'agreement_rate': comparison['agreement_rate'],
                'validation_status': comparison['validation_status']
            }
        }
        
        print("\n" + "=" * 60)
        print("Comparison Results")
        print("=" * 60)
        print(f"Our predictions: {comparison['our_count']} BGCs")
        print(f"antiSMASH found: {comparison['antismash_count']} BGCs")
        print(f"Agreement rate: {comparison['agreement_rate']}%")
        print(f"Validation status: {comparison['validation_status'].upper()}")
        
        return result


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Compare BGC predictions with antiSMASH"
    )
    parser.add_argument("--input", "-i", required=True,
                       help="Input FASTA file")
    parser.add_argument("--predictions", "-p", required=True,
                       help="JSON file with our BGC predictions")
    parser.add_argument("--output", "-o", required=True,
                       help="Output JSON file for comparison results")
    parser.add_argument("--no-cache", action="store_true",
                       help="Disable caching (force new antiSMASH submission)")
    parser.add_argument("--email", default="bgcqdr@example.com",
                       help="Email for antiSMASH notifications")
    
    args = parser.parse_args()
    
    # Load our predictions
    with open(args.predictions) as f:
        predictions_data = json.load(f)
    
    # Extract predictions list
    if isinstance(predictions_data, dict):
        our_predictions = predictions_data.get('top_candidates', [])
    else:
        our_predictions = predictions_data
    
    # Run comparison
    comparator = AntiSMASHComparator()
    results = comparator.run_comparison(
        args.input,
        our_predictions,
        use_cache=not args.no_cache
    )
    
    # Save results
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n[OK] Comparison results saved to {args.output}")
    
    if results['status'] == 'completed':
        return 0
    else:
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
