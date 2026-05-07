#!/bin/bash
# Quick Stage-2 Production Run Script
# This script sets up and runs the complete Stage-2 pipeline

echo "🧬 Stage-2 BGC Pipeline - Quick Setup & Execute"
echo "==============================================="
echo ""

# Update Pfam path in stage2_production.py
cd /mnt/d/web.dv

# Create a temporary modified version with correct paths
cat stage2_production.py | sed "s|PFAM_DB = .*|PFAM_DB = \"/home/$(whoami)/data/Pfam-A.hmm\"|g" | \
sed "s|INPUT_FASTA = .*|INPUT_FASTA = \"stage2_test_results/extracted_regions.fasta\"|g" | \
sed "s|OUTPUT_DIR = .*|OUTPUT_DIR = \"stage2_production_results\"|g" > /tmp/stage2_run.py

echo "📁 Input: stage2_test_results/extracted_regions.fasta"
echo "📂 Output: stage2_production_results/"
echo "📚 Pfam: /home/$(whoami)/data/Pfam-A.hmm"
echo ""

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command -v prodigal &> /dev/null; then
    echo "❌ Prodigal not found. Installing..."
    sudo apt install -y prodigal
fi

if ! command -v hmmscan &> /dev/null; then
    echo "❌ HMMER not found. Installing..."
    sudo apt install -y hmmer
fi

if ! python3 -c "from Bio import SeqIO" &> /dev/null; then
    echo "❌ Biopython not found. Installing..."
    pip3 install biopython pandas --user
fi

if [ ! -f ~/data/Pfam-A.hmm ]; then
    echo "❌ Pfam database not found at ~/data/Pfam-A.hmm"
    echo "   Please run: bash /mnt/d/web.dv/setup_stage2.sh first"
    exit 1
fi

echo "✅ All prerequisites met"
echo ""
echo "🚀 Running Stage-2 Production Pipeline..."
echo "   This may take 10-30 minutes for 588 regions"
echo ""

python3 /tmp/stage2_run.py

echo ""
echo "🎉 Stage-2 Complete!"
echo "   Results saved to: /mnt/d/web.dv/stage2_production_results/"