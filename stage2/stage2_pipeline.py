"""
Stage-2 Gene Miner: Complete Pipeline
======================================
End-to-end Stage-2 pipeline that transforms Phase-1 regions into BGC candidates.

Pipeline:
1. Extract regions from genome FASTA
2. Call ORFs with Prodigal  
3. Annotate domains with HMMER
4. Parse domain results
5. Apply BGC classification rules
6. Generate final candidate list

Usage:
    python stage2_pipeline.py --phase1 results.tsv --genome genome.fasta --output stage2_output/
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
import pandas as pd
import time

def run_command(cmd: list, description: str, check_output: bool = True):
    """Run a command and handle errors."""
    print(f"\n{'='*20}")
    print(f"Step: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*20}")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = time.time() - start_time
        print(f"✅ Completed in {duration:.1f}s")
        
        if result.stdout.strip():
            print("Output:")
            print(result.stdout)
        
        return result
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed!")
        print(f"Return code: {e.returncode}")
        print(f"Error: {e.stderr}")
        raise
    except FileNotFoundError as e:
        print(f"❌ Command not found: {e}")
        print("Make sure all required tools are installed and in PATH")
        raise

def check_dependencies():
    """Check if required tools are available."""
    print("Checking dependencies...")
    
    # Check Python modules
    try:
        import pandas
        import Bio
        print("  ✅ Python dependencies: OK")
    except ImportError as e:
        print(f"  ❌ Missing Python package: {e}")
        return False
    
    # Check Prodigal
    try:
        result = subprocess.run(['prodigal', '-v'], capture_output=True, text=True)
        if result.returncode == 0:
            print("  ✅ Prodigal: Available")
        else:
            print("  ❌ Prodigal: Not working properly")
            return False
    except FileNotFoundError:
        print("  ❌ Prodigal: Not found (install with: conda install -c bioconda prodigal)")
        return False
    
    # Check HMMER
    try:
        result = subprocess.run(['hmmscan', '-h'], capture_output=True, text=True)
        if result.returncode == 0:
            print("  ✅ HMMER: Available")
        else:
            print("  ❌ HMMER: Not working properly")
            return False
    except FileNotFoundError:
        print("  ❌ HMMER: Not found (install with: conda install -c bioconda hmmer)")
        return False
    
    return True

def setup_output_directory(output_dir: str):
    """Create output directory structure."""
    output_path = Path(output_dir)
    
    # Create subdirectories
    subdirs = [
        'regions',      # Extracted FASTA regions
        'orfs',         # Prodigal results
        'domains',      # HMMER results  
        'final'         # Final BGC candidates
    ]
    
    for subdir in subdirs:
        (output_path / subdir).mkdir(parents=True, exist_ok=True)
    
    print(f"✅ Output directory: {output_dir}")
    return output_path

def run_stage2_pipeline(phase1_results: str, genome_fasta: str, output_dir: str, 
                       pfam_db: str = None, threads: int = 4):
    """Run the complete Stage-2 pipeline."""
    
    print("🧬 STAGE-2 GENE MINER PIPELINE")
    print("=" * 60)
    print(f"Phase-1 results: {phase1_results}")
    print(f"Genome FASTA:    {genome_fasta}")
    print(f"Output dir:      {output_dir}")
    print(f"Threads:         {threads}")
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Dependency check failed!")
        sys.exit(1)
    
    # Setup output directory
    output_path = setup_output_directory(output_dir)
    
    # File paths
    regions_fasta = output_path / 'regions' / 'phase1_regions.fasta'
    proteins_faa = output_path / 'orfs' / 'regions_proteins.faa'
    domains_domtbl = output_path / 'domains' / 'domains.domtblout'
    domain_table_csv = output_path / 'domains' / 'domain_table.csv'
    bgc_candidates_csv = output_path / 'final' / 'bgc_candidates.csv'
    
    # ══════════════════════════════════════════════════
    # STEP 1: Extract regions from genome FASTA
    # ══════════════════════════════════════════════════
    
    cmd = [
        sys.executable, 'extract_regions.py',
        '--phase1-results', phase1_results,
        '--genome-fasta', genome_fasta,
        '--output', str(regions_fasta),
        '--extend', '5000'
    ]
    run_command(cmd, "Extract Phase-1 regions")
    
    # ══════════════════════════════════════════════════
    # STEP 2: Call ORFs with Prodigal
    # ══════════════════════════════════════════════════
    
    cmd = [
        sys.executable, 'call_orfs.py',
        '--input', str(regions_fasta),
        '--output-dir', str(output_path / 'orfs')
    ]
    run_command(cmd, "Gene prediction with Prodigal")
    
    # ══════════════════════════════════════════════════
    # STEP 3: Domain annotation with HMMER
    # ══════════════════════════════════════════════════
    
    if pfam_db and os.path.exists(pfam_db):
        print(f"Using Pfam database: {pfam_db}")
        cmd = [
            'hmmscan',
            '--cpu', str(threads),
            '--domtblout', str(domains_domtbl),
            pfam_db,
            str(proteins_faa)
        ]
        
        # Redirect stdout to log file
        with open(output_path / 'domains' / 'hmmer.log', 'w') as log_file:
            result = subprocess.run(cmd, stdout=log_file, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                print(f"❌ HMMER failed: {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, cmd)
        
        print("✅ HMMER domain annotation complete")
    else:
        print("⚠️  No Pfam database provided - creating mock domain annotations")
        print("   For real analysis, download Pfam-A.hmm from: http://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/")
        
        # Create mock domain table for testing
        with open(domains_domtbl, 'w') as f:
            f.write("# Mock domain annotations for testing\n")
            f.write("# Download Pfam-A.hmm for real analysis\n")
    
    # ══════════════════════════════════════════════════
    # STEP 4: Parse domain annotations
    # ══════════════════════════════════════════════════
    
    if os.path.exists(domains_domtbl) and os.path.getsize(domains_domtbl) > 100:
        cmd = [
            sys.executable, 'parse_domains.py',
            '--domtblout', str(domains_domtbl),
            '--proteins', str(proteins_faa),
            '--output', str(domain_table_csv),
            '--evalue', '1e-5'
        ]
        run_command(cmd, "Parse domain annotations")
    else:
        print("⚠️  No domain annotations found - creating empty table")
        pd.DataFrame().to_csv(domain_table_csv, index=False)
    
    # ══════════════════════════════════════════════════
    # STEP 5: BGC classification
    # ══════════════════════════════════════════════════
    
    if os.path.exists(domain_table_csv) and os.path.getsize(domain_table_csv) > 100:
        cmd = [
            sys.executable, 'classify_bgcs.py',
            '--domain-table', str(domain_table_csv),
            '--output', str(bgc_candidates_csv),
            '--min-score', '0.4',
            '--min-domains', '1'  # Relaxed for testing
        ]
        run_command(cmd, "BGC classification and filtering")
    else:
        print("⚠️  No domain table found - creating empty results")
        pd.DataFrame().to_csv(bgc_candidates_csv, index=False)
    
    # ══════════════════════════════════════════════════
    # FINAL REPORT
    # ══════════════════════════════════════════════════
    
    print(f"\n{'='*60}")
    print("STAGE-2 PIPELINE COMPLETE!")
    print(f"{'='*60}")
    
    # Count results
    try:
        if os.path.exists(bgc_candidates_csv):
            candidates = pd.read_csv(bgc_candidates_csv)
            print(f"\n📊 RESULTS SUMMARY:")
            print(f"   BGC candidates found: {len(candidates)}")
            
            if len(candidates) > 0:
                print(f"   Predicted types:")
                type_counts = candidates['predicted_type'].value_counts()
                for bgc_type, count in type_counts.items():
                    print(f"     {bgc_type}: {count}")
                
                print(f"\n🎯 TOP CANDIDATES:")
                top_candidates = candidates.nlargest(5, 'confidence_score')
                for _, row in top_candidates.iterrows():
                    print(f"     {row['region_id']}: {row['predicted_type']} "
                          f"(score: {row['confidence_score']:.3f}, {row['bgc_domains']} domains)")
        
        print(f"\n📂 OUTPUT FILES:")
        print(f"   Regions:     {regions_fasta}")
        print(f"   Proteins:    {proteins_faa}")
        print(f"   Domains:     {domain_table_csv}")
        print(f"   Candidates:  {bgc_candidates_csv}")
        
        print(f"\n🚀 Ready for Stage-3 (detailed analysis)")
        
    except Exception as e:
        print(f"Error generating summary: {e}")

def main():
    parser = argparse.ArgumentParser(
        description="Stage-2 Gene Miner: Complete Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (no domain annotation)
  python stage2_pipeline.py --phase1 results.tsv --genome genome.fasta --output stage2_out/
  
  # With Pfam database for domain annotation
  python stage2_pipeline.py --phase1 results.tsv --genome genome.fasta --output stage2_out/ --pfam Pfam-A.hmm
        """
    )
    
    parser.add_argument("--phase1", "-p", required=True,
                       help="Phase-1 results TSV file")
    parser.add_argument("--genome", "-g", required=True,
                       help="Original genome FASTA file")
    parser.add_argument("--output", "-o", required=True,
                       help="Output directory for Stage-2 results")
    parser.add_argument("--pfam", "-f", default=None,
                       help="Pfam-A.hmm database file (optional)")
    parser.add_argument("--threads", "-t", type=int, default=4,
                       help="Number of threads (default: 4)")
    
    args = parser.parse_args()
    
    # Validate inputs
    if not os.path.exists(args.phase1):
        print(f"❌ Phase-1 results not found: {args.phase1}")
        sys.exit(1)
    
    if not os.path.exists(args.genome):
        print(f"❌ Genome FASTA not found: {args.genome}")
        sys.exit(1)
    
    # Run pipeline
    try:
        run_stage2_pipeline(
            args.phase1, args.genome, args.output, 
            args.pfam, args.threads
        )
        
    except KeyboardInterrupt:
        print(f"\n🛑 Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()