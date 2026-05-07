"""
Phase-1 BGC Discovery: Training Script
=======================================
Train the 1D CNN for biosynthetic likelihood scoring.

Features:
- GPU acceleration (auto-detect)
- Early stopping
- Learning rate scheduling
- Recall-focused metrics (for high-recall requirement)
- Model checkpointing
"""

import os
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, 
    f1_score, roc_auc_score, confusion_matrix
)

from phase1_model import get_model, count_parameters


# ====================================================
# CONFIGURATION
# ====================================================

DEFAULT_CONFIG = {
    # Data
    "train_path": "./preprocessed_data/train.pt",
    "val_path": "./preprocessed_data/val.pt",
    
    # Model
    "model_variant": "standard",  # "standard" or "large"
    
    # Training
    "batch_size": 64,
    "epochs": 50,
    "learning_rate": 1e-3,
    "weight_decay": 1e-4,
    
    # Early stopping
    "patience": 10,
    "min_delta": 0.001,
    
    # Output
    "output_dir": "./phase1_output/",
    "model_name": "phase1_cnn.pt",
}


# ====================================================
# DATA LOADING
# ====================================================

def load_data(train_path: str, val_path: str, batch_size: int) -> Tuple[DataLoader, DataLoader]:
    """
    Load preprocessed training and validation data.
    
    Returns:
        (train_loader, val_loader)
    """
    print("Loading data...")
    
    # Load tensors
    train_data = torch.load(train_path, weights_only=True)
    val_data = torch.load(val_path, weights_only=True)
    
    X_train, y_train = train_data['X'], train_data['y']
    X_val, y_val = val_data['X'], val_data['y']
    
    print(f"  Train: {len(X_train):,} samples")
    print(f"  Val:   {len(X_val):,} samples")
    
    # Create datasets
    train_dataset = TensorDataset(X_train, y_train.float())
    val_dataset = TensorDataset(X_val, y_val.float())
    
    # Create dataloaders
    train_loader = DataLoader(
        train_dataset, 
        batch_size=batch_size, 
        shuffle=True,
        num_workers=0,
        pin_memory=True
    )
    
    val_loader = DataLoader(
        val_dataset, 
        batch_size=batch_size, 
        shuffle=False,
        num_workers=0,
        pin_memory=True
    )
    
    return train_loader, val_loader


# ====================================================
# METRICS
# ====================================================

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> Dict:
    """
    Compute classification metrics with focus on RECALL.
    
    Phase-1 success criterion: Recall > 0.9
    """
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),  # CRITICAL
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "auc_roc": roc_auc_score(y_true, y_prob) if len(np.unique(y_true)) > 1 else 0.0,
    }
    
    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred)
    if cm.shape == (2, 2):
        tn, fp, fn, tp = cm.ravel()
        metrics["true_positives"] = tp
        metrics["false_positives"] = fp
        metrics["true_negatives"] = tn
        metrics["false_negatives"] = fn
        metrics["specificity"] = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    
    return metrics


def print_metrics(metrics: Dict, prefix: str = ""):
    """Print metrics in a formatted way."""
    print(f"{prefix}Accuracy:  {metrics['accuracy']:.4f}")
    print(f"{prefix}Precision: {metrics['precision']:.4f}")
    print(f"{prefix}Recall:    {metrics['recall']:.4f}  ← TARGET > 0.9")
    print(f"{prefix}F1 Score:  {metrics['f1']:.4f}")
    print(f"{prefix}AUC-ROC:   {metrics['auc_roc']:.4f}")


# ====================================================
# TRAINING LOOP
# ====================================================

def train_epoch(model, train_loader, criterion, optimizer, device) -> Tuple[float, Dict]:
    """Train for one epoch."""
    model.train()
    total_loss = 0
    all_preds = []
    all_labels = []
    all_probs = []
    
    for batch_idx, (X, y) in enumerate(train_loader):
        X, y = X.to(device), y.to(device)
        
        optimizer.zero_grad()
        outputs = model(X).squeeze(-1)
        loss = criterion(outputs, y)
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
        
        probs = torch.sigmoid(outputs).detach().cpu().numpy()
        preds = (probs > 0.5).astype(int)
        
        all_probs.extend(probs)
        all_preds.extend(preds)
        all_labels.extend(y.cpu().numpy())
    
    avg_loss = total_loss / len(train_loader)
    metrics = compute_metrics(
        np.array(all_labels), 
        np.array(all_preds), 
        np.array(all_probs)
    )
    metrics["loss"] = avg_loss
    
    return avg_loss, metrics


def validate(model, val_loader, criterion, device) -> Tuple[float, Dict]:
    """Validate the model."""
    model.eval()
    total_loss = 0
    all_preds = []
    all_labels = []
    all_probs = []
    
    with torch.no_grad():
        for X, y in val_loader:
            X, y = X.to(device), y.to(device)
            
            outputs = model(X).squeeze(-1)
            loss = criterion(outputs, y)
            
            total_loss += loss.item()
            
            probs = torch.sigmoid(outputs).cpu().numpy()
            preds = (probs > 0.5).astype(int)
            
            all_probs.extend(probs)
            all_preds.extend(preds)
            all_labels.extend(y.cpu().numpy())
    
    avg_loss = total_loss / len(val_loader)
    metrics = compute_metrics(
        np.array(all_labels), 
        np.array(all_preds), 
        np.array(all_probs)
    )
    metrics["loss"] = avg_loss
    
    return avg_loss, metrics


# ====================================================
# EARLY STOPPING
# ====================================================

class EarlyStopping:
    """
    Early stopping based on validation recall (not loss).
    
    Phase-1 prioritizes RECALL - we stop when recall stops improving.
    """
    
    def __init__(self, patience: int = 10, min_delta: float = 0.001):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_recall = 0.0
        self.early_stop = False
        
    def __call__(self, recall: float) -> bool:
        if recall > self.best_recall + self.min_delta:
            self.best_recall = recall
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True
        return self.early_stop


# ====================================================
# MAIN TRAINING FUNCTION
# ====================================================

def train_phase1(config: Dict = None):
    """
    Main training function for Phase-1 CNN.
    """
    if config is None:
        config = DEFAULT_CONFIG.copy()
    
    print("=" * 70)
    print("Phase-1 BGC Discovery: CNN Training")
    print("=" * 70)
    
    # ─────────────────────────────────────────────────
    # Setup device
    # ─────────────────────────────────────────────────
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nDevice: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    
    # ─────────────────────────────────────────────────
    # Load data
    # ─────────────────────────────────────────────────
    
    train_loader, val_loader = load_data(
        config["train_path"], 
        config["val_path"], 
        config["batch_size"]
    )
    
    # ─────────────────────────────────────────────────
    # Initialize model
    # ─────────────────────────────────────────────────
    
    print(f"\nInitializing model (variant: {config['model_variant']})...")
    model = get_model(config["model_variant"], device)
    print(f"  Parameters: {count_parameters(model):,}")
    
    # ─────────────────────────────────────────────────
    # Loss, optimizer, scheduler
    # ─────────────────────────────────────────────────
    
    # Weighted BCE Loss for high recall (penalize false negatives)
    pos_weight = torch.tensor([2.5], device=device)  # 2.5x penalty for missing BGCs
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    
    optimizer = optim.AdamW(
        model.parameters(),
        lr=config["learning_rate"],
        weight_decay=config["weight_decay"]
    )
    
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, 
        mode='max',  # Maximize recall
        factor=0.5, 
        patience=5,
        verbose=True
    )
    
    early_stopping = EarlyStopping(
        patience=config["patience"],
        min_delta=config["min_delta"]
    )
    
    # ─────────────────────────────────────────────────
    # Create output directory
    # ─────────────────────────────────────────────────
    
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # ─────────────────────────────────────────────────
    # Training loop
    # ─────────────────────────────────────────────────
    
    print(f"\n{'='*70}")
    print("Starting training...")
    print(f"{'='*70}\n")
    
    best_recall = 0.0
    best_model_state = None
    history = {"train": [], "val": []}
    
    for epoch in range(1, config["epochs"] + 1):
        epoch_start = time.time()
        
        # Train
        train_loss, train_metrics = train_epoch(
            model, train_loader, criterion, optimizer, device
        )
        
        # Validate
        val_loss, val_metrics = validate(
            model, val_loader, criterion, device
        )
        
        epoch_time = time.time() - epoch_start
        
        # Record history
        history["train"].append(train_metrics)
        history["val"].append(val_metrics)
        
        # Print progress
        print(f"Epoch {epoch:02d}/{config['epochs']} ({epoch_time:.1f}s)")
        print(f"  Train - Loss: {train_loss:.4f}, Recall: {train_metrics['recall']:.4f}, "
              f"Acc: {train_metrics['accuracy']:.4f}")
        print(f"  Val   - Loss: {val_loss:.4f}, Recall: {val_metrics['recall']:.4f}, "
              f"Acc: {val_metrics['accuracy']:.4f}, AUC: {val_metrics['auc_roc']:.4f}")
        
        # Check if best model (by recall)
        if val_metrics['recall'] > best_recall:
            best_recall = val_metrics['recall']
            best_model_state = model.state_dict().copy()
            print(f"  ★ New best recall: {best_recall:.4f}")
            
            # Save checkpoint
            checkpoint_path = output_dir / "best_model.pt"
            torch.save({
                'epoch': epoch,
                'model_state_dict': best_model_state,
                'optimizer_state_dict': optimizer.state_dict(),
                'recall': best_recall,
                'config': config,
            }, checkpoint_path)
        
        print()
        
        # Learning rate scheduling
        scheduler.step(val_metrics['recall'])
        
        # Early stopping
        if early_stopping(val_metrics['recall']):
            print(f"Early stopping triggered at epoch {epoch}")
            break
    
    # ─────────────────────────────────────────────────
    # Save final model
    # ─────────────────────────────────────────────────
    
    print(f"\n{'='*70}")
    print("Training complete!")
    print(f"{'='*70}")
    
    # Load best model
    model.load_state_dict(best_model_state)
    
    # Final validation
    print("\nFinal validation metrics:")
    _, final_metrics = validate(model, val_loader, criterion, device)
    print_metrics(final_metrics, prefix="  ")
    
    # Check success criterion
    print(f"\n{'='*70}")
    if final_metrics['recall'] >= 0.9:
        print("✅ SUCCESS: Recall > 0.9 achieved!")
        print("   Phase-1 model is ready for genome scanning.")
    else:
        print(f"⚠️  Recall = {final_metrics['recall']:.4f} (target: > 0.9)")
        print("   Consider: more epochs, larger model, or threshold tuning.")
    print(f"{'='*70}")
    
    # Save final model for deployment
    final_model_path = output_dir / config["model_name"]
    torch.save({
        'model_state_dict': model.state_dict(),
        'config': config,
        'final_metrics': final_metrics,
    }, final_model_path)
    print(f"\nModel saved to: {final_model_path}")
    
    # Save training history
    history_path = output_dir / "training_history.pt"
    torch.save(history, history_path)
    print(f"History saved to: {history_path}")
    
    return model, final_metrics, history


# ====================================================
# THRESHOLD OPTIMIZATION (for high recall)
# ====================================================

def optimize_threshold_for_recall(model, val_loader, device, target_recall: float = 0.95):
    """
    Find the threshold that achieves target recall.
    
    For Phase-1 filtering, we want HIGH RECALL (don't miss BGCs).
    """
    print(f"\nOptimizing threshold for recall ≥ {target_recall}...")
    
    model.eval()
    all_probs = []
    all_labels = []
    
    with torch.no_grad():
        for X, y in val_loader:
            X = X.to(device)
            logits = model(X).squeeze(-1)
            probs = torch.sigmoid(logits).cpu().numpy()
            all_probs.extend(probs)
            all_labels.extend(y.numpy())
    
    all_probs = np.array(all_probs)
    all_labels = np.array(all_labels)
    
    # Search for optimal threshold
    best_threshold = 0.5
    best_f1 = 0.0
    
    for threshold in np.arange(0.1, 0.9, 0.01):
        preds = (all_probs >= threshold).astype(int)
        recall = recall_score(all_labels, preds)
        
        if recall >= target_recall:
            f1 = f1_score(all_labels, preds)
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = threshold
    
    # Final metrics at best threshold
    final_preds = (all_probs >= best_threshold).astype(int)
    final_recall = recall_score(all_labels, final_preds)
    final_precision = precision_score(all_labels, final_preds)
    final_f1 = f1_score(all_labels, final_preds)
    
    print(f"  Optimal threshold: {best_threshold:.2f}")
    print(f"  Recall:    {final_recall:.4f}")
    print(f"  Precision: {final_precision:.4f}")
    print(f"  F1:        {final_f1:.4f}")
    
    return best_threshold


# ====================================================
# CLI
# ====================================================

def parse_args():
    parser = argparse.ArgumentParser(description="Train Phase-1 BGC CNN")
    
    parser.add_argument("--train-path", type=str, default="./preprocessed_data/train.pt")
    parser.add_argument("--val-path", type=str, default="./preprocessed_data/val.pt")
    parser.add_argument("--model-variant", type=str, default="standard", 
                        choices=["standard", "large"])
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--output-dir", type=str, default="./phase1_output/")
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    config = DEFAULT_CONFIG.copy()
    config["train_path"] = args.train_path
    config["val_path"] = args.val_path
    config["model_variant"] = args.model_variant
    config["batch_size"] = args.batch_size
    config["epochs"] = args.epochs
    config["learning_rate"] = args.lr
    config["output_dir"] = args.output_dir
    
    model, metrics, history = train_phase1(config)
    
    # Optimize threshold for high recall
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_loader, val_loader = load_data(
        config["train_path"], 
        config["val_path"], 
        config["batch_size"]
    )
    optimal_threshold = optimize_threshold_for_recall(
        model, val_loader, device, target_recall=0.95
    )
    
    # Save threshold
    threshold_path = Path(config["output_dir"]) / "optimal_threshold.txt"
    with open(threshold_path, 'w') as f:
        f.write(f"{optimal_threshold}")
    print(f"\nOptimal threshold saved to: {threshold_path}")
