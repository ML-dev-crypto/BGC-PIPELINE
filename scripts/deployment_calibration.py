"""
Phase-1 Deployment Calibration
===============================
Find the optimal threshold for genome scanning.

Success criteria:
- Recall ≥ 0.9
- Genome flagged ≤ 5-10%
"""

import torch
import numpy as np
from sklearn.metrics import recall_score, precision_score

def deployment_calibration():
    print("🎯 Phase-1 Deployment Calibration")
    print("=" * 50)
    
    # Load validation data
    data_val = torch.load('./preprocessed_data/val.pt', weights_only=True)
    X_val, y_val = data_val['X'], data_val['y']
    
    # Load BEST model (Smart Save from final training)
    checkpoint = torch.load('./phase1_output/phase1_final.pt', weights_only=False)
    print(f"Using final model: Epoch {checkpoint['epoch']}, Quality Score = {checkpoint['quality_score']:.4f}")
    print(f"  Recall: {checkpoint['recall']:.4f}, Accuracy: {checkpoint['accuracy']:.4f}")
    
    # Initialize model
    from phase1_model import get_model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = get_model("standard", device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    # Get validation predictions
    X_val = X_val.to(device)
    with torch.no_grad():
        probs = model.predict_score(X_val).cpu().numpy()
    
    y_true = y_val.numpy()
    
    # Test deployment thresholds
    thresholds = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]
    
    print("\nDeployment Threshold Analysis:")
    print("Threshold  Recall   Precision  Flagged%  Status")
    print("-" * 55)
    
    optimal_threshold = None
    
    for threshold in thresholds:
        preds = (probs >= threshold).astype(int)
        
        recall = recall_score(y_true, preds)
        precision = precision_score(y_true, preds, zero_division=0)
        flagged_pct = (preds == 1).mean() * 100  # % of genome flagged
        
        # Check success criteria
        status = ""
        if recall >= 0.9 and flagged_pct <= 10:
            status = "✅ GOOD"
            if optimal_threshold is None:
                optimal_threshold = threshold
        elif recall >= 0.9:
            status = "⚠️ High flagged"
        else:
            status = "❌ Low recall"
        
        print(f"{threshold:.2f}       {recall:.3f}    {precision:.3f}     {flagged_pct:.1f}%     {status}")
    
    print("-" * 55)
    
    if optimal_threshold:
        print(f"\n🎯 OPTIMAL THRESHOLD: {optimal_threshold}")
        print(f"   This achieves recall ≥ 0.9 while flagging ≤ 10% of genome")
        
        # Save optimal threshold
        with open('./phase1_output/deployment_threshold.txt', 'w') as f:
            f.write(str(optimal_threshold))
        print(f"   Saved to: ./phase1_output/deployment_threshold.txt")
        
        print("\n✅ PHASE-1 IS READY FOR GENOME SCANNING!")
        print("   Use: python scan_genome.py --input genome.fasta --output results.tsv")
        
    else:
        print("\n⚠️ No threshold found that meets both criteria")
        print("   Recommended: Use threshold 0.25 for high recall")
        
        # Default to 0.25 for high recall
        with open('./phase1_output/deployment_threshold.txt', 'w') as f:
            f.write('0.25')
        
        print("   Saved threshold 0.25 for deployment")
    
    print("\n" + "=" * 50)
    print("Phase-1 deployment calibration complete!")
    return optimal_threshold

if __name__ == "__main__":
    deployment_calibration()