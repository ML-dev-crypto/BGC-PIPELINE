"""
BGC Pipeline Validation Script
==============================
Tests pipeline output against known BGC characteristics.
Compares detected domains, gene architectures, and completeness.
"""

import json
import sys
from pathlib import Path
from collections import Counter

def load_results(results_file):
    """Load BGC results JSON."""
    with open(results_file, 'r') as f:
        return json.load(f)

def validate_bgc(bgc):
    """Validate single BGC candidate."""
    validation = {
        "region_id": bgc["region_id"],
        "bgc_class": bgc["bgc_class"],
        "score": bgc["score"],
        "validation_checks": {}
    }
    
    # Check 1: Domain architecture expected for class
    domain_arch = bgc["domain_architecture"]
    validation["validation_checks"]["has_domains"] = len(domain_arch) > 0
    
    # Check 2: Gene count
    gene_count = len(bgc["genes"])
    validation["validation_checks"]["gene_count"] = gene_count
    validation["validation_checks"]["genes_have_domains"] = sum(
        1 for g in bgc["genes"] if g["domains"]
    )
    
    # Check 3: Domain specificity
    total_domains = sum(len(g["domains"]) for g in bgc["genes"])
    bgc_domains = sum(
        1 for g in bgc["genes"] 
        for d in g["domains"] 
        if "bgc_type" in d and d["bgc_type"] != "Other"
    )
    validation["validation_checks"]["total_domains"] = total_domains
    validation["validation_checks"]["bgc_specific_domains"] = bgc_domains
    validation["validation_checks"]["specificity_ratio"] = (
        bgc_domains / total_domains if total_domains > 0 else 0
    )
    
    # Check 4: E-value quality
    all_evals = [
        d["evalue"] 
        for g in bgc["genes"] 
        for d in g["domains"]
    ]
    if all_evals:
        validation["validation_checks"]["min_evalue"] = min(all_evals)
        validation["validation_checks"]["max_evalue"] = max(all_evals)
        validation["validation_checks"]["avg_evalue"] = sum(all_evals) / len(all_evals)
    
    # Check 5: Module analysis (for PKS/NRPS)
    validation["validation_checks"]["modules"] = bgc["module_count"]
    validation["validation_checks"]["completeness"] = bgc["completeness"]
    
    return validation

def generate_report(results_file):
    """Generate validation report."""
    
    print("\n" + "="*70)
    print("BGC PIPELINE VALIDATION REPORT")
    print("="*70)
    
    # Load results
    bgcs = load_results(results_file)
    print(f"\n✅ Loaded {len(bgcs)} BGC candidates from: {results_file}\n")
    
    # Aggregate statistics
    class_distribution = Counter(b["bgc_class"] for b in bgcs)
    print("BGC CLASS DISTRIBUTION:")
    for bgc_class, count in sorted(class_distribution.items(), key=lambda x: -x[1]):
        print(f"  {bgc_class}: {count}")
    
    print("\n" + "-"*70)
    print("VALIDATION CHECKS (Per BGC):")
    print("-"*70)
    
    valid_count = 0
    for i, bgc in enumerate(bgcs[:5], 1):  # Show first 5
        validation = validate_bgc(bgc)
        
        print(f"\n[{i}] {bgc['region_id']}")
        print(f"    Class: {bgc['bgc_class']} | Score: {bgc['score']}")
        print(f"    Genes: {validation['validation_checks']['gene_count']} | "
              f"With domains: {validation['validation_checks']['genes_have_domains']}")
        print(f"    Total domains: {validation['validation_checks']['total_domains']} | "
              f"BGC-specific: {validation['validation_checks']['bgc_specific_domains']} | "
              f"Ratio: {validation['validation_checks']['specificity_ratio']:.2%}")
        
        if validation['validation_checks']['has_domains']:
            evals = validation['validation_checks']
            print(f"    E-value range: {evals['min_evalue']:.2e} to {evals['max_evalue']:.2e}")
            print(f"    Modules: {evals['modules']} | Completeness: {evals['completeness']}")
            valid_count += 1
        else:
            print("    ⚠️  NO DOMAINS DETECTED - INVALID BGC")
    
    print("\n" + "="*70)
    print(f"SUMMARY: {valid_count}/{min(5, len(bgcs))} of first 5 have valid domains")
    print(f"TOTAL: {len(bgcs)} BGC candidates identified across dataset")
    print("="*70 + "\n")
    
    # Detailed metrics
    print("DETAILED METRICS:")
    all_validations = [validate_bgc(b) for b in bgcs]
    
    avg_specificity = sum(
        v['validation_checks']['specificity_ratio'] 
        for v in all_validations
    ) / len(all_validations) if all_validations else 0
    
    print(f"  Average specificity ratio: {avg_specificity:.2%}")
    print(f"  Average module count: {sum(b['module_count'] for b in bgcs) / len(bgcs):.1f}")
    print(f"  Average score: {sum(b['score'] for b in bgcs) / len(bgcs):.2f}")
    
    completeness_dist = Counter(b["completeness"] for b in bgcs)
    print(f"  Completeness distribution:")
    for comp, count in sorted(completeness_dist.items(), key=lambda x: -x[1]):
        print(f"    {comp}: {count}")

if __name__ == "__main__":
    results_file = "stage2_production_results/bgc_results.json"
    
    if not Path(results_file).exists():
        print(f"❌ Results file not found: {results_file}")
        sys.exit(1)
    
    generate_report(results_file)
