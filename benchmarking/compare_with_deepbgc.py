#!/usr/bin/env python3
"""
compare_with_deepbgc.py — Compare BGC-QDR results with DeepBGC
================================================================

Runs DeepBGC on the same eDNA FASTA files and compares:
  1. Number of BGCs detected
  2. BGC class distribution
  3. Detection overlap (genomic coordinates)
  4. Runtime performance

Usage:
  python compare_with_deepbgc.py
  python compare_with_deepbgc.py --deepbgc-results benchmark_results/deepbgc_*/
"""

import argparse
import json
import subprocess
import time
from pathlib import Path
from collections import Counter

# Paths
EDNA_DIR = Path("edna_fasta")
BGC_QDR_RESULTS = Path("stage2_production_results/bgc_results.json")
OUTPUT_DIR = Path("benchmark_results")
OUTPUT_DIR.mkdir(exist_ok=True)

def run_deepbgc(fasta_file: Path, output_dir: Path) -> dict:
    """Run DeepBGC on a FASTA file and return results."""
    print(f"  Running DeepBGC on {fasta_file.name}...")
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            ["deepbgc", "pipeline", str(fasta_file), "-o", str(output_dir)],
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        elapsed = time.time() - start_time
        
        if result.returncode != 0:
            print(f"    ⚠ DeepBGC failed: {result.stderr}")
            return {"success": False, "error": result.stderr, "runtime_s": elapsed}
        
        # Parse DeepBGC output
        bgc_tsv = output_dir / f"{fasta_file.stem}.bgc.tsv"
        if not bgc_tsv.exists():
            return {"success": False, "error": "No BGC TSV output", "runtime_s": elapsed}
        
        bgcs = []
        with open(bgc_tsv) as f:
            header = f.readline().strip().split('\t')
            for line in f:
                if line.strip():
                    fields = line.strip().split('\t')
                    bgcs.append({
                        "sequence_id": fields[0] if len(fields) > 0 else "",
                        "start": int(fields[1]) if len(fields) > 1 else 0,
                        "end": int(fields[2]) if len(fields) > 2 else 0,
                        "score": float(fields[3]) if len(fields) > 3 else 0.0,
                        "product_class": fields[4] if len(fields) > 4 else "unknown"
                    })
        
        return {
            "success": True,
            "n_bgcs": len(bgcs),
            "bgcs": bgcs,
            "runtime_s": elapsed
        }
        
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return {"success": False, "error": "Timeout (>10 min)", "runtime_s": elapsed}
    except FileNotFoundError:
        return {"success": False, "error": "DeepBGC not installed", "runtime_s": 0}

def parse_bgcqdr_results() -> dict:
    """Parse BGC-QDR results."""
    if not BGC_QDR_RESULTS.exists():
        return {"success": False, "error": "BGC-QDR results not found"}
    
    with open(BGC_QDR_RESULTS) as f:
        bgcs = json.load(f)
    
    # Group by source genome
    by_genome = {}
    for bgc in bgcs:
        genome = bgc.get("source_genome", "unknown")
        if genome not in by_genome:
            by_genome[genome] = []
        by_genome[genome].append(bgc)
    
    return {
        "success": True,
        "n_bgcs": len(bgcs),
        "by_genome": by_genome,
        "bgcs": bgcs
    }

def calculate_overlap(bgc1: dict, bgc2: dict) -> float:
    """Calculate Jaccard overlap between two BGC regions."""
    # Assume both have start/end coordinates
    start1, end1 = bgc1.get("start", 0), bgc1.get("end", 0)
    start2, end2 = bgc2.get("start", 0), bgc2.get("end", 0)
    
    if start1 == 0 or start2 == 0:
        return 0.0
    
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    overlap_len = max(0, overlap_end - overlap_start)
    
    union_len = max(end1, end2) - min(start1, start2)
    
    return overlap_len / union_len if union_len > 0 else 0.0

def compare_results(bgcqdr: dict, deepbgc: dict) -> dict:
    """Compare BGC-QDR and DeepBGC results."""
    comparison = {
        "bgcqdr_count": bgcqdr.get("n_bgcs", 0),
        "deepbgc_count": deepbgc.get("n_bgcs", 0),
        "bgcqdr_runtime_s": "N/A (pre-computed)",
        "deepbgc_runtime_s": deepbgc.get("runtime_s", 0),
    }
    
    # Class distribution
    if bgcqdr.get("success"):
        bgcqdr_classes = Counter(b.get("bgc_class", "unknown") 
                                 for b in bgcqdr["bgcs"])
        comparison["bgcqdr_classes"] = dict(bgcqdr_classes)
    
    if deepbgc.get("success"):
        deepbgc_classes = Counter(b.get("product_class", "unknown") 
                                  for b in deepbgc["bgcs"])
        comparison["deepbgc_classes"] = dict(deepbgc_classes)
    
    # Overlap analysis (if both successful)
    if bgcqdr.get("success") and deepbgc.get("success"):
        overlaps = []
        for bgc_q in bgcqdr["bgcs"]:
            for bgc_d in deepbgc["bgcs"]:
                overlap = calculate_overlap(bgc_q, bgc_d)
                if overlap > 0.3:  # 30% overlap threshold
                    overlaps.append({
                        "bgcqdr_id": bgc_q.get("region_id", "?"),
                        "deepbgc_id": f"{bgc_d['sequence_id']}:{bgc_d['start']}-{bgc_d['end']}",
                        "overlap": round(overlap, 3)
                    })
        
        comparison["overlapping_bgcs"] = len(overlaps)
        comparison["overlap_details"] = overlaps[:10]  # Top 10
    
    return comparison

def main():
    parser = argparse.ArgumentParser(description="Compare BGC-QDR with DeepBGC")
    parser.add_argument("--deepbgc-results", type=Path, 
                       help="Path to existing DeepBGC results (skip running)")
    parser.add_argument("--skip-deepbgc", action="store_true",
                       help="Skip running DeepBGC (use existing results only)")
    args = parser.parse_args()
    
    print("=" * 72)
    print("  BGC-QDR vs DeepBGC Comparison")
    print("=" * 72)
    print()
    
    # Parse BGC-QDR results
    print("Loading BGC-QDR results...")
    bgcqdr = parse_bgcqdr_results()
    if not bgcqdr["success"]:
        print(f"  ❌ {bgcqdr['error']}")
        return
    print(f"  ✅ BGC-QDR: {bgcqdr['n_bgcs']} BGCs detected")
    print()
    
    # Run or load DeepBGC results
    if args.skip_deepbgc:
        print("Skipping DeepBGC run (--skip-deepbgc)")
        deepbgc = {"success": False, "error": "Skipped by user"}
    elif args.deepbgc_results:
        print(f"Loading DeepBGC results from {args.deepbgc_results}...")
        # Parse existing results
        deepbgc = {"success": False, "error": "Not implemented yet"}
    else:
        print("Running DeepBGC on eDNA samples...")
        print("(This may take 5-10 minutes per genome)")
        print()
        
        fasta_files = list(EDNA_DIR.glob("*.fasta"))
        if not fasta_files:
            print("  ❌ No FASTA files found in edna_fasta/")
            return
        
        all_deepbgc_results = []
        total_runtime = 0
        
        for fasta in fasta_files:
            output_subdir = OUTPUT_DIR / f"deepbgc_{fasta.stem}"
            output_subdir.mkdir(exist_ok=True)
            
            result = run_deepbgc(fasta, output_subdir)
            all_deepbgc_results.append(result)
            
            if result["success"]:
                print(f"    ✅ {result['n_bgcs']} BGCs in {result['runtime_s']:.1f}s")
                total_runtime += result["runtime_s"]
            else:
                print(f"    ❌ {result['error']}")
        
        # Aggregate DeepBGC results
        deepbgc = {
            "success": any(r["success"] for r in all_deepbgc_results),
            "n_bgcs": sum(r.get("n_bgcs", 0) for r in all_deepbgc_results),
            "runtime_s": total_runtime,
            "bgcs": [bgc for r in all_deepbgc_results 
                    if r.get("success") for bgc in r.get("bgcs", [])]
        }
        
        print()
        print(f"  ✅ DeepBGC: {deepbgc['n_bgcs']} BGCs detected in {total_runtime:.1f}s")
    
    print()
    print("=" * 72)
    print("  Comparison Results")
    print("=" * 72)
    print()
    
    comparison = compare_results(bgcqdr, deepbgc)
    
    # Print comparison table
    print(f"{'Metric':<30} {'BGC-QDR':>15} {'DeepBGC':>15}")
    print("-" * 62)
    print(f"{'Total BGCs detected':<30} {comparison['bgcqdr_count']:>15} "
          f"{comparison['deepbgc_count']:>15}")
    print(f"{'Runtime':<30} {str(comparison['bgcqdr_runtime_s']):>15} "
          f"{comparison['deepbgc_runtime_s']:>14.1f}s")
    
    if "overlapping_bgcs" in comparison:
        print(f"{'Overlapping BGCs (>30%)':<30} {comparison['overlapping_bgcs']:>15}")
    
    print()
    
    # Class distribution
    if "bgcqdr_classes" in comparison:
        print("BGC-QDR Class Distribution:")
        for cls, count in sorted(comparison["bgcqdr_classes"].items(), 
                                key=lambda x: -x[1]):
            print(f"  {cls:<35} {count:>6}")
        print()
    
    if "deepbgc_classes" in comparison:
        print("DeepBGC Class Distribution:")
        for cls, count in sorted(comparison["deepbgc_classes"].items(), 
                                key=lambda x: -x[1]):
            print(f"  {cls:<35} {count:>6}")
        print()
    
    # Save results
    output_file = OUTPUT_DIR / "deepbgc_comparison.json"
    with open(output_file, 'w') as f:
        json.dump({
            "bgcqdr": {
                "n_bgcs": bgcqdr.get("n_bgcs", 0),
                "classes": comparison.get("bgcqdr_classes", {})
            },
            "deepbgc": {
                "n_bgcs": deepbgc.get("n_bgcs", 0),
                "runtime_s": deepbgc.get("runtime_s", 0),
                "classes": comparison.get("deepbgc_classes", {})
            },
            "comparison": comparison
        }, f, indent=2)
    
    print(f"Results saved to {output_file}")
    print()
    print("=" * 72)

if __name__ == "__main__":
    main()
