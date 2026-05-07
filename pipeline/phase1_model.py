"""
Phase-1 BGC Discovery: 1D CNN Model
===================================
Topology-preserving convolutional neural network for biosynthetic likelihood scoring.

Architecture: 1D CNN (NOT Transformer, NOT Graph)
- Preserves local sequence patterns
- Fast inference for genome scanning
- Works on fragments (1000 bp windows)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class Phase1CNN(nn.Module):
    """
    1D Convolutional Neural Network for BGC detection.
    
    Input:  (batch, seq_len=1000, channels=4)  [one-hot DNA]
    Output: (batch, 1) probability score
    
    Architecture:
    - 4 convolutional blocks with increasing filters
    - BatchNorm + ReLU + MaxPool after each conv
    - Global average pooling
    - Fully connected classifier
    """
    
    def __init__(self, 
                 seq_len: int = 1000,
                 in_channels: int = 4,
                 dropout: float = 0.3):
        super().__init__()
        
        self.seq_len = seq_len
        self.in_channels = in_channels
        
        # ─────────────────────────────────────────────────
        # Convolutional blocks (capture local motifs)
        # ─────────────────────────────────────────────────
        
        # Block 1: Capture short motifs (3-15 bp)
        self.conv1 = nn.Conv1d(in_channels, 64, kernel_size=15, padding=7)
        self.bn1 = nn.BatchNorm1d(64)
        self.pool1 = nn.MaxPool1d(kernel_size=4, stride=4)
        
        # Block 2: Capture medium motifs
        self.conv2 = nn.Conv1d(64, 128, kernel_size=11, padding=5)
        self.bn2 = nn.BatchNorm1d(128)
        self.pool2 = nn.MaxPool1d(kernel_size=4, stride=4)
        
        # Block 3: Capture longer patterns
        self.conv3 = nn.Conv1d(128, 256, kernel_size=7, padding=3)
        self.bn3 = nn.BatchNorm1d(256)
        self.pool3 = nn.MaxPool1d(kernel_size=4, stride=4)
        
        # Block 4: High-level features
        self.conv4 = nn.Conv1d(256, 512, kernel_size=5, padding=2)
        self.bn4 = nn.BatchNorm1d(512)
        
        # ─────────────────────────────────────────────────
        # Global pooling + Classifier
        # ─────────────────────────────────────────────────
        
        self.global_pool = nn.AdaptiveAvgPool1d(1)
        self.dropout = nn.Dropout(dropout)
        
        # Fully connected layers
        self.fc1 = nn.Linear(512, 128)
        self.fc2 = nn.Linear(128, 1)
        
    def forward(self, x):
        """
        Forward pass.
        
        Args:
            x: Input tensor of shape (batch, seq_len, 4)
               One-hot encoded DNA sequences
               
        Returns:
            Probability score (batch, 1)
        """
        # Input shape: (batch, seq_len, 4)
        # Conv1d expects: (batch, channels, seq_len)
        x = x.transpose(1, 2)
        
        # Convolutional blocks
        x = self.pool1(F.relu(self.bn1(self.conv1(x))))
        x = self.pool2(F.relu(self.bn2(self.conv2(x))))
        x = self.pool3(F.relu(self.bn3(self.conv3(x))))
        x = F.relu(self.bn4(self.conv4(x)))
        
        # Global pooling: (batch, 512, seq_reduced) → (batch, 512, 1)
        x = self.global_pool(x)
        x = x.squeeze(-1)  # (batch, 512)
        
        # Classifier
        x = self.dropout(x)
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.fc2(x)
        
        # Output logits (sigmoid will be applied in BCEWithLogitsLoss)
        # x = torch.sigmoid(x)  # Removed - let loss function handle this
        
        return x
    
    def predict_score(self, x):
        """
        Get biosynthetic likelihood score (for scanning).
        
        Args:
            x: One-hot encoded DNA window (batch, 1000, 4)
            
        Returns:
            Score between 0 and 1
        """
        self.eval()
        with torch.no_grad():
            logits = self.forward(x).squeeze(-1)
            return torch.sigmoid(logits)


class Phase1CNNLarge(nn.Module):
    """
    Larger 1D CNN variant for higher accuracy.
    Use if GPU memory allows and you need better recall.
    """
    
    def __init__(self, 
                 seq_len: int = 1000,
                 in_channels: int = 4,
                 dropout: float = 0.4):
        super().__init__()
        
        self.seq_len = seq_len
        
        # Multi-scale convolutions (capture different motif sizes simultaneously)
        self.conv_3 = nn.Conv1d(in_channels, 64, kernel_size=3, padding=1)
        self.conv_7 = nn.Conv1d(in_channels, 64, kernel_size=7, padding=3)
        self.conv_15 = nn.Conv1d(in_channels, 64, kernel_size=15, padding=7)
        self.conv_25 = nn.Conv1d(in_channels, 64, kernel_size=25, padding=12)
        
        # Merge multi-scale features
        self.bn1 = nn.BatchNorm1d(256)
        self.pool1 = nn.MaxPool1d(4, 4)
        
        # Deep blocks
        self.conv2 = nn.Conv1d(256, 256, kernel_size=7, padding=3)
        self.bn2 = nn.BatchNorm1d(256)
        self.pool2 = nn.MaxPool1d(4, 4)
        
        self.conv3 = nn.Conv1d(256, 512, kernel_size=5, padding=2)
        self.bn3 = nn.BatchNorm1d(512)
        self.pool3 = nn.MaxPool1d(4, 4)
        
        self.conv4 = nn.Conv1d(512, 512, kernel_size=3, padding=1)
        self.bn4 = nn.BatchNorm1d(512)
        
        # Classifier
        self.global_pool = nn.AdaptiveAvgPool1d(1)
        self.dropout = nn.Dropout(dropout)
        self.fc1 = nn.Linear(512, 256)
        self.fc2 = nn.Linear(256, 64)
        self.fc3 = nn.Linear(64, 1)
        
    def forward(self, x):
        # (batch, seq_len, 4) → (batch, 4, seq_len)
        x = x.transpose(1, 2)
        
        # Multi-scale feature extraction
        x3 = F.relu(self.conv_3(x))
        x7 = F.relu(self.conv_7(x))
        x15 = F.relu(self.conv_15(x))
        x25 = F.relu(self.conv_25(x))
        
        # Concatenate multi-scale features
        x = torch.cat([x3, x7, x15, x25], dim=1)  # (batch, 256, seq_len)
        x = self.pool1(F.relu(self.bn1(x)))
        
        # Deep convolutions
        x = self.pool2(F.relu(self.bn2(self.conv2(x))))
        x = self.pool3(F.relu(self.bn3(self.conv3(x))))
        x = F.relu(self.bn4(self.conv4(x)))
        
        # Global pooling + classifier
        x = self.global_pool(x).squeeze(-1)
        x = self.dropout(x)
        x = F.relu(self.fc1(x))
        x = self.dropout(x)
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        
        return x  # Return logits for BCEWithLogitsLoss
    
    def predict_score(self, x):
        self.eval()
        with torch.no_grad():
            logits = self.forward(x).squeeze(-1)
            return torch.sigmoid(logits)


def get_model(variant: str = "standard", device: str = "cuda") -> nn.Module:
    """
    Factory function to get Phase-1 model.
    
    Args:
        variant: "standard" or "large"
        device: "cuda" or "cpu"
        
    Returns:
        Initialized model on specified device
    """
    if variant == "standard":
        model = Phase1CNN()
    elif variant == "large":
        model = Phase1CNNLarge()
    else:
        raise ValueError(f"Unknown variant: {variant}")
    
    return model.to(device)


def count_parameters(model: nn.Module) -> int:
    """Count trainable parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    # Test model
    print("=" * 60)
    print("Phase-1 CNN Model Test")
    print("=" * 60)
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    
    # Test standard model
    model = get_model("standard", device)
    print(f"\nStandard model parameters: {count_parameters(model):,}")
    
    # Test forward pass
    batch = torch.randn(8, 1000, 4).to(device)
    output = model(batch)
    print(f"Input shape:  {batch.shape}")
    print(f"Output shape: {output.shape}")
    print(f"Output range: [{output.min().item():.4f}, {output.max().item():.4f}]")
    
    # Test large model
    model_large = get_model("large", device)
    print(f"\nLarge model parameters: {count_parameters(model_large):,}")
    
    output_large = model_large(batch)
    print(f"Output shape: {output_large.shape}")
    
    print("\n✅ Model test passed!")
