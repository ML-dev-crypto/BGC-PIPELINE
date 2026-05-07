"""
Phase-1 Final Fix: Smart Save Training
======================================
Train with Quality Score = Recall × Accuracy to avoid "Yes-Man" models.
Saves the balanced model, not the extreme recall model.
"""

import os
import time
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np

from phase1_model import get_model

# CONFIG
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
LR = 1e-4  # Lower learning rate to prevent instability
WEIGHT_DECAY = 1e-4
POS_WEIGHT = torch.tensor([2.0]).to(DEVICE)  # Reduced from 2.5
EPOCHS = 15
BATCH_SIZE = 64

def train_final_fix():
    print("🚀 Phase-1 Final Training (Smart Save Mode)")
    print("=" * 60)
    print(f"Device: {DEVICE}")
    if DEVICE.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    
    # ────────────────────────────────────────────────
    # Load Data
    # ────────────────────────────────────────────────
    
    print("\nLoading data...")
    train_data = torch.load('./preprocessed_data/train.pt', weights_only=True)
    val_data = torch.load('./preprocessed_data/val.pt', weights_only=True)
    
    X_train, y_train = train_data['X'], train_data['y']
    X_val, y_val = val_data['X'], val_data['y']
    
    train_dataset = TensorDataset(X_train, y_train.float())
    val_dataset = TensorDataset(X_val, y_val.float())
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    
    print(f"  Train: {len(X_train):,} samples")
    print(f"  Val:   {len(X_val):,} samples")
    
    # ────────────────────────────────────────────────
    # Initialize Model
    # ────────────────────────────────────────────────
    
    model = get_model("standard", DEVICE)
    optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    criterion = nn.BCEWithLogitsLoss(pos_weight=POS_WEIGHT)
    
    print(f"\nModel initialized with {sum(p.numel() for p in model.parameters()):,} parameters")
    
    # ────────────────────────────────────────────────
    # Training Loop with SMART SAVE
    # ────────────────────────────────────────────────
    
    best_quality_score = 0.0
    best_epoch = 0
    
    print(f"\n{'='*60}")
    print("Starting Smart Save Training...")
    print("Quality Score = Recall × Accuracy (avoids Yes-Man models)")
    print(f"{'='*60}\n")
    
    for epoch in range(EPOCHS):
        epoch_start = time.time()
        
        # ────── TRAINING ──────
        model.train()
        train_loss = 0
        for batch_idx, (inputs, labels) in enumerate(train_loader):
            inputs, labels = inputs.to(DEVICE), labels.to(DEVICE)
            
            optimizer.zero_grad()
            outputs = model(inputs).squeeze(-1)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
        
        avg_train_loss = train_loss / len(train_loader)
        
        # ────── VALIDATION ──────
        model.eval()
        tp, fn, fp, tn = 0, 0, 0, 0
        val_loss = 0
        
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(DEVICE), labels.to(DEVICE)
                outputs = model(inputs).squeeze(-1)
                loss = criterion(outputs, labels)
                val_loss += loss.item()
                
                # Convert to predictions
                probs = torch.sigmoid(outputs)
                preds = (probs > 0.5).float()
                
                # Confusion matrix
                tp += ((preds == 1) & (labels == 1)).sum().item()
                fn += ((preds == 0) & (labels == 1)).sum().item()
                fp += ((preds == 1) & (labels == 0)).sum().item()
                tn += ((preds == 0) & (labels == 0)).sum().item()
        
        avg_val_loss = val_loss / len(val_loader)
        
        # ────── METRICS ──────
        recall = tp / (tp + fn + 1e-8)
        accuracy = (tp + tn) / (tp + tn + fp + fn + 1e-8)
        precision = tp / (tp + fp + 1e-8)
        
        # 🎯 THE SMART QUALITY SCORE
        # Penalizes models with high recall but terrible precision/accuracy
        quality_score = recall * accuracy
        
        epoch_time = time.time() - epoch_start
        
        # ────── LOGGING ──────
        print(f"Epoch {epoch+1:02d}/{EPOCHS} ({epoch_time:.1f}s)")
        print(f"  Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f}")
        print(f"  Recall: {recall:.4f} | Precision: {precision:.4f} | Accuracy: {accuracy:.4f}")
        print(f"  Quality Score: {quality_score:.4f} (Recall × Accuracy)")
        
        # ────── SMART SAVE CONDITION ──────
        # Must improve quality score AND meet minimum standards
        save_condition = (
            quality_score > best_quality_score and 
            recall > 0.80 and  # Minimum recall
            accuracy > 0.70    # Minimum accuracy
        )
        
        if save_condition:
            best_quality_score = quality_score
            best_epoch = epoch + 1
            
            # Save the SMART model
            os.makedirs('./phase1_output', exist_ok=True)
            torch.save({
                'epoch': epoch + 1,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'quality_score': quality_score,
                'recall': recall,
                'accuracy': accuracy,
                'precision': precision,
            }, './phase1_output/phase1_final.pt')
            
            print(f"  ★ SAVED NEW BEST MODEL (Quality Score: {quality_score:.4f})")
        
        print()
        
        # ────── GOLDILOCKS ZONE ──────
        # Perfect balance achieved - stop training
        if recall > 0.90 and accuracy > 0.85:
            print("  ✅ GOLDILOCKS ZONE HIT (Recall > 0.9, Accuracy > 0.85)")
            print("  🛑 STOPPING EARLY - Perfect balance achieved!")
            break
        
        # Prevent total collapse
        if recall < 0.5:
            print("  🛑 STOPPING - Model collapsed")
            break
    
    # ────────────────────────────────────────────────
    # Training Complete
    # ────────────────────────────────────────────────
    
    print(f"\n{'='*60}")
    print("Smart Save Training Complete!")
    print(f"{'='*60}")
    print(f"Best model saved from Epoch {best_epoch}")
    print(f"Quality Score: {best_quality_score:.4f}")
    print(f"Model saved to: ./phase1_output/phase1_final.pt")
    print(f"\n🎯 Next step: Run deployment calibration on the final model")
    print(f"{'='*60}")

if __name__ == "__main__":
    train_final_fix()