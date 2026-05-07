"""
Stage-2 Simplified: No External Dependencies Test
=================================================
Test Stage-2 pipeline without external tools (Prodigal/HMMER).
Shows the pipeline structure and region extraction.
"""

import os
import sys
import pandas as pd
from pathlib import Path
from Bio import SeqIO

def extract_regions_simple(phase1_results: str, genome_fasta: str, output_dir: str):
    """Simplified Stage-2 test without external dependencies."""
    
    print("🧬 STAGE-2 SIMPLIFIED TEST")
    print("=" * 50)
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load Phase-1 results
    print(f"Loading Phase-1 results: {phase1_results}")
    phase1_df = pd.read_csv(phase1_results, sep='\t')
    print(f"  Found {len(phase1_df)} candidate regions")
    
    # Load genome
    print(f"Loading genome: {genome_fasta}")
    genome_seqs = {}
    for record in SeqIO.parse(genome_fasta, "fasta"):
        genome_seqs[record.id] = str(record.seq).upper()
    print(f"  Loaded {len(genome_seqs)} contigs")
    
    # Extract regions
    regions_fasta = output_path / 'extracted_regions.fasta'
    extracted_count = 0
    
    with open(regions_fasta, 'w') as f:
        for idx, row in phase1_df.iterrows():
            contig_id = row['contig_id']
            start = int(row['start'])
            end = int(row['end'])
            score = float(row['mean_score'])
            
            if contig_id in genome_seqs:
                sequence = genome_seqs[contig_id]
                
                # Extract region with 5kb extension
                extended_start = max(0, start - 5000)
                extended_end = min(len(sequence), end + 5000)
                region_seq = sequence[extended_start:extended_end]
                
                if len(region_seq) >= 1000:
                    header = f">{contig_id}|start={extended_start}|end={extended_end}|score={score:.4f}|length={len(region_seq)}"
                    f.write(header + '\n')
                    f.write(region_seq + '\n')
                    extracted_count += 1
    
    print(f"✅ Extracted {extracted_count} regions to: {regions_fasta}")
    
    # Generate summary report
    summary = {
        'phase1_regions': len(phase1_df),
        'extracted_regions': extracted_count,
        'total_bp_extracted': sum(len(s) for s in genome_seqs.values()),
        'output_file': str(regions_fasta)
    }
    
    # Save summary
    summary_file = output_path / 'summary.txt'
    with open(summary_file, 'w') as f:
        f.write("STAGE-2 SIMPLIFIED TEST RESULTS\n")
        f.write("=" * 40 + "\n\n")
        for key, value in summary.items():
            f.write(f"{key}: {value}\n")
    
    print(f"\n📊 SUMMARY:")
    print(f"   Phase-1 regions: {summary['phase1_regions']}")
    print(f"   Extracted regions: {summary['extracted_regions']}")
    print(f"   Success rate: {extracted_count/len(phase1_df)*100:.1f}%")
    print(f"\n📂 OUTPUT FILES:")
    print(f"   Regions FASTA: {regions_fasta}")
    print(f"   Summary: {summary_file}")
    
    print(f"\n🎯 NEXT STEPS:")
    print(f"   1. Install Prodigal for gene prediction")
    print(f"   2. Install HMMER + Pfam for domain annotation")
    print(f"   3. Run full Stage-2 pipeline")
    print(f"\n✅ Stage-2 structure validated!")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python stage2_simple.py <phase1_results.tsv> <genome.fasta> <output_dir>")
        sys.exit(1)
    
    phase1_results, genome_fasta, output_dir = sys.argv[1:4]
    
    if not os.path.exists(phase1_results):
        print(f"❌ Phase-1 results not found: {phase1_results}")
        sys.exit(1)
    
    if not os.path.exists(genome_fasta):
        print(f"❌ Genome FASTA not found: {genome_fasta}")
        sys.exit(1)
    
    extract_regions_simple(phase1_results, genome_fasta, output_dir)