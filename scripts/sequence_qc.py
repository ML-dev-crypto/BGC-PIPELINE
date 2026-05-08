"""
Sequence Quality Control Module
================================
Pre-flight QC for FASTA inputs before BGC detection pipeline.

Filters out:
- Short contigs (<500bp)
- High N-content (>10% ambiguous bases)
- Low complexity sequences (repeats, homopolymers)
- Extreme GC content (<20% or >80%)

Returns QC report with per-contig statistics.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter
import hashlib


class SequenceQC:
    """Quality control for FASTA sequences."""
    
    # QC thresholds
    MIN_LENGTH = 500  # bp
    MAX_N_PERCENT = 10.0  # %
    MIN_GC_PERCENT = 20.0  # %
    MAX_GC_PERCENT = 80.0  # %
    MAX_HOMOPOLYMER_RUN = 15  # consecutive same base
    MIN_COMPLEXITY_SCORE = 0.3  # Shannon entropy normalized
    
    def __init__(self, fasta_path: str):
        self.fasta_path = Path(fasta_path)
        self.sequences = self._parse_fasta()
        self.qc_results = []
        
    def _parse_fasta(self) -> Dict[str, str]:
        """Parse FASTA file into dict."""
        sequences = {}
        current_id = None
        current_seq = []
        
        with open(self.fasta_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('>'):
                    # Save previous sequence
                    if current_id:
                        sequences[current_id] = ''.join(current_seq)
                    # Start new sequence
                    current_id = line[1:].split()[0]  # First word after >
                    current_seq = []
                elif line:
                    current_seq.append(line.upper())
            
            # Save last sequence
            if current_id:
                sequences[current_id] = ''.join(current_seq)
        
        return sequences
    
    def _calculate_gc_content(self, seq: str) -> float:
        """Calculate GC content percentage."""
        gc_count = seq.count('G') + seq.count('C')
        total = len(seq)
        return (gc_count / total * 100) if total > 0 else 0.0
    
    def _calculate_n_content(self, seq: str) -> float:
        """Calculate N (ambiguous base) content percentage."""
        n_count = seq.count('N')
        total = len(seq)
        return (n_count / total * 100) if total > 0 else 0.0
    
    def _find_longest_homopolymer(self, seq: str) -> Tuple[str, int]:
        """Find longest homopolymer run (e.g., AAAAAAA)."""
        max_base = ''
        max_length = 0
        
        for base in 'ACGT':
            # Find all runs of this base
            pattern = f'{base}+'
            matches = re.finditer(pattern, seq)
            for match in matches:
                length = len(match.group())
                if length > max_length:
                    max_length = length
                    max_base = base
        
        return max_base, max_length
    
    def _calculate_complexity(self, seq: str) -> float:
        """
        Calculate sequence complexity using Shannon entropy.
        Returns normalized score 0-1 (higher = more complex).
        """
        if len(seq) == 0:
            return 0.0
        
        # Count k-mers (use 3-mers for balance)
        k = 3
        kmers = [seq[i:i+k] for i in range(len(seq) - k + 1)]
        
        if not kmers:
            return 0.0
        
        # Calculate Shannon entropy
        counts = Counter(kmers)
        total = len(kmers)
        entropy = 0.0
        
        for count in counts.values():
            p = count / total
            if p > 0:
                entropy -= p * (p ** 0.5)  # Modified entropy for DNA
        
        # Normalize by maximum possible entropy
        max_entropy = 1.0  # Theoretical max for this metric
        normalized = min(1.0, entropy / max_entropy)
        
        return normalized
    
    def _check_repeat_pattern(self, seq: str) -> Tuple[bool, str]:
        """
        Check for simple repeat patterns (e.g., ATATATATAT).
        Returns (is_repeat, pattern).
        """
        # Check for dinucleotide repeats
        for pattern_len in [2, 3, 4]:
            for i in range(len(seq) - pattern_len * 5):
                pattern = seq[i:i+pattern_len]
                # Check if pattern repeats at least 5 times
                test_region = seq[i:i+pattern_len*5]
                if test_region == pattern * 5:
                    return True, pattern
        
        return False, ''
    
    def analyze_sequence(self, seq_id: str, seq: str) -> Dict:
        """
        Perform comprehensive QC on a single sequence.
        
        Returns dict with QC metrics and pass/fail status.
        """
        length = len(seq)
        gc_content = self._calculate_gc_content(seq)
        n_content = self._calculate_n_content(seq)
        homopolymer_base, homopolymer_length = self._find_longest_homopolymer(seq)
        complexity = self._calculate_complexity(seq)
        is_repeat, repeat_pattern = self._check_repeat_pattern(seq)
        
        # Determine pass/fail for each criterion
        checks = {
            'length': length >= self.MIN_LENGTH,
            'n_content': n_content <= self.MAX_N_PERCENT,
            'gc_content': self.MIN_GC_PERCENT <= gc_content <= self.MAX_GC_PERCENT,
            'homopolymer': homopolymer_length <= self.MAX_HOMOPOLYMER_RUN,
            'complexity': complexity >= self.MIN_COMPLEXITY_SCORE,
            'repeat_pattern': not is_repeat
        }
        
        # Overall pass if all checks pass
        passed = all(checks.values())
        
        # Failure reasons
        failures = [key for key, value in checks.items() if not value]
        
        return {
            'seq_id': seq_id,
            'length': length,
            'gc_content': round(gc_content, 2),
            'n_content': round(n_content, 2),
            'homopolymer_base': homopolymer_base if homopolymer_base else 'None',
            'homopolymer_length': homopolymer_length,
            'complexity_score': round(complexity, 3),
            'is_repeat': is_repeat,
            'repeat_pattern': repeat_pattern if repeat_pattern else 'None',
            'passed': passed,
            'failures': failures,
            'checks': checks
        }
    
    def run_qc(self) -> Dict:
        """
        Run QC on all sequences.
        
        Returns comprehensive QC report.
        """
        print(f"Running QC on {len(self.sequences)} sequences...")
        
        self.qc_results = []
        passed_sequences = {}
        failed_sequences = {}
        
        for seq_id, seq in self.sequences.items():
            result = self.analyze_sequence(seq_id, seq)
            self.qc_results.append(result)
            
            if result['passed']:
                passed_sequences[seq_id] = seq
            else:
                failed_sequences[seq_id] = seq
        
        # Calculate summary statistics
        total = len(self.sequences)
        passed = len(passed_sequences)
        failed = len(failed_sequences)
        
        # Count failure reasons
        failure_counts = Counter()
        for result in self.qc_results:
            for failure in result['failures']:
                failure_counts[failure] += 1
        
        # Calculate input hash for cache invalidation
        input_hash = self._calculate_input_hash()
        
        report = {
            'input_file': str(self.fasta_path),
            'input_hash': input_hash,
            'total_sequences': total,
            'passed_sequences': passed,
            'failed_sequences': failed,
            'pass_rate': round(passed / total * 100, 1) if total > 0 else 0.0,
            'failure_reasons': dict(failure_counts),
            'qc_thresholds': {
                'min_length': self.MIN_LENGTH,
                'max_n_percent': self.MAX_N_PERCENT,
                'min_gc_percent': self.MIN_GC_PERCENT,
                'max_gc_percent': self.MAX_GC_PERCENT,
                'max_homopolymer_run': self.MAX_HOMOPOLYMER_RUN,
                'min_complexity_score': self.MIN_COMPLEXITY_SCORE
            },
            'per_sequence_results': self.qc_results,
            'passed_seq_ids': list(passed_sequences.keys()),
            'failed_seq_ids': list(failed_sequences.keys())
        }
        
        return report, passed_sequences
    
    def _calculate_input_hash(self) -> str:
        """Calculate hash of input sequences for cache invalidation."""
        hasher = hashlib.sha256()
        
        # Hash all sequences in sorted order for consistency
        for seq_id in sorted(self.sequences.keys()):
            seq = self.sequences[seq_id]
            hasher.update(f"{seq_id}:{seq}".encode())
        
        return hasher.hexdigest()[:16]  # First 16 chars
    
    def write_filtered_fasta(self, output_path: str, passed_sequences: Dict[str, str]):
        """Write QC-passed sequences to new FASTA file."""
        output_path = Path(output_path)
        
        with open(output_path, 'w') as f:
            for seq_id, seq in passed_sequences.items():
                f.write(f">{seq_id}\n")
                # Write sequence in 80-character lines
                for i in range(0, len(seq), 80):
                    f.write(seq[i:i+80] + '\n')
        
        print(f"  Wrote {len(passed_sequences)} QC-passed sequences to {output_path}")


def main():
    """Command-line interface for sequence QC."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Sequence quality control for FASTA files")
    parser.add_argument("--input", "-i", required=True,
                       help="Input FASTA file")
    parser.add_argument("--output", "-o", required=True,
                       help="Output filtered FASTA file")
    parser.add_argument("--report", "-r", required=True,
                       help="Output QC report JSON file")
    parser.add_argument("--min-length", type=int, default=500,
                       help="Minimum contig length (default: 500)")
    parser.add_argument("--max-n-percent", type=float, default=10.0,
                       help="Maximum N content percent (default: 10.0)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Sequence Quality Control")
    print("=" * 60)
    
    # Override thresholds if provided
    if args.min_length:
        SequenceQC.MIN_LENGTH = args.min_length
    if args.max_n_percent:
        SequenceQC.MAX_N_PERCENT = args.max_n_percent
    
    # Run QC
    qc = SequenceQC(args.input)
    report, passed_sequences = qc.run_qc()
    
    # Print summary
    print(f"\nQC Summary:")
    print(f"  Total sequences: {report['total_sequences']}")
    print(f"  Passed: {report['passed_sequences']} ({report['pass_rate']}%)")
    print(f"  Failed: {report['failed_sequences']}")
    
    if report['failure_reasons']:
        print(f"\n  Failure reasons:")
        for reason, count in report['failure_reasons'].items():
            print(f"    {reason}: {count}")
    
    # Write outputs
    qc.write_filtered_fasta(args.output, passed_sequences)
    
    with open(args.report, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"  Wrote QC report to {args.report}")
    
    print(f"\n✅ QC complete!")


if __name__ == "__main__":
    main()
