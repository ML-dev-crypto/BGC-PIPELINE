"""
Phase-1 BGC Discovery Pipeline: Preprocessing Script
====================================================
Converts MIBiG GBK and environmental eDNA FASTA files into PyTorch tensors
for Tensor Network-based biosynthetic likelihood filtering.

Author: BGC Discovery Pipeline
Date: 2026-01-19
"""

import os
import glob
from pathlib import Path
from typing import List, Tuple
import numpy as np
import torch
from Bio import SeqIO
from sklearn.model_selection import train_test_split
from collections import Counter

# ====================================================
# CONFIGURATION
# ====================================================

# Data paths
MIBIG_GBK_DIR = "./mibig_gbk_4.0/"
EDNA_FASTA_DIR = "./edna_fasta/"

# Output paths
OUTPUT_DIR = "./preprocessed_data/"
TRAIN_OUTPUT = os.path.join(OUTPUT_DIR, "train.pt")
VAL_OUTPUT = os.path.join(OUTPUT_DIR, "val.pt")

# Chunking parameters
CHUNK_SIZE = 1000  # bp
STRIDE = 500       # bp

# Train/validation split
TRAIN_RATIO = 0.8
VAL_RATIO = 0.2
RANDOM_SEED = 42

# Labels
LABEL_BGC = 1      # MIBiG biosynthetic sequences
LABEL_EDNA = 0     # Environmental DNA background


# ====================================================
# STEP 1: EXTRACT NUCLEOTIDE SEQUENCES FROM GBK FILES
# ====================================================

def extract_sequences_from_gbk(gbk_dir: str) -> List[Tuple[str, str]]:
    """
    Extract nucleotide DNA sequences from MIBiG GenBank files.
    
    Args:
        gbk_dir: Directory containing .gbk files
        
    Returns:
        List of (sequence_id, nucleotide_sequence) tuples
    """
    print(f"[1/9] Extracting nucleotide sequences from GBK files in {gbk_dir}...")
    
    sequences = []
    gbk_files = glob.glob(os.path.join(gbk_dir, "*.gbk"))
    gbk_files += glob.glob(os.path.join(gbk_dir, "*.gb"))
    
    if not gbk_files:
        raise FileNotFoundError(f"No .gbk or .gb files found in {gbk_dir}")
    
    for gbk_file in gbk_files:
        try:
            for record in SeqIO.parse(gbk_file, "genbank"):
                # Extract ONLY the nucleotide sequence (ignore annotations)
                seq_id = record.id
                nucleotide_seq = str(record.seq).upper()
                
                if len(nucleotide_seq) > 0:
                    sequences.append((seq_id, nucleotide_seq))
        except Exception as e:
            print(f"  Warning: Could not parse {gbk_file}: {e}")
            continue
    
    print(f"  Extracted {len(sequences)} sequences from {len(gbk_files)} GBK files")
    return sequences


# ====================================================
# STEP 2: LOAD ENVIRONMENTAL eDNA SEQUENCES FROM FASTA
# ====================================================

def load_fasta_sequences(fasta_dir: str) -> List[Tuple[str, str]]:
    """
    Load environmental DNA sequences from FASTA files.
    
    Args:
        fasta_dir: Directory containing .fasta or .fna files
        
    Returns:
        List of (sequence_id, nucleotide_sequence) tuples
    """
    print(f"[2/9] Loading eDNA sequences from FASTA files in {fasta_dir}...")
    
    sequences = []
    fasta_files = glob.glob(os.path.join(fasta_dir, "*.fasta"))
    fasta_files += glob.glob(os.path.join(fasta_dir, "*.fna"))
    fasta_files += glob.glob(os.path.join(fasta_dir, "*.fa"))
    
    if not fasta_files:
        raise FileNotFoundError(f"No .fasta, .fna, or .fa files found in {fasta_dir}")
    
    for fasta_file in fasta_files:
        try:
            for record in SeqIO.parse(fasta_file, "fasta"):
                seq_id = record.id
                nucleotide_seq = str(record.seq).upper()
                
                if len(nucleotide_seq) > 0:
                    sequences.append((seq_id, nucleotide_seq))
        except Exception as e:
            print(f"  Warning: Could not parse {fasta_file}: {e}")
            continue
    
    print(f"  Loaded {len(sequences)} sequences from {len(fasta_files)} FASTA files")
    return sequences


# ====================================================
# STEP 3: CHUNK SEQUENCES INTO FIXED-LENGTH FRAGMENTS
# ====================================================

def chunk_sequences(sequences: List[Tuple[str, str]], 
                    chunk_size: int = CHUNK_SIZE, 
                    stride: int = STRIDE) -> List[str]:
    """
    Chunk sequences into fixed-length fragments using a sliding window.
    
    Args:
        sequences: List of (seq_id, nucleotide_sequence) tuples
        chunk_size: Length of each chunk in bp
        stride: Step size for sliding window
        
    Returns:
        List of DNA sequence chunks (strings of length chunk_size)
    """
    print(f"[3/9] Chunking sequences (size={chunk_size}, stride={stride})...")
    
    chunks = []
    
    for seq_id, seq in sequences:
        seq_len = len(seq)
        
        # Slide window across sequence
        for start in range(0, seq_len - chunk_size + 1, stride):
            end = start + chunk_size
            chunk = seq[start:end]
            
            # Only keep complete chunks of exact length
            if len(chunk) == chunk_size:
                chunks.append(chunk)
    
    print(f"  Generated {len(chunks)} chunks")
    return chunks


# ====================================================
# STEP 4: ONE-HOT ENCODE DNA SEQUENCES
# ====================================================

def one_hot_encode_dna(sequence: str) -> np.ndarray:
    """
    One-hot encode a DNA sequence.
    
    Encoding scheme:
        A → [1, 0, 0, 0]
        C → [0, 1, 0, 0]
        G → [0, 0, 1, 0]
        T → [0, 0, 0, 1]
        N or other → [0, 0, 0, 0]
    
    Args:
        sequence: DNA sequence string
        
    Returns:
        NumPy array of shape (len(sequence), 4)
    """
    mapping = {
        'A': [1, 0, 0, 0],
        'C': [0, 1, 0, 0],
        'G': [0, 0, 1, 0],
        'T': [0, 0, 0, 1]
    }
    
    # Default for ambiguous bases
    default = [0, 0, 0, 0]
    
    encoded = np.array([mapping.get(base, default) for base in sequence], dtype=np.float32)
    return encoded


def encode_chunks(chunks: List[str]) -> np.ndarray:
    """
    One-hot encode a list of DNA chunks.
    
    Args:
        chunks: List of DNA sequence strings
        
    Returns:
        NumPy array of shape (n_chunks, chunk_size, 4)
    """
    print(f"[4/9] One-hot encoding {len(chunks)} chunks...")
    
    encoded_chunks = []
    
    for i, chunk in enumerate(chunks):
        encoded = one_hot_encode_dna(chunk)
        encoded_chunks.append(encoded)
        
        if (i + 1) % 10000 == 0:
            print(f"  Encoded {i + 1}/{len(chunks)} chunks")
    
    encoded_array = np.stack(encoded_chunks, axis=0)
    print(f"  Final shape: {encoded_array.shape}")
    
    return encoded_array


# ====================================================
# STEP 5: BALANCE DATASET AT CHUNK LEVEL
# ====================================================

def balance_dataset(X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Balance the dataset by downsampling the majority class.
    
    Args:
        X: Feature array of shape (n_samples, chunk_size, 4)
        y: Label array of shape (n_samples,)
        
    Returns:
        Balanced (X, y) tuple
    """
    print(f"[5/9] Balancing dataset at chunk level...")
    
    # Count samples per class
    unique, counts = np.unique(y, return_counts=True)
    print(f"  Before balancing: {dict(zip(unique, counts))}")
    
    # Find minority class size
    min_count = counts.min()
    
    # Sample equal number from each class
    balanced_indices = []
    for label in unique:
        label_indices = np.where(y == label)[0]
        sampled_indices = np.random.choice(label_indices, size=min_count, replace=False)
        balanced_indices.extend(sampled_indices)
    
    balanced_indices = np.array(balanced_indices)
    
    # Shuffle the balanced indices
    np.random.shuffle(balanced_indices)
    
    X_balanced = X[balanced_indices]
    y_balanced = y[balanced_indices]
    
    unique_bal, counts_bal = np.unique(y_balanced, return_counts=True)
    print(f"  After balancing: {dict(zip(unique_bal, counts_bal))}")
    print(f"  Total balanced samples: {len(y_balanced)}")
    
    return X_balanced, y_balanced


# ====================================================
# STEP 6: SPLIT DATASET (STRATIFIED)
# ====================================================

def split_dataset(X: np.ndarray, y: np.ndarray, 
                 train_ratio: float = TRAIN_RATIO,
                 random_seed: int = RANDOM_SEED) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Split dataset into training and validation sets with stratification.
    
    Args:
        X: Feature array
        y: Label array
        train_ratio: Fraction of data for training
        random_seed: Random seed for reproducibility
        
    Returns:
        (X_train, X_val, y_train, y_val) tuple
    """
    print(f"[6/9] Splitting dataset (train={train_ratio*100}%, val={100-train_ratio*100}%)...")
    
    X_train, X_val, y_train, y_val = train_test_split(
        X, y,
        train_size=train_ratio,
        stratify=y,
        random_state=random_seed,
        shuffle=True
    )
    
    print(f"  Training set: {len(X_train)} samples")
    print(f"    Class distribution: {dict(zip(*np.unique(y_train, return_counts=True)))}")
    print(f"  Validation set: {len(X_val)} samples")
    print(f"    Class distribution: {dict(zip(*np.unique(y_val, return_counts=True)))}")
    
    return X_train, X_val, y_train, y_val


# ====================================================
# STEP 7: CONVERT TO PYTORCH TENSORS
# ====================================================

def to_pytorch_tensors(X: np.ndarray, y: np.ndarray) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Convert NumPy arrays to PyTorch tensors.
    
    Args:
        X: Feature array
        y: Label array
        
    Returns:
        (X_tensor, y_tensor) tuple
    """
    X_tensor = torch.from_numpy(X).float()  # shape: (N, 1000, 4)
    y_tensor = torch.from_numpy(y).long()   # shape: (N,)
    
    return X_tensor, y_tensor


# ====================================================
# STEP 8: SAVE TENSORS
# ====================================================

def save_tensors(X_train: torch.Tensor, y_train: torch.Tensor,
                X_val: torch.Tensor, y_val: torch.Tensor,
                output_dir: str = OUTPUT_DIR):
    """
    Save training and validation tensors to disk.
    
    Args:
        X_train, y_train: Training data
        X_val, y_val: Validation data
        output_dir: Directory to save tensors
    """
    print(f"[7/9] Saving tensors to {output_dir}...")
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Save training data
    train_path = os.path.join(output_dir, "train.pt")
    torch.save({
        'X': X_train,
        'y': y_train
    }, train_path)
    print(f"  Saved training data to {train_path}")
    print(f"    X_train shape: {X_train.shape}, dtype: {X_train.dtype}")
    print(f"    y_train shape: {y_train.shape}, dtype: {y_train.dtype}")
    
    # Save validation data
    val_path = os.path.join(output_dir, "val.pt")
    torch.save({
        'X': X_val,
        'y': y_val
    }, val_path)
    print(f"  Saved validation data to {val_path}")
    print(f"    X_val shape: {X_val.shape}, dtype: {X_val.dtype}")
    print(f"    y_val shape: {y_val.shape}, dtype: {y_val.dtype}")


# ====================================================
# MAIN PREPROCESSING PIPELINE
# ====================================================

def main():
    """
    Execute the complete Phase-1 preprocessing pipeline.
    """
    print("=" * 80)
    print("Phase-1 BGC Discovery: Preprocessing Pipeline")
    print("=" * 80)
    print()
    
    # Set random seed for reproducibility
    np.random.seed(RANDOM_SEED)
    torch.manual_seed(RANDOM_SEED)
    
    # ─────────────────────────────────────────────────
    # STEP 1-2: Load data from both sources
    # ─────────────────────────────────────────────────
    
    # Extract MIBiG sequences from GBK files
    mibig_sequences = extract_sequences_from_gbk(MIBIG_GBK_DIR)
    
    # Load environmental eDNA sequences from FASTA
    edna_sequences = load_fasta_sequences(EDNA_FASTA_DIR)
    
    print()
    
    # ─────────────────────────────────────────────────
    # STEP 3: Chunk both datasets identically
    # ─────────────────────────────────────────────────
    
    print(f"Processing MIBiG (BGC) data...")
    mibig_chunks = chunk_sequences(mibig_sequences, CHUNK_SIZE, STRIDE)
    
    print(f"Processing eDNA (background) data...")
    edna_chunks = chunk_sequences(edna_sequences, CHUNK_SIZE, STRIDE)
    
    print()
    
    # ─────────────────────────────────────────────────
    # STEP 4: One-hot encode both datasets
    # ─────────────────────────────────────────────────
    
    print(f"Encoding MIBiG chunks...")
    X_mibig = encode_chunks(mibig_chunks)
    
    print(f"Encoding eDNA chunks...")
    X_edna = encode_chunks(edna_chunks)
    
    print()
    
    # ─────────────────────────────────────────────────
    # STEP 5: Assign labels and combine datasets
    # ─────────────────────────────────────────────────
    
    print(f"[5/9] Assigning labels and combining datasets...")
    
    # Create labels
    y_mibig = np.ones(len(X_mibig), dtype=np.int64) * LABEL_BGC
    y_edna = np.zeros(len(X_edna), dtype=np.int64)
    
    # Combine
    X = np.concatenate([X_mibig, X_edna], axis=0)
    y = np.concatenate([y_mibig, y_edna], axis=0)
    
    print(f"  Combined dataset: {X.shape[0]} samples")
    print(f"  Shape: {X.shape}")
    print(f"  Label distribution: {dict(zip(*np.unique(y, return_counts=True)))}")
    print()
    
    # ─────────────────────────────────────────────────
    # STEP 6: Balance dataset at chunk level
    # ─────────────────────────────────────────────────
    
    X_balanced, y_balanced = balance_dataset(X, y)
    print()
    
    # ─────────────────────────────────────────────────
    # STEP 7: Split into train/val (stratified)
    # ─────────────────────────────────────────────────
    
    X_train, X_val, y_train, y_val = split_dataset(
        X_balanced, y_balanced, 
        train_ratio=TRAIN_RATIO, 
        random_seed=RANDOM_SEED
    )
    print()
    
    # ─────────────────────────────────────────────────
    # STEP 8: Convert to PyTorch tensors
    # ─────────────────────────────────────────────────
    
    print(f"[8/9] Converting to PyTorch tensors...")
    X_train_tensor, y_train_tensor = to_pytorch_tensors(X_train, y_train)
    X_val_tensor, y_val_tensor = to_pytorch_tensors(X_val, y_val)
    print(f"  Conversion complete")
    print()
    
    # ─────────────────────────────────────────────────
    # STEP 9: Save tensors to disk
    # ─────────────────────────────────────────────────
    
    save_tensors(X_train_tensor, y_train_tensor, X_val_tensor, y_val_tensor)
    print()
    
    # ─────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────
    
    print("=" * 80)
    print("[9/9] Preprocessing complete!")
    print("=" * 80)
    print()
    print("SUMMARY:")
    print(f"  Training samples:   {len(X_train_tensor)}")
    print(f"  Validation samples: {len(X_val_tensor)}")
    print(f"  Tensor shape:       {X_train_tensor.shape}")
    print(f"  Tensor dtype:       {X_train_tensor.dtype}")
    print()
    print("OUTPUT FILES:")
    print(f"  {TRAIN_OUTPUT}")
    print(f"  {VAL_OUTPUT}")
    print()
    print("These tensors are ready to be uploaded to Kaggle for model training.")
    print("=" * 80)


if __name__ == "__main__":
    main()
