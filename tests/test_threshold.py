"""
Phase-1 Quick Recall Fix: Test Lower Threshold
===============================================
Test if lowering threshold to 0.25 achieves recall > 0.9
without retraining (fastest solution).
"""

import torch
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

def test_thresholds():
    print("Testing different thresholds for recall optimization...")
    
    # Load validation data
    data_val = torch.load('./preprocessed_data/val.pt', weights_only=True)
    X_val, y_val = data_val['X'], data_val['y']
    
    # Load trained model
    checkpoint = torch.load('./phase1_output/phase1_cnn.pt', map_location='cpu', weights_only=False)
    
    # Get model
    from phase1_model import get_model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = get_model("standard", device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    # Get predictions
    X_val = X_val.to(device)
    with torch.no_grad():
        probs = model(X_val).squeeze(-1).cpu().numpy()
    
    y_true = y_val.numpy()
    
    # Test different thresholds
    thresholds = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]
    
    print("\nThreshold Analysis:")
    print("Thresh  Recall  Precision  F1     Accuracy")
    print("-" * 45)
    
    best_threshold = 0.5
    best_recall = 0.0
    
    for threshold in thresholds:
        preds = (probs >= threshold).astype(int)
        
        recall = recall_score(y_true, preds)
        precision = precision_score(y_true, preds, zero_division=0)
        f1 = f1_score(y_true, preds, zero_division=0)
        accuracy = accuracy_score(y_true, preds)
        
        print(f"{threshold:.2f}    {recall:.3f}   {precision:.3f}     {f1:.3f}   {accuracy:.3f}")
        
        if recall >= 0.9 and recall > best_recall:
            best_recall = recall
            best_threshold = threshold
    
    print("-" * 45)
    if best_recall >= 0.9:
        print(f"✅ SUCCESS: Threshold {best_threshold} achieves recall = {best_recall:.3f}")
        print("✅ Phase-1 is READY - no retraining needed!")
        
        # Save optimal threshold
        with open('./phase1_output/optimal_threshold.txt', 'w') as f:
            f.write(str(best_threshold))
        print(f"✅ Saved optimal threshold: {best_threshold}")
        
        return True, best_threshold
    else:
        print(f"❌ Best recall: {best_recall:.3f} (need ≥ 0.9)")
        print("❌ Need to retrain with weighted BCE loss")
        return False, best_threshold

if __name__ == "__main__":
    success, threshold = test_thresholds()