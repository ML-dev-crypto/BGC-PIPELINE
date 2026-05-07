"""
Phase-1 Recall Fix: Retrain with Weighted BCE Loss
==================================================
Quick retraining with recall-optimized settings.
"""

from train_phase1 import train_phase1

# Optimized config for recall
config = {
    "train_path": "./preprocessed_data/train.pt",
    "val_path": "./preprocessed_data/val.pt",
    "model_variant": "standard",
    "batch_size": 64,
    "epochs": 20,  # Reduced epochs
    "learning_rate": 1e-3,
    "weight_decay": 1e-4,
    "patience": 8,  # Earlier stopping
    "min_delta": 0.001,
    "output_dir": "./phase1_output/",
    "model_name": "phase1_cnn_recall.pt",
}

print("🎯 Retraining Phase-1 with recall optimization...")
print("  - Weighted BCE Loss (pos_weight=2.5)")
print("  - Recall-focused early stopping")
print("  - Max 20 epochs")

model, metrics, history = train_phase1(config)

if metrics['recall'] >= 0.9:
    print("\n✅ SUCCESS: Phase-1 model ready for genome scanning!")
else:
    print(f"\n⚠️ Recall = {metrics['recall']:.3f}, consider threshold tuning")