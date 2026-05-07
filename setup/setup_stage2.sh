#!/bin/bash
# Stage-2 Setup Script for WSL
# Run this directly in WSL terminal: bash /mnt/d/web.dv/setup_stage2.sh

echo "🔧 Setting up Stage-2 Bioinformatics Tools in WSL"
echo "=================================================="
echo ""

# Check if running in WSL
if [ ! -f /proc/version ] || ! grep -qi microsoft /proc/version; then
    echo "❌ This script must be run in WSL (Windows Subsystem for Linux)"
    exit 1
fi

echo "📦 Updating package list..."
sudo apt update

echo ""
echo "🧬 Installing Prodigal (gene prediction)..."
sudo apt install -y prodigal

echo ""
echo "🔍 Installing HMMER (domain search)..."
sudo apt install -y hmmer

echo ""
echo "🐍 Installing Python pip..."
sudo apt install -y python3-pip

echo ""
echo "📚 Installing Python packages..."
pip3 install biopython pandas --user

echo ""
echo "🧪 Verifying installations..."
echo ""

# Test Prodigal
if command -v prodigal &> /dev/null; then
    echo "✅ Prodigal installed"
    prodigal -v 2>&1 | head -n 1
else
    echo "❌ Prodigal installation failed"
fi

# Test HMMER
if command -v hmmscan &> /dev/null; then
    echo "✅ HMMER installed"
    hmmscan -h 2>&1 | head -n 2
else
    echo "❌ HMMER installation failed"
fi

# Test Python packages
echo ""
if python3 -c "from Bio import SeqIO; import pandas; print('✅ Python packages: Biopython and Pandas installed')" 2>&1; then
    :
else
    echo "❌ Python packages installation failed"
fi

echo ""
echo "📚 Downloading Pfam database..."
echo "   This downloads ~1.2GB and may take 30-60 minutes depending on your connection"
echo ""

# Create data directory
mkdir -p ~/data
cd ~/data

# Check if Pfam already exists
if [ -f ~/data/Pfam-A.hmm ]; then
    echo "✅ Pfam database already exists at ~/data/Pfam-A.hmm"
else
    echo "📥 Downloading Pfam-A.hmm.gz..."
    wget -c ftp://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.gz
    
    if [ $? -eq 0 ]; then
        echo "✅ Download complete"
        
        echo "🗜️  Decompressing..."
        gunzip Pfam-A.hmm.gz
        
        if [ $? -eq 0 ]; then
            echo "✅ Decompression complete"
        else
            echo "❌ Decompression failed"
            exit 1
        fi
    else
        echo "❌ Download failed"
        echo "   You can download manually:"
        echo "   wget ftp://ftp.ebi.ac.uk/pub/databases/Pfam/current_release/Pfam-A.hmm.gz"
        exit 1
    fi
fi

# Press Pfam database
if [ -f ~/data/Pfam-A.hmm ]; then
    echo ""
    echo "🔨 Pressing Pfam database (creating search indices)..."
    hmmpress ~/data/Pfam-A.hmm
    
    if [ $? -eq 0 ]; then
        echo "✅ Pfam database pressed successfully"
    else
        echo "❌ Database pressing failed"
        exit 1
    fi
fi

echo ""
echo "🎉 Stage-2 Setup Complete!"
echo ""
echo "📊 Summary:"
ls -lh ~/data/Pfam-A.hmm* 2>/dev/null | awk '{print "   "$9" ("$5")"}'
echo ""
echo "🚀 Ready to run production Stage-2 pipeline!"
echo ""
echo "Next steps:"
echo "1. Copy extracted regions to WSL:"
echo "   cp /mnt/d/web.dv/stage2_test_results/extracted_regions.fasta ~/bgc_regions.fasta"
echo ""
echo "2. Copy Stage-2 script to WSL:"
echo "   cp /mnt/d/web.dv/stage2_production.py ~/stage2_production.py"
echo ""
echo "3. Edit PFAM_DB path in stage2_production.py:"
echo "   nano ~/stage2_production.py"
echo "   # Change PFAM_DB to: /home/$(whoami)/data/Pfam-A.hmm"
echo ""
echo "4. Run the production pipeline:"
echo "   cd ~"
echo "   python3 stage2_production.py"
echo ""