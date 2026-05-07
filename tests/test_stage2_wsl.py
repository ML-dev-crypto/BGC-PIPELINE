"""
Stage-2 Quick Test Script
Execute this in WSL to verify your production setup works correctly.
"""

import os
import subprocess
import tempfile
from pathlib import Path

def test_stage2_setup():
    """Test Stage-2 tools with minimal example."""
    
    print("🧪 Testing Stage-2 Production Setup...")
    
    # Create test sequence
    test_fasta = """
>region_1|start=0|end=1000|score=0.85
ATGGCGATCGAACGCTACAAGGTGAAATCGCCCGGCGAAGTGCTGTACAACCGCATCGACG
TCGAGCGCAAGGACCTGACCGCCGAGAACGTCAAGGCCATCGCCGAGCGCGACAAGCTGAT
GTTCGACGAGCGCAAGCTGTCGATCCACGCCGAGTTCGAGCGCAAGCTGAACGCCGAGCTG
ATCGACGCCAAGGACTTCGAGCGCAAGCTGACCGCCGAGAACGTCAAGGCCATCGCCGAGC
GCGACAAGCTGATGTTCGACGAGCGCAAGCTGTCGATCCACGCCGAGTTCGAGCGCAAGCT
GAACGCCGAGCTGATCGACGCCAAGGACTTCGAGCGCAAGCTGACCGCCGAGAACGTCAAG
GCCATCGCCGAGCGCGACAAGCTGATGTTCGACGAGCGCAAGCTGTCGATCCACGCCGAGT
TCGAGCGCAAGCTGAACGCCGAGCTGATCGACGCCAAGGACTTCGAGCGCAAGCTGACCGC
CGAGAACGTCAAGGCCATCGCCGAGCGCGACAAGCTGATGTTCGACGAGCGCAAGCTGTCG
ATCCACGCCGAGTTCGAGCGCAAGCTGAACGCCGAGCTGATCGACGCCAAGGACTTCGAGC
GCAAGCTGACCGCCGAGAACGTCAAGGCCATCGCCGAGCGCGACAAGCTGATGTTCGACGA
GCGCAAGCTGTCGATCCACGCCGAGTTCGAGCGCAAGCTGAACGCCGAGCTGATCGACGCC
AAGGACTTCGAGCGCAAGCTGACCGCCGAGAACGTCAAGGCCATCGCCGAGCGCGACAAGC
TGATGTTCGACGAGCGCAAGCTGTCGATCCACGCCGAGTTCGAGCGCAAGCTGAACGCCGA
GCTGATCGACGCCAAGGACTTCGAGCGCAAGCTGACCGCCGAGAACGTCAAGGCCATCGCC
GAGCGCGACAAGCTGATGTTCGACGAGCGCAAGCTGTCGATCCACGCCGAGTTCGAGCGCA
AGCTGAACGCCGAGCTGATCGACGCCAAG
""".strip()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Write test FASTA
        test_fasta_path = temp_path / "test_regions.fasta"
        with open(test_fasta_path, 'w') as f:
            f.write(test_fasta)
        
        print(f"📁 Created test file: {test_fasta_path}")
        
        # Test 1: Prodigal gene prediction
        print("🧬 Testing Prodigal gene prediction...")
        prodigal_out = temp_path / "test_genes.gff"
        prodigal_faa = temp_path / "test_genes.faa"
        
        prodigal_cmd = [
            'prodigal', 
            '-i', str(test_fasta_path),
            '-o', str(prodigal_out),
            '-a', str(prodigal_faa),
            '-f', 'gff',
            '-p', 'meta'
        ]
        
        try:
            result = subprocess.run(prodigal_cmd, capture_output=True, text=True, check=True)
            print("  ✅ Prodigal: Gene prediction successful")
            
            # Check output
            if os.path.exists(prodigal_faa):
                with open(prodigal_faa, 'r') as f:
                    genes = f.read().count('>')
                print(f"  📊 Found {genes} predicted genes")
            
        except subprocess.CalledProcessError as e:
            print(f"  ❌ Prodigal failed: {e}")
            return False
        except FileNotFoundError:
            print("  ❌ Prodigal not found - install with: sudo apt install prodigal")
            return False
        
        # Test 2: HMMER domain search (need Pfam path)
        print("🔍 Testing HMMER domain search...")
        
        # Common Pfam paths to try
        pfam_paths = [
            f"/home/{os.getenv('USER', 'user')}/data/Pfam-A.hmm",
            "/home/ubuntu/data/Pfam-A.hmm",
            "./Pfam-A.hmm"
        ]
        
        pfam_db = None
        for path in pfam_paths:
            if os.path.exists(path):
                pfam_db = path
                break
        
        if pfam_db:
            print(f"  📚 Found Pfam database: {pfam_db}")
            
            hmmer_out = temp_path / "test_domains.out"
            hmmer_cmd = [
                'hmmscan',
                '--domtblout', str(hmmer_out),
                '-E', '1e-3',
                pfam_db,
                str(prodigal_faa)
            ]
            
            try:
                result = subprocess.run(hmmer_cmd, capture_output=True, text=True, check=True)
                print("  ✅ HMMER: Domain search successful")
                
                # Check domains found
                if os.path.exists(hmmer_out):
                    with open(hmmer_out, 'r') as f:
                        domains = len([l for l in f if not l.startswith('#')])
                    print(f"  📊 Found {domains} domain hits")
                    
            except subprocess.CalledProcessError as e:
                print(f"  ❌ HMMER failed: {e}")
                return False
            except FileNotFoundError:
                print("  ❌ HMMER not found - install with: sudo apt install hmmer")
                return False
                
        else:
            print("  ⚠️  Pfam database not found. Download with:")
            print("     wget ftp://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.gz")
            print("     gunzip Pfam-A.hmm.gz")
            print("     hmmpress Pfam-A.hmm")
            return False
        
        # Test 3: Python modules
        print("🐍 Testing Python modules...")
        try:
            from Bio import SeqIO
            import pandas as pd
            import json
            print("  ✅ Python modules: All required modules available")
        except ImportError as e:
            print(f"  ❌ Python modules: Missing {e}")
            print("     Install with: pip3 install biopython pandas")
            return False
        
        print("\n🎉 Stage-2 setup verification PASSED!")
        print("    Ready to run production pipeline on real data.")
        
        return True

if __name__ == "__main__":
    success = test_stage2_setup()
    
    if success:
        print("\n🚀 Next steps:")
        print("1. Copy your extracted_regions.fasta to WSL")
        print("2. Copy stage2_production.py to WSL")
        print("3. Update PFAM_DB path in stage2_production.py")
        print("4. Run: python3 stage2_production.py")
    else:
        print("\n❌ Setup incomplete. Fix issues above before proceeding.")