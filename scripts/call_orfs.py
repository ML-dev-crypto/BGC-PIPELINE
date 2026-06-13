"""
Stage-2 Gene Miner: ORF Caller Wrapper
=======================================
Wrapper for Prodigal gene prediction on Phase-1 regions.

Prodigal runs inside WSL (Windows Subsystem for Linux) so that it
shares the same Linux environment as HMMER.  Windows paths are
automatically converted to WSL mount paths (/mnt/c/...).

Requirements: prodigal installed in WSL
    wsl -- bash -c "conda install -c bioconda prodigal"
  or
    wsl -- bash -c "sudo apt install prodigal"
"""

import os
import sys
import subprocess
from pathlib import Path, PurePosixPath
import argparse


# ---------------------------------------------------------------------------
# WSL path helpers
# ---------------------------------------------------------------------------

def win_to_wsl_path(windows_path: str) -> str:
    """
    Convert a Windows absolute path to its WSL /mnt/<drive>/... equivalent.

    Examples:
        D:\\web.dv\\results  ->  /mnt/d/web.dv/results
        C:\\Users\\foo\\bar  ->  /mnt/c/Users/foo/bar
    """
    p = Path(windows_path).resolve()
    drive = p.drive          # e.g. 'D:'
    rest = p.as_posix()[len(drive):]   # everything after 'D:'
    drive_letter = drive.rstrip(':').lower()
    return f"/mnt/{drive_letter}{rest}"


def check_prodigal():
    """Check if Prodigal is available inside WSL."""
    try:
        result = subprocess.run(
            ['wsl', '--', 'prodigal', '-v'],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            version = result.stderr.split('\n')[0] if result.stderr else "unknown version"
            print(f"[OK] Prodigal found in WSL: {version}")
            return True
    except FileNotFoundError:
        pass

    print("[ERROR] Prodigal not found in WSL!")
    print("   Install with:  wsl -- conda install -c bioconda prodigal")
    print("            or:  wsl -- sudo apt install prodigal")
    return False


def run_prodigal(input_fasta: str, output_dir: str, threads: int = 4):
    """
    Run Prodigal inside WSL on input FASTA regions.

    Args:
        input_fasta: Windows path to input FASTA
        output_dir:  Windows path to output directory
        threads:     Unused (Prodigal is single-threaded), kept for API compat

    Returns:
        Dict with Windows paths to output files and gene_count.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Windows output paths
    proteins_faa   = output_path / "regions_proteins.faa"
    nucleotides_fna = output_path / "regions_nucleotides.fna"
    genes_gbk      = output_path / "regions_genes.gbk"

    print(f"Running Prodigal (WSL) on {input_fasta}...")
    print(f"  Output directory: {output_dir}")

    # Convert Windows paths to WSL /mnt/... paths
    wsl_input      = win_to_wsl_path(input_fasta)
    wsl_proteins   = win_to_wsl_path(str(proteins_faa))
    wsl_nucl       = win_to_wsl_path(str(nucleotides_fna))
    wsl_gbk        = win_to_wsl_path(str(genes_gbk))

    cmd = [
        'wsl', '--',
        'prodigal',
        '-i', wsl_input,
        '-a', wsl_proteins,    # amino acid sequences
        '-d', wsl_nucl,        # nucleotide sequences
        '-o', wsl_gbk,         # GenBank format
        '-p', 'meta',          # metagenomic mode (good for fragments)
        '-q',                  # quiet mode
    ]

    print(f"  Command: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)

        gene_count = 0
        if proteins_faa.exists():
            with open(proteins_faa) as f:
                gene_count = sum(1 for line in f if line.startswith('>'))

        print(f"  [OK] Success: {gene_count} genes predicted")
        print(f"     Proteins:    {proteins_faa}")
        print(f"     Nucleotides: {nucleotides_fna}")
        print(f"     GenBank:     {genes_gbk}")

        return {
            'proteins': str(proteins_faa),
            'nucleotides': str(nucleotides_fna),
            'genbank': str(genes_gbk),
            'gene_count': gene_count,
        }

    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Prodigal (WSL) failed!")
        print(f"     Return code: {e.returncode}")
        print(f"     Stderr: {e.stderr[:400]}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Run Prodigal gene prediction (via WSL) on Phase-1 regions"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Input FASTA file with Phase-1 regions")
    parser.add_argument("--output-dir", "-o", required=True,
                        help="Output directory for Prodigal results")
    parser.add_argument("--threads", "-t", type=int, default=4,
                        help="Number of threads (default: 4)")

    args = parser.parse_args()

    print("=" * 60)
    print("Stage-2: ORF Calling with Prodigal (WSL)")
    print("=" * 60)

    if not check_prodigal():
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"[ERROR] Input file not found: {args.input}")
        sys.exit(1)

    try:
        results = run_prodigal(args.input, args.output_dir, args.threads)
        print(f"\n[OK] ORF calling complete!")
        print(f"   Genes predicted: {results['gene_count']}")
        print(f"   Ready for domain annotation")
    except Exception as e:
        print(f"\n[ERROR] ORF calling failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()