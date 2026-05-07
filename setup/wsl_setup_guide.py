#!/usr/bin/env python3
"""
WSL Stage-2 Setup with Password Input
This script helps set up Stage-2 tools in WSL step by step.
"""

import subprocess
import sys

def run_wsl_command(command, description):
    """Run a command in WSL with description."""
    print(f"🚀 {description}")
    print(f"   Command: {command}")
    
    full_command = f"wsl -d Ubuntu -- bash -c '{command}'"
    result = subprocess.run(full_command, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ Success")
        if result.stdout:
            print(f"   Output: {result.stdout[:200]}...")
        return True
    else:
        print(f"❌ Failed")
        if result.stderr:
            print(f"   Error: {result.stderr[:200]}...")
        return False

def setup_stage2_wsl():
    """Step-by-step setup of Stage-2 in WSL."""
    
    print("🔧 WSL Stage-2 Setup for BGC Pipeline")
    print("=" * 50)
    
    # Step 1: Update packages
    if not run_wsl_command("sudo apt update", "Updating package list"):
        print("\n⚠️  Please run manually: wsl -d Ubuntu -- bash -c 'sudo apt update'")
        return False
    
    # Step 2: Install tools
    install_cmd = "sudo apt install -y prodigal hmmer python3-pip"
    if not run_wsl_command(install_cmd, "Installing Prodigal, HMMER, and Python pip"):
        print("\n⚠️  Please run manually:")
        print(f"   wsl -d Ubuntu -- bash -c '{install_cmd}'")
        return False
    
    # Step 3: Install Python packages
    pip_cmd = "pip3 install biopython pandas"
    if not run_wsl_command(pip_cmd, "Installing Python packages"):
        print("\n⚠️  Please run manually:")
        print(f"   wsl -d Ubuntu -- bash -c '{pip_cmd}'")
        return False
    
    # Step 4: Verify installations
    print("\n🔍 Verifying installations...")
    
    # Check Prodigal
    if run_wsl_command("prodigal -v", "Checking Prodigal"):
        print("   ✅ Prodigal installed")
    
    # Check HMMER
    if run_wsl_command("hmmscan -h", "Checking HMMER"):
        print("   ✅ HMMER installed")
    
    # Check Python
    if run_wsl_command("python3 -c \"from Bio import SeqIO; print('Biopython OK')\"", "Checking Python packages"):
        print("   ✅ Python packages installed")
    
    # Step 5: Download Pfam database
    print("\n📚 Downloading Pfam database (this takes time)...")
    print("   This step downloads ~1.2GB and may take 30-60 minutes")
    
    download_cmds = [
        "mkdir -p ~/data",
        "cd ~/data",
        "wget -c ftp://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.gz",
        "gunzip Pfam-A.hmm.gz",
        "hmmpress Pfam-A.hmm"
    ]
    
    for cmd in download_cmds:
        if not run_wsl_command(cmd, f"Running: {cmd[:50]}..."):
            print(f"\n⚠️  Please run manually:")
            print(f"   wsl -d Ubuntu -- bash -c '{cmd}'")
    
    print("\n🎉 WSL Stage-2 Setup Complete!")
    print("\nNext steps:")
    print("1. Check Pfam download: wsl -d Ubuntu -- bash -c 'ls -lh ~/data/Pfam-A.hmm*'")
    print("2. Run test: wsl -d Ubuntu -- bash -c 'cd /mnt/d/web.dv && python3 test_stage2_wsl.py'")
    print("3. Run production: wsl -d Ubuntu -- bash -c 'cd /mnt/d/web.dv && python3 stage2_production.py'")
    
    return True

if __name__ == "__main__":
    print("\n🔐 IMPORTANT: You'll be prompted for your WSL password during installation.")
    print("   This is normal - just type your password when asked.")
    print()
    
    success = setup_stage2_wsl()
    
    if success:
        print("\n✅ Ready for production Stage-2 execution!")
    else:
        print("\n❌ Setup incomplete. Please check the errors above.")