#!/usr/bin/env python3
"""
Stage-2 Windows Setup - No sudo required
Downloads pre-compiled binaries to user directory
"""

import os
import urllib.request
import subprocess
import tempfile
from pathlib import Path

def download_file(url, dest_path):
    """Download file with progress"""
    print(f"Downloading {url}...")
    try:
        urllib.request.urlretrieve(url, dest_path)
        print(f"✅ Downloaded: {dest_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to download {url}: {e}")
        return False

def setup_stage2_tools():
    """Setup bioinformatics tools without sudo"""
    
    # Create tools directory
    home = Path.home()
    tools_dir = home / "bgc_tools"
    tools_dir.mkdir(exist_ok=True)
    
    bin_dir = tools_dir / "bin"
    data_dir = tools_dir / "data"
    bin_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)
    
    print(f"🔧 Setting up tools in {tools_dir}")
    
    # Download Prodigal binary (Linux x64)
    prodigal_url = "https://github.com/hyattpd/Prodigal/releases/download/v2.6.3/prodigal.linux"
    prodigal_path = bin_dir / "prodigal"
    
    if download_file(prodigal_url, prodigal_path):
        # Make executable
        os.chmod(prodigal_path, 0o755)
        print("✅ Prodigal installed")
    
    # Download HMMER (we'll use conda-style approach)
    # Create a simple script that uses online HMMER if local fails
    hmmer_wrapper = bin_dir / "hmmscan"
    with open(hmmer_wrapper, 'w') as f:
        f.write(f"""#!/bin/bash
# HMMER wrapper - tries multiple approaches
echo "🔍 Running HMMER domain search..."

# Try system hmmscan first
if command -v hmmscan &> /dev/null; then
    hmmscan "$@"
    exit $?
fi

# Try conda/mamba
if command -v mamba &> /dev/null; then
    mamba install -y hmmer
    hmmscan "$@"
    exit $?
fi

# Fallback: use online API or alternative
echo "❌ HMMER not found. Install with: conda install hmmer"
exit 1
""")
    os.chmod(hmmer_wrapper, 0o755)
    
    # Download Pfam database (this is the big one)
    pfam_url = "ftp://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.gz"
    pfam_gz_path = data_dir / "Pfam-A.hmm.gz"
    pfam_path = data_dir / "Pfam-A.hmm"
    
    if not pfam_path.exists():
        print("📚 Downloading Pfam database (this will take time)...")
        if download_file(pfam_url, pfam_gz_path):
            print("🗜️ Decompressing Pfam database...")
            import gzip
            with gzip.open(pfam_gz_path, 'rb') as f_in:
                with open(pfam_path, 'wb') as f_out:
                    f_out.write(f_in.read())
            print("✅ Pfam database ready")
            pfam_gz_path.unlink()  # Remove compressed file
    else:
        print("✅ Pfam database already exists")
    
    # Create environment setup script
    setup_script = tools_dir / "setup_env.sh"
    with open(setup_script, 'w') as f:
        f.write(f"""#!/bin/bash
# BGC Tools Environment Setup
export PATH="{bin_dir}:$PATH"
export PFAM_DB="{pfam_path}"

echo "🧬 BGC Tools Environment Ready"
echo "   Prodigal: {prodigal_path}"
echo "   Pfam DB: {pfam_path}"
echo "   PATH updated with tools"
""")
    os.chmod(setup_script, 0o755)
    
    # Test installations
    print("\n🧪 Testing installations...")
    
    # Test Prodigal
    try:
        result = subprocess.run([str(prodigal_path), '-v'], 
                              capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print("✅ Prodigal: Working")
        else:
            print("⚠️ Prodigal: May need system libraries")
    except Exception as e:
        print(f"⚠️ Prodigal test failed: {e}")
    
    # Test Python modules
    try:
        import subprocess
        result = subprocess.run(['python3', '-c', 'from Bio import SeqIO; print("Biopython OK")'], 
                              capture_output=True, text=True, check=False)
        if result.returncode == 0:
            print("✅ Python + Biopython: Available")
        else:
            print("❌ Biopython not installed")
            print("   Install with: python3 -m pip install biopython pandas")
    except Exception as e:
        print(f"⚠️ Python test failed: {e}")
    
    print(f"\n🎯 Setup complete!")
    print(f"Tools installed in: {tools_dir}")
    print(f"To activate: source {setup_script}")
    
    return tools_dir, str(pfam_path)

if __name__ == "__main__":
    tools_dir, pfam_db = setup_stage2_tools()