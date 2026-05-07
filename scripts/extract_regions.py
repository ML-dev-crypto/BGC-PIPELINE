"""
Stage-2 Gene Miner: FASTA Region Extractor
===========================================
Extract Phase-1 candidate regions from genome FASTA files.

Input:  Phase-1 TSV results + original genome FASTA
Output: FASTA file with candidate regions ready for ORF calling
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd
from Bio import SeqIO

def load_phase1_results(tsv_path: str) -> pd.DataFrame:
    """Load Phase-1 scanning results."""
    df = pd.read_csv(tsv_path, sep='\t')
    print(f"Loaded {len(df)} Phase-1 candidate regions")
    return df

def load_genome_sequences(fasta_path: str) -> Dict[str, str]:
    """Load genome sequences into memory."""
    print(f"Loading genome sequences from {fasta_path}...")
    sequences = {}
    for record in SeqIO.parse(fasta_path, "fasta"):
        sequences[record.id] = str(record.seq).upper()
    print(f"  Loaded {len(sequences)} contigs")
    return sequences

def extract_regions(phase1_df: pd.DataFrame, 
                   genome_seqs: Dict[str, str], 
                   output_path: str,
                   extend_bp: int = 5000):
    """
    Extract Phase-1 regions from genome sequences.
    
    Args:
        phase1_df: DataFrame with contig_id, start, end, score columns
        genome_seqs: Dictionary of contig_id -> sequence
        output_path: Output FASTA path
        extend_bp: Extend regions by this many bp on each side
    """
    
    print(f"Extracting regions with {extend_bp} bp extension...")
    
    extracted_count = 0
    failed_count = 0
    
    with open(output_path, 'w') as f:
        for idx, row in phase1_df.iterrows():
            contig_id = row['contig_id']
            start = int(row['start'])
            end = int(row['end'])
            score = float(row['mean_score'] if 'mean_score' in row else row['max_score'])
            
            # Check if contig exists
            if contig_id not in genome_seqs:
                print(f"  Warning: Contig {contig_id} not found in genome")
                failed_count += 1
                continue
            
            sequence = genome_seqs[contig_id]
            seq_len = len(sequence)
            
            # Extend region (but stay within contig bounds)
            extended_start = max(0, start - extend_bp)
            extended_end = min(seq_len, end + extend_bp)
            
            # Extract region
            region_seq = sequence[extended_start:extended_end]
            
            if len(region_seq) < 1000:  # Skip very short regions
                failed_count += 1
                continue
            
            # Create FASTA header with metadata
            header = f">{contig_id}|start={extended_start}|end={extended_end}|score={score:.4f}|length={len(region_seq)}"
            
            # Write to file
            f.write(header + '\n')
            f.write(region_seq + '\n')
            
            extracted_count += 1
    
    print(f"  Extracted: {extracted_count} regions")
    print(f"  Failed: {failed_count} regions")
    print(f"  Output: {output_path}")
    
    return extracted_count

def main():
    parser = argparse.ArgumentParser(description="Extract Phase-1 regions from genome FASTA")
    parser.add_argument("--phase1-results", "-p", required=True,
                       help="Phase-1 TSV results file")
    parser.add_argument("--genome-fasta", "-g", required=True,
                       help="Original genome FASTA file")
    parser.add_argument("--output", "-o", required=True,
                       help="Output FASTA file for extracted regions")
    parser.add_argument("--extend", "-e", type=int, default=5000,
                       help="Extend regions by N bp on each side (default: 5000)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Stage-2: FASTA Region Extractor")
    print("=" * 60)
    
    # Load data
    phase1_df = load_phase1_results(args.phase1_results)
    genome_seqs = load_genome_sequences(args.genome_fasta)
    
    # Extract regions
    extracted_count = extract_regions(
        phase1_df, genome_seqs, args.output, args.extend
    )
    
    if extracted_count > 0:
        print(f"\n✅ Success: {extracted_count} regions extracted")
        print(f"   Ready for ORF calling: {args.output}")
    else:
        print(f"\n❌ Error: No regions extracted")
        sys.exit(1)

if __name__ == "__main__":
    main()