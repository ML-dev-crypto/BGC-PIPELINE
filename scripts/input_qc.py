"""
Input Quality Control Module
=============================
Comprehensive QC for FASTA inputs with strict validation.

Rejects:
- Contigs shorter than 500bp
- Contigs with >10% N bases
- Low-complexity sequences (entropy check)

Aborts pipeline if >80% of contigs fail QC.
"""

import hashlib
import math
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord


class InputQC:
    """Input quality control with strict validation."""
    
    # QC thresholds
    MIN_LENGTH = 500  # bp
    MAX_N_PERCENT = 10.0  # %
    MIN_ENTROPY = 1.5  # bits per position (sliding window)
    WINDOW_SIZE = 100  # bp for entropy calculation
    ABORT_THRESHOLD = 80.0  # % - abort if more than this fail
    
    def __init__(self, fasta_path: str):
        """
        Initialize QC module.
        
        Args:
            fasta_path: Path to input FASTA file
        """
        self.fasta_path = Path(fasta_path)
        if not self.fasta_path.exists():
            raise FileNotFoundError(f"FASTA file not found: {fasta_path}")
        
        self.sequences = {}
        self.qc_results = []
        
    def _parse_fasta(self) -> Dict[str, SeqRecord]:
        """Parse FASTA file using BioPython."""
        sequences = {}
        
        with open(self.fasta_path) as f:
            for record in SeqIO.parse(f, "fasta"):
                sequences[record.id] = record
        
        return sequences
    
    def _calculate_n_content(self, seq: str) -> float:
        """Calculate percentage of N bases."""
        n_count = seq.upper().count('N')
        return (n_count / len(seq) * 100) if len(seq) > 0 else 0.0
    
    def _calculate_shannon_entropy(self, seq: str) -> float:
        """
        Calculate Shannon entropy for a sequence.
        
        Returns entropy in bits per position.
        Higher entropy = more complex sequence.
        """
        if len(seq) == 0:
            return 0.0
        
        # Count base frequencies
        counts = Counter(seq.upper())
        total = len(seq)
        
        # Calculate Shannon entropy
        entropy = 0.0
        for count in counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
        
        return entropy
    
    def _sliding_window_entropy(self, seq: str, window_size: int = 100) -> float:
        """
        Calculate minimum entropy across sliding windows.
        
        Returns the minimum entropy found (worst case).
        Low minimum entropy indicates low-complexity regions.
        """
        if len(seq) < window_size:
            return self._calculate_shannon_entropy(seq)
        
        min_entropy = float('inf')
        
        for i in range(len(seq) - window_size + 1):
            window = seq[i:i+window_size]
            entropy = self._calculate_shannon_entropy(window)
            min_entropy = min(min_entropy, entropy)
        
        return min_entropy
    
    def _detect_sequence_origin(self, contig_id: str, seq: str) -> str:
        """
        Detect if sequence is synthetic/marker based on ID and characteristics.
        
        Returns: 'synthetic', 'marker', 'environmental', or 'unknown'
        """
        contig_lower = contig_id.lower()
        
        # Check for synthetic/marker keywords in ID
        synthetic_keywords = ['synthetic', 'marker', 'engineered', 'artificial', 'control']
        marker_keywords = ['marker', 'positive_control', 'reference', 'standard']
        
        if any(kw in contig_lower for kw in marker_keywords):
            return 'marker'
        elif any(kw in contig_lower for kw in synthetic_keywords):
            return 'synthetic'
        elif 'env_sample' in contig_lower or 'environmental' in contig_lower:
            return 'environmental'
        
        # Check for highly repetitive patterns (common in synthetic sequences)
        # Look for tandem repeats of 3-6bp motifs
        for motif_len in [3, 4, 5, 6]:
            for i in range(len(seq) - motif_len * 10):
                motif = seq[i:i+motif_len]
                # Check if motif repeats 10+ times consecutively
                repeat_region = motif * 10
                if repeat_region in seq[i:i+motif_len*15]:
                    return 'synthetic'
        
        return 'unknown'
    
    def _check_contig(self, contig_id: str, record: SeqRecord) -> Dict:
        """
        Perform QC checks on a single contig.
        
        Returns dict with QC results and pass/fail status.
        """
        seq = str(record.seq).upper()
        length = len(seq)
        
        # Calculate metrics
        n_content = self._calculate_n_content(seq)
        min_entropy = self._sliding_window_entropy(seq, self.WINDOW_SIZE)
        
        # Detect sequence origin
        seq_origin = self._detect_sequence_origin(contig_id, seq)
        
        # Determine pass/fail for each criterion
        checks = {
            'length': length >= self.MIN_LENGTH,
            'n_content': n_content <= self.MAX_N_PERCENT,
            'complexity': min_entropy >= self.MIN_ENTROPY
        }
        
        # Overall pass if all checks pass
        passed = all(checks.values())
        
        # Failure reasons
        failure_reasons = []
        if not checks['length']:
            failure_reasons.append(f'too_short_{length}bp')
        if not checks['n_content']:
            failure_reasons.append(f'high_n_content_{n_content:.1f}%')
        if not checks['complexity']:
            failure_reasons.append(f'low_complexity_entropy_{min_entropy:.2f}')
        
        return {
            'contig_id': contig_id,
            'length': length,
            'n_content': round(n_content, 2),
            'min_entropy': round(min_entropy, 3),
            'sequence_origin': seq_origin,
            'passed': passed,
            'failure_reasons': failure_reasons,
            'checks': checks
        }
    
    def run_qc(self) -> Tuple[Dict, List[SeqRecord]]:
        """
        Run QC on all contigs.
        
        Returns:
            (qc_report_dict, passed_sequences_list)
        
        Raises:
            ValueError: If >80% of contigs fail QC (abort pipeline)
        """
        print(f"Running Input QC on {self.fasta_path}...")
        
        # Parse FASTA
        self.sequences = self._parse_fasta()
        total_contigs = len(self.sequences)
        
        print(f"  Total contigs: {total_contigs}")
        
        # Run QC on each contig
        passed_sequences = []
        failed_sequences = []
        
        for contig_id, record in self.sequences.items():
            result = self._check_contig(contig_id, record)
            self.qc_results.append(result)
            
            if result['passed']:
                passed_sequences.append(record)
            else:
                failed_sequences.append(result)
        
        # Calculate statistics
        passed_count = len(passed_sequences)
        failed_count = len(failed_sequences)
        fail_rate = (failed_count / total_contigs * 100) if total_contigs > 0 else 0.0
        
        # Count failure reasons
        failure_reason_counts = Counter()
        for result in self.qc_results:
            for reason in result['failure_reasons']:
                # Extract just the reason type (before underscore)
                reason_type = reason.split('_')[0] + '_' + reason.split('_')[1] if '_' in reason else reason
                failure_reason_counts[reason_type] += 1
        
        # Count sequence origins
        origin_counts = Counter()
        for result in self.qc_results:
            origin_counts[result['sequence_origin']] += 1
        
        # CRITICAL: Abort if >80% fail
        if fail_rate > self.ABORT_THRESHOLD:
            raise ValueError(
                f"[ERROR] QC ABORT: {fail_rate:.1f}% of contigs failed quality checks.\n"
                f"   Input quality too low to proceed with pipeline.\n"
                f"   Passed: {passed_count}/{total_contigs}\n"
                f"   Failed: {failed_count}/{total_contigs}\n"
                f"   Failure reasons: {dict(failure_reason_counts)}\n"
                f"   Threshold: >{self.ABORT_THRESHOLD}% failure rate"
            )
        
        # Build QC report
        qc_report = {
            'input_file': str(self.fasta_path),
            'total_contigs': total_contigs,
            'passed': passed_count,
            'failed': failed_count,
            'pass_rate': round(100 - fail_rate, 1),
            'fail_rate': round(fail_rate, 1),
            'failure_reasons': dict(failure_reason_counts),
            'sequence_origins': dict(origin_counts),
            'qc_thresholds': {
                'min_length_bp': self.MIN_LENGTH,
                'max_n_percent': self.MAX_N_PERCENT,
                'min_entropy_bits': self.MIN_ENTROPY,
                'entropy_window_size_bp': self.WINDOW_SIZE,
                'abort_threshold_percent': self.ABORT_THRESHOLD
            },
            'per_contig_results': self.qc_results
        }
        
        print(f"  [OK] QC Complete:")
        print(f"     Passed: {passed_count} ({100-fail_rate:.1f}%)")
        print(f"     Failed: {failed_count} ({fail_rate:.1f}%)")
        
        # Warn about synthetic/marker sequences
        synthetic_count = origin_counts.get('synthetic', 0) + origin_counts.get('marker', 0)
        if synthetic_count > 0:
            print(f"  [WARN]  WARNING: Detected {synthetic_count} synthetic/marker sequences")
            print(f"     These may inflate BGC counts in downstream analysis")
            print(f"     Origins: {dict(origin_counts)}")
        
        if failure_reason_counts:
            print(f"     Failure reasons:")
            for reason, count in failure_reason_counts.most_common():
                print(f"       {reason}: {count}")
        
        return qc_report, passed_sequences
    
    def write_filtered_fasta(self, output_path: str, passed_sequences: List[SeqRecord]):
        """Write QC-passed sequences to new FASTA file."""
        output_path = Path(output_path)
        
        with open(output_path, 'w') as f:
            SeqIO.write(passed_sequences, f, "fasta")
        
        print(f"  Wrote {len(passed_sequences)} QC-passed contigs to {output_path}")


def main():
    """Command-line interface for input QC."""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(
        description="Input quality control for FASTA files with strict validation"
    )
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
    parser.add_argument("--min-entropy", type=float, default=1.5,
                       help="Minimum entropy bits (default: 1.5)")
    parser.add_argument("--exclude-synthetic", action="store_true",
                       help="Exclude synthetic/marker sequences from output (recommended for real analysis)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Input Quality Control")
    print("=" * 60)
    
    # Override thresholds if provided
    if args.min_length:
        InputQC.MIN_LENGTH = args.min_length
    if args.max_n_percent:
        InputQC.MAX_N_PERCENT = args.max_n_percent
    if args.min_entropy:
        InputQC.MIN_ENTROPY = args.min_entropy
    
    try:
        # Run QC
        qc = InputQC(args.input)
        qc_report, passed_sequences = qc.run_qc()
        
        # Filter out synthetic/marker sequences if requested
        if args.exclude_synthetic:
            original_count = len(passed_sequences)
            # Get sequence origins from QC results
            synthetic_ids = {
                result['contig_id'] 
                for result in qc.qc_results 
                if result['sequence_origin'] in ['synthetic', 'marker']
            }
            # Filter sequences
            passed_sequences = [
                seq for seq in passed_sequences 
                if seq.id not in synthetic_ids
            ]
            filtered_count = original_count - len(passed_sequences)
            if filtered_count > 0:
                print(f"  [INFO] Excluded {filtered_count} synthetic/marker sequences")
                print(f"     Remaining: {len(passed_sequences)} environmental sequences")
        
        # Write outputs
        qc.write_filtered_fasta(args.output, passed_sequences)
        
        with open(args.report, 'w') as f:
            json.dump(qc_report, f, indent=2)
        print(f"  Wrote QC report to {args.report}")
        
        print(f"\n[OK] Input QC complete!")
        return 0
        
    except ValueError as e:
        # QC abort exception
        print(f"\n{e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Input QC failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
