"""
Stage-2 Gene Miner: ORF Caller Wrapper
=======================================
Wrapper for Prodigal gene prediction on Phase-1 regions.

Requirements: Prodigal must be installed and in PATH
Install: conda install -c bioconda prodigal
"""

import os
import sys
import subprocess
from pathlib import Path
import argparse

def check_prodigal():
    """Check if Prodigal is available."""
    try:
        result = subprocess.run(['prodigal', '-v'], 
                              capture_output=True, text=True, check=False)
        if result.returncode == 0:
            version = result.stderr.split('\n')[0] if result.stderr else "Unknown version"
            print(f"✅ Prodigal found: {version}")
            return True
    except FileNotFoundError:
        pass
    
    print("❌ Prodigal not found!")
    print("   Install with: conda install -c bioconda prodigal")
    return False

def run_prodigal(input_fasta: str, output_dir: str, threads: int = 4):
    """
    Run Prodigal on input FASTA regions.
    
    Args:
        input_fasta: Input FASTA with Phase-1 regions
        output_dir: Output directory for results
        threads: Number of threads (not directly supported by Prodigal)
    
    Returns:
        Paths to output files
    """
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Output files
    proteins_faa = output_path / "regions_proteins.faa"
    nucleotides_fna = output_path / "regions_nucleotides.fna"
    genes_gbk = output_path / "regions_genes.gbk"
    
    print(f"Running Prodigal on {input_fasta}...")
    print(f"  Output directory: {output_dir}")
    
    # Prodigal command (metagenomic mode for fragments)
    cmd = [
        'prodigal',
        '-i', input_fasta,
        '-a', str(proteins_faa),     # amino acid sequences
        '-d', str(nucleotides_fna),  # nucleotide sequences
        '-o', str(genes_gbk),        # GenBank format
        '-p', 'meta',                # metagenomic mode (good for fragments)
        '-q'                         # quiet mode
    ]
    
    print(f"  Command: {' '.join(cmd)}")
    
    # Run Prodigal
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Count genes
        gene_count = 0
        if proteins_faa.exists():
            with open(proteins_faa) as f:
                gene_count = sum(1 for line in f if line.startswith('>'))
        
        print(f"  ✅ Success: {gene_count} genes predicted")
        print(f"     Proteins:    {proteins_faa}")
        print(f"     Nucleotides: {nucleotides_fna}")
        print(f"     GenBank:     {genes_gbk}")
        
        return {
            'proteins': str(proteins_faa),
            'nucleotides': str(nucleotides_fna),
            'genbank': str(genes_gbk),
            'gene_count': gene_count
        }
        
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Prodigal failed!")
        print(f"     Return code: {e.returncode}")
        print(f"     Error output: {e.stderr}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Run Prodigal gene prediction on Phase-1 regions")
    parser.add_argument("--input", "-i", required=True,
                       help="Input FASTA file with Phase-1 regions")
    parser.add_argument("--output-dir", "-o", required=True,
                       help="Output directory for Prodigal results")
    parser.add_argument("--threads", "-t", type=int, default=4,
                       help="Number of threads (default: 4)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Stage-2: ORF Calling with Prodigal")
    print("=" * 60)
    
    # Check if Prodigal is available
    if not check_prodigal():
        sys.exit(1)
    
    # Check input file
    if not os.path.exists(args.input):
        print(f"❌ Input file not found: {args.input}")
        sys.exit(1)
    
    # Run Prodigal
    try:
        results = run_prodigal(args.input, args.output_dir, args.threads)
        
        print(f"\n✅ ORF calling complete!")
        print(f"   Genes predicted: {results['gene_count']}")
        print(f"   Ready for domain annotation")
        
    except Exception as e:
        print(f"\n❌ ORF calling failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()