"""
Stage-2 Setup Guide: WSL + Bioinformatics Tools
================================================
Production setup for the biological refinery on Windows.

CRITICAL: Stage-2 requires WSL/Linux environment
Windows is supported for Phase-1 only.
"""

# WSL SETUP INSTRUCTIONS
"""
1. INSTALL WSL (Windows Subsystem for Linux)
   Open PowerShell as Administrator and run:
   
   wsl --install Ubuntu
   
   Reboot and complete Ubuntu setup.

2. UPDATE UBUNTU
   In WSL terminal:
   
   sudo apt update
   sudo apt upgrade -y

3. INSTALL BIOINFORMATICS TOOLS
   In WSL terminal:
   
   # Essential tools
   sudo apt install -y build-essential wget curl
   
   # Prodigal (gene prediction)
   sudo apt install -y prodigal
   
   # HMMER (domain search)
   sudo apt install -y hmmer
   
   # Python + Biopython
   sudo apt install -y python3-pip
   pip3 install biopython pandas

4. DOWNLOAD PFAM DATABASE
   In WSL terminal (this takes time and space):
   
   mkdir -p ~/data
   cd ~/data
   
   # Download Pfam-A.hmm (large file ~1.2GB compressed)
   wget ftp://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.gz
   
   # Decompress
   gunzip Pfam-A.hmm.gz
   
   # Press database for HMMER (creates index files)
   hmmpress Pfam-A.hmm

5. VERIFY INSTALLATION
   Test all tools:
   
   prodigal -v
   hmmscan -h  
   python3 -c "from Bio import SeqIO; print('Biopython OK')"
   ls ~/data/Pfam-A.hmm*  # Should show 4 files (.h3m, .h3i, .h3f, .h3p)

6. COPY FILES TO WSL
   From Windows, copy your Phase-1 results to WSL:
   
   # In WSL terminal, create working directory
   mkdir -p ~/bgc_pipeline
   cd ~/bgc_pipeline
   
   # Copy from Windows to WSL (adjust paths)
   cp /mnt/d/web.dv/stage2_test_results/extracted_regions.fasta .
   cp /mnt/d/web.dv/stage2_production.py .

7. UPDATE PATHS IN SCRIPT
   Edit stage2_production.py in WSL:
   
   INPUT_FASTA = "extracted_regions.fasta"
   OUTPUT_DIR = "stage2_full_results"  
   PFAM_DB = "/home/[username]/data/Pfam-A.hmm"  # Update username

8. RUN PRODUCTION PIPELINE
   In WSL terminal:
   
   python3 stage2_production.py
"""

# EXPECTED TIMELINE
"""
SETUP TIME:
- WSL install: 10-20 minutes
- Tool installation: 5 minutes  
- Pfam download: 30-60 minutes (depending on connection)
- Database pressing: 5-10 minutes

ANALYSIS TIME (588 regions):
- Gene prediction: 2-5 minutes
- Domain annotation: 10-30 minutes (depends on region size)
- Graph construction: 1-2 minutes
"""

# SUCCESS CRITERIA FOR STAGE-2
"""
EXPECTED REDUCTION:
588 Phase-1 regions → ~100-200 regions with BGC domains → ~30-80 final candidates

If you get:
- 0 domains found: Check Pfam database path and hmmpress
- >500 candidates: Relax E-value cutoff or check parsing
- <10 candidates: Phase-1 threshold may be too strict

GOOD OUTPUT SIGNALS:
- PKS_KS, NRPS_A domains detected
- Domain coordinates preserved  
- BGC graphs with gene order
- JSON file with biological structure
"""

# TROUBLESHOOTING
"""
COMMON ISSUES:

1. "Prodigal not found"
   → Run: sudo apt install prodigal

2. "HMMER not found"  
   → Run: sudo apt install hmmer

3. "Pfam database not found"
   → Check path in PFAM_DB variable
   → Ensure hmmpress was run

4. "No domains found"
   → Check E-value cutoff (try 1e-3)
   → Verify Pfam database is pressed correctly

5. "Permission denied"
   → Ensure files are copied to WSL filesystem
   → Use chmod +x if needed
"""

def verify_wsl_setup():
    """Verification script to run in WSL."""
    import os
    import subprocess
    
    print("🔍 Verifying WSL Setup for Stage-2...")
    
    # Check tools
    tools = ['prodigal', 'hmmscan', 'python3']
    for tool in tools:
        try:
            result = subprocess.run([tool, '--version'], 
                                  capture_output=True, text=True, check=False)
            if result.returncode == 0:
                print(f"  ✅ {tool}: Available")
            else:
                print(f"  ❌ {tool}: Not working")
        except FileNotFoundError:
            print(f"  ❌ {tool}: Not found")
    
    # Check Python modules
    try:
        from Bio import SeqIO
        import pandas
        print("  ✅ Python packages: OK")
    except ImportError as e:
        print(f"  ❌ Python packages: {e}")
    
    # Check Pfam database
    pfam_path = "/home/{}/data/Pfam-A.hmm".format(os.getenv('USER', 'user'))
    if os.path.exists(pfam_path):
        print(f"  ✅ Pfam database: {pfam_path}")
        
        # Check if pressed
        index_files = [f"{pfam_path}.{ext}" for ext in ['h3m', 'h3i', 'h3f', 'h3p']]
        if all(os.path.exists(f) for f in index_files):
            print("  ✅ Pfam database: Properly pressed")
        else:
            print("  ⚠️  Pfam database: Not pressed (run: hmmpress Pfam-A.hmm)")
    else:
        print(f"  ❌ Pfam database: Not found at {pfam_path}")
    
    print("\n🎯 If all checks pass, you're ready for Stage-2!")

if __name__ == "__main__":
    verify_wsl_setup()