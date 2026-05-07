"""
Phase-1 BGC Discovery: Genome Scanner
======================================
Scan assembled contigs with trained Phase-1 CNN to identify candidate BGC regions.

This is the FIRST real "product output" - converts classifier into a genome scanner.

Input:  Assembled contigs (FASTA)
Output: Table of candidate BGC regions with scores

Usage:
    python scan_genome.py --input contigs.fasta --output results.tsv
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Generator
from dataclasses import dataclass
import json

import numpy as np
import torch
from Bio import SeqIO

from phase1_model import get_model


# ====================================================
# CONFIGURATION
# ====================================================

DEFAULT_CONFIG = {
    # Scanning parameters
    "window_size": 1000,        # bp (must match training)
    "stride": 250,              # bp (can be smaller than training for finer resolution)
    "min_contig_length": 1000,  # Skip contigs shorter than window
    
    # Scoring
    "threshold": 0.5,           # Default threshold (can be optimized)
    "merge_distance": 500,      # Merge regions within this distance
    
    # Model
    "model_path": "./phase1_output/phase1_cnn.pt",
    "model_variant": "standard",
    
    # Output
    "output_format": "tsv",     # "tsv" or "json"
    
    # Performance
    "batch_size": 256,          # Larger batches for faster scanning
    "device": "auto",           # "auto", "cuda", or "cpu"
}


# ====================================================
# DATA STRUCTURES
# ====================================================

@dataclass
class Window:
    """A single scanning window."""
    contig_id: str
    start: int
    end: int
    sequence: str


@dataclass
class ScoredWindow:
    """Window with Phase-1 score."""
    contig_id: str
    start: int
    end: int
    score: float


@dataclass
class CandidateRegion:
    """Merged candidate BGC region."""
    contig_id: str
    start: int
    end: int
    mean_score: float
    max_score: float
    n_windows: int
    length: int


# ====================================================
# DNA ENCODING
# ====================================================

def one_hot_encode(sequence: str) -> np.ndarray:
    """
    One-hot encode a DNA sequence.
    
    A → [1,0,0,0], C → [0,1,0,0], G → [0,0,1,0], T → [0,0,0,1]
    N/other → [0,0,0,0]
    """
    mapping = {
        'A': [1, 0, 0, 0],
        'C': [0, 1, 0, 0],
        'G': [0, 0, 1, 0],
        'T': [0, 0, 0, 1]
    }
    default = [0, 0, 0, 0]
    
    encoded = np.array(
        [mapping.get(base, default) for base in sequence.upper()],
        dtype=np.float32
    )
    return encoded


# ====================================================
# GENOME SCANNER
# ====================================================

class GenomeScanner:
    """
    Phase-1 genome scanner.
    
    Scans contigs with sliding windows and scores each window
    using the trained Phase-1 CNN.
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or DEFAULT_CONFIG.copy()
        
        # Setup device
        if self.config["device"] == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(self.config["device"])
        
        # Load model
        self.model = self._load_model()
        
        print(f"GenomeScanner initialized")
        print(f"  Device: {self.device}")
        print(f"  Window: {self.config['window_size']} bp")
        print(f"  Stride: {self.config['stride']} bp")
        print(f"  Threshold: {self.config['threshold']}")
    
    def _load_model(self) -> torch.nn.Module:
        """Load trained Phase-1 model."""
        model_path = self.config["model_path"]
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {model_path}")
        
        # Load checkpoint
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        
        # Get model variant from checkpoint if available
        if 'config' in checkpoint:
            variant = checkpoint['config'].get('model_variant', self.config['model_variant'])
        else:
            variant = self.config['model_variant']
        
        # Initialize model
        model = get_model(variant, self.device)
        model.load_state_dict(checkpoint['model_state_dict'])
        model.eval()
        
        print(f"  Loaded model from: {model_path}")
        
        return model
    
    def _sliding_windows(self, contig_id: str, sequence: str) -> Generator[Window, None, None]:
        """Generate sliding windows over a contig."""
        window_size = self.config["window_size"]
        stride = self.config["stride"]
        seq_len = len(sequence)
        
        for start in range(0, seq_len - window_size + 1, stride):
            end = start + window_size
            yield Window(
                contig_id=contig_id,
                start=start,
                end=end,
                sequence=sequence[start:end]
            )
    
    def _score_batch(self, windows: List[Window]) -> List[ScoredWindow]:
        """Score a batch of windows."""
        if not windows:
            return []
        
        # Encode sequences
        encoded = np.stack([
            one_hot_encode(w.sequence) for w in windows
        ])
        
        # Convert to tensor
        X = torch.from_numpy(encoded).to(self.device)
        
        # Get predictions
        with torch.no_grad():
            scores = self.model.predict_score(X).cpu().numpy()
        
        # Create scored windows
        scored_windows = []
        for window, score in zip(windows, scores):
            scored_windows.append(ScoredWindow(
                contig_id=window.contig_id,
                start=window.start,
                end=window.end,
                score=float(score)
            ))
        
        return scored_windows
    
    def scan_contig(self, contig_id: str, sequence: str) -> List[ScoredWindow]:
        """Scan a single contig and return scored windows."""
        # Skip short contigs
        if len(sequence) < self.config["min_contig_length"]:
            return []
        
        # Collect windows in batches
        windows = list(self._sliding_windows(contig_id, sequence))
        
        if not windows:
            return []
        
        # Score in batches
        batch_size = self.config["batch_size"]
        scored_windows = []
        
        for i in range(0, len(windows), batch_size):
            batch = windows[i:i + batch_size]
            scored = self._score_batch(batch)
            scored_windows.extend(scored)
        
        return scored_windows
    
    def scan_fasta(self, fasta_path: str, verbose: bool = True) -> List[ScoredWindow]:
        """Scan all contigs in a FASTA file."""
        all_scored_windows = []
        
        if verbose:
            print(f"\nScanning: {fasta_path}")
        
        # Parse FASTA
        contigs = list(SeqIO.parse(fasta_path, "fasta"))
        
        if verbose:
            print(f"  Found {len(contigs)} contigs")
        
        for i, record in enumerate(contigs):
            contig_id = record.id
            sequence = str(record.seq).upper()
            
            scored = self.scan_contig(contig_id, sequence)
            all_scored_windows.extend(scored)
            
            if verbose and (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(contigs)} contigs...")
        
        if verbose:
            print(f"  Total windows scored: {len(all_scored_windows)}")
        
        return all_scored_windows
    
    def filter_by_threshold(self, scored_windows: List[ScoredWindow]) -> List[ScoredWindow]:
        """Filter windows by score threshold."""
        threshold = self.config["threshold"]
        filtered = [w for w in scored_windows if w.score >= threshold]
        return filtered
    
    def merge_overlapping_regions(self, scored_windows: List[ScoredWindow]) -> List[CandidateRegion]:
        """
        Merge overlapping high-scoring windows into candidate regions.
        
        This is CRITICAL for producing sensible BGC predictions
        (not random noise, not whole contigs).
        """
        if not scored_windows:
            return []
        
        merge_distance = self.config["merge_distance"]
        
        # Group by contig
        by_contig = {}
        for sw in scored_windows:
            if sw.contig_id not in by_contig:
                by_contig[sw.contig_id] = []
            by_contig[sw.contig_id].append(sw)
        
        # Merge within each contig
        candidate_regions = []
        
        for contig_id, windows in by_contig.items():
            # Sort by start position
            windows.sort(key=lambda w: w.start)
            
            # Merge overlapping/nearby windows
            current_region = {
                "start": windows[0].start,
                "end": windows[0].end,
                "scores": [windows[0].score]
            }
            
            for window in windows[1:]:
                # Check if window overlaps or is close to current region
                if window.start <= current_region["end"] + merge_distance:
                    # Extend region
                    current_region["end"] = max(current_region["end"], window.end)
                    current_region["scores"].append(window.score)
                else:
                    # Save current region and start new one
                    candidate_regions.append(CandidateRegion(
                        contig_id=contig_id,
                        start=current_region["start"],
                        end=current_region["end"],
                        mean_score=np.mean(current_region["scores"]),
                        max_score=np.max(current_region["scores"]),
                        n_windows=len(current_region["scores"]),
                        length=current_region["end"] - current_region["start"]
                    ))
                    
                    current_region = {
                        "start": window.start,
                        "end": window.end,
                        "scores": [window.score]
                    }
            
            # Don't forget the last region
            candidate_regions.append(CandidateRegion(
                contig_id=contig_id,
                start=current_region["start"],
                end=current_region["end"],
                mean_score=np.mean(current_region["scores"]),
                max_score=np.max(current_region["scores"]),
                n_windows=len(current_region["scores"]),
                length=current_region["end"] - current_region["start"]
            ))
        
        # Sort by score
        candidate_regions.sort(key=lambda r: r.max_score, reverse=True)
        
        return candidate_regions


# ====================================================
# OUTPUT FORMATTING
# ====================================================

def save_results_tsv(regions: List[CandidateRegion], output_path: str):
    """Save results as TSV file."""
    with open(output_path, 'w') as f:
        # Header
        f.write("contig_id\tstart\tend\tlength\tmean_score\tmax_score\tn_windows\n")
        
        # Data
        for r in regions:
            f.write(f"{r.contig_id}\t{r.start}\t{r.end}\t{r.length}\t"
                    f"{r.mean_score:.4f}\t{r.max_score:.4f}\t{r.n_windows}\n")
    
    print(f"Results saved to: {output_path}")


def save_results_json(regions: List[CandidateRegion], output_path: str):
    """Save results as JSON file."""
    data = {
        "n_regions": len(regions),
        "regions": [
            {
                "contig_id": r.contig_id,
                "start": r.start,
                "end": r.end,
                "length": r.length,
                "mean_score": round(r.mean_score, 4),
                "max_score": round(r.max_score, 4),
                "n_windows": r.n_windows
            }
            for r in regions
        ]
    }
    
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Results saved to: {output_path}")


def print_summary(regions: List[CandidateRegion], scored_windows: List[ScoredWindow]):
    """Print scanning summary."""
    print("\n" + "=" * 60)
    print("SCANNING SUMMARY")
    print("=" * 60)
    
    print(f"\nTotal windows scored: {len(scored_windows)}")
    print(f"Candidate regions found: {len(regions)}")
    
    if regions:
        lengths = [r.length for r in regions]
        scores = [r.max_score for r in regions]
        
        print(f"\nRegion statistics:")
        print(f"  Total bp in candidates: {sum(lengths):,}")
        print(f"  Mean region length: {np.mean(lengths):,.0f} bp")
        print(f"  Median region length: {np.median(lengths):,.0f} bp")
        print(f"  Min/Max length: {min(lengths):,} - {max(lengths):,} bp")
        
        print(f"\nScore statistics:")
        print(f"  Mean max_score: {np.mean(scores):.4f}")
        print(f"  Score range: {min(scores):.4f} - {max(scores):.4f}")
        
        print(f"\nTop 10 candidate regions:")
        for i, r in enumerate(regions[:10], 1):
            print(f"  {i}. {r.contig_id}:{r.start}-{r.end} "
                  f"({r.length:,} bp, score={r.max_score:.3f})")
    
    print("=" * 60)


# ====================================================
# MAIN FUNCTION
# ====================================================

def scan_genome(
    input_fasta: str,
    output_path: str,
    model_path: str = None,
    threshold: float = None,
    stride: int = None,
    output_format: str = "tsv"
) -> List[CandidateRegion]:
    """
    Main scanning function.
    
    Args:
        input_fasta: Path to input FASTA file
        output_path: Path for output results
        model_path: Path to trained Phase-1 model
        threshold: Score threshold for filtering
        stride: Scanning stride (smaller = finer resolution)
        output_format: "tsv" or "json"
        
    Returns:
        List of candidate BGC regions
    """
    # Build config
    config = DEFAULT_CONFIG.copy()
    
    if model_path:
        config["model_path"] = model_path
    if threshold:
        config["threshold"] = threshold
    if stride:
        config["stride"] = stride
    config["output_format"] = output_format
    
    # Try to load optimized threshold if available
    threshold_file = Path(config["model_path"]).parent / "optimal_threshold.txt"
    if threshold_file.exists() and threshold is None:
        with open(threshold_file) as f:
            config["threshold"] = float(f.read().strip())
        print(f"Using optimized threshold: {config['threshold']}")
    
    # Initialize scanner
    scanner = GenomeScanner(config)
    
    # Scan FASTA
    scored_windows = scanner.scan_fasta(input_fasta)
    
    # Filter by threshold
    high_score_windows = scanner.filter_by_threshold(scored_windows)
    print(f"\nWindows above threshold ({config['threshold']}): {len(high_score_windows)}")
    
    # Merge into regions
    candidate_regions = scanner.merge_overlapping_regions(high_score_windows)
    
    # Print summary
    print_summary(candidate_regions, scored_windows)
    
    # Save results
    if output_format == "tsv":
        save_results_tsv(candidate_regions, output_path)
    else:
        save_results_json(candidate_regions, output_path)
    
    return candidate_regions


# ====================================================
# CLI
# ====================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Phase-1 BGC Genome Scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scan_genome.py --input contigs.fasta --output results.tsv
  python scan_genome.py --input genome.fna --output results.json --format json
  python scan_genome.py --input data.fasta --threshold 0.7 --stride 100
        """
    )
    
    parser.add_argument("--input", "-i", required=True,
                        help="Input FASTA file (assembled contigs)")
    parser.add_argument("--output", "-o", required=True,
                        help="Output file path")
    parser.add_argument("--model", "-m", default="./phase1_output/phase1_cnn.pt",
                        help="Path to trained Phase-1 model")
    parser.add_argument("--threshold", "-t", type=float, default=None,
                        help="Score threshold (default: use optimized or 0.5)")
    parser.add_argument("--stride", "-s", type=int, default=250,
                        help="Scanning stride in bp (default: 250)")
    parser.add_argument("--format", "-f", choices=["tsv", "json"], default="tsv",
                        help="Output format (default: tsv)")
    
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    scan_genome(
        input_fasta=args.input,
        output_path=args.output,
        model_path=args.model,
        threshold=args.threshold,
        stride=args.stride,
        output_format=args.format
    )
