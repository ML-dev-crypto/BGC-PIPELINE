"""
Stage-2 Gene Miner: BGC Rule Engine
====================================
Apply biological logic to filter real BGCs from false positives.

This is where biology beats statistics.
"""

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple
from collections import Counter
import pandas as pd

# RiPP precursor-modifying enzyme pairs (AND logic required)
RIPP_REQUIRED_PAIRS = {
    'lanthipeptide': {
        'precursor': ['LANT_', 'LanA'],
        'modifying': ['LanB', 'LanC', 'LanM']
    },
    'thiopeptide': {
        'precursor': ['TFUA', 'TfuA'],
        'modifying': ['TfuA', 'TPMT']
    },
}

# BGC classification rules
BGC_RULES = {
    'PKS': {
        'required': ['PKS', 'ACP'],
        'highly_recommended': ['AT', 'KR'],
        'optional': ['DH', 'ER', 'TE', 'MT'],
        'max_gene_distance': 20000,  # bp
        'min_domains': 2,
        'expected_domains': ['PKS', 'KS', 'AT', 'ACP'],  # For completeness scoring
        'description': 'Polyketide synthase cluster'
    },
    
    'NRPS': {
        'required': ['A', 'PCP'],
        'highly_recommended': ['C'],
        'optional': ['E', 'TE', 'MT'],
        'max_gene_distance': 20000,
        'min_domains': 2,
        'expected_domains': ['A', 'C', 'PCP'],  # For completeness scoring
        'description': 'Non-ribosomal peptide synthetase cluster'
    },
    
    'PKS-NRPS': {
        'required': ['PKS', 'A'],
        'highly_recommended': ['ACP', 'PCP'],
        'optional': ['AT', 'C', 'KR', 'TE'],
        'max_gene_distance': 25000,
        'min_domains': 3,
        'expected_domains': ['PKS', 'A', 'ACP', 'PCP', 'C'],  # For completeness scoring
        'description': 'Hybrid PKS-NRPS cluster'
    },
    
    'RiPP': {
        'required': [],  # RiPPs are diverse
        'highly_recommended': ['Lasso', 'Lanthi', 'Thiopep'],
        'optional': ['P450', 'MT', 'HAL'],
        'max_gene_distance': 15000,
        'min_domains': 1,
        'expected_domains': ['Lasso', 'Lanthi', 'Thiopep'],  # For completeness scoring
        'description': 'Ribosomally synthesized post-translationally modified peptide'
    },
    
    'Terpene': {
        'required': [],
        'highly_recommended': ['Terpene_synth', 'Terpene_cyclase'],
        'optional': ['P450', 'MT'],
        'max_gene_distance': 15000,
        'min_domains': 1,
        'expected_domains': ['Terpene_synth', 'Terpene_cyclase'],  # For completeness scoring
        'description': 'Terpene biosynthetic cluster'
    },
    
    'Other': {
        'required': [],
        'highly_recommended': ['P450', 'MT', 'GT'],
        'optional': ['ABC', 'MFS', 'FAD', 'NAD'],
        'max_gene_distance': 20000,
        'min_domains': 2,
        'expected_domains': ['P450', 'MT', 'GT'],  # For completeness scoring
        'description': 'Other secondary metabolite cluster'
    }
}

class BGCRuleEngine:
    """Apply biological rules to classify BGC candidates."""
    
    def __init__(self, domain_table: pd.DataFrame):
        self.domain_table = domain_table
        self.regions = self._group_by_region()
        
    def _group_by_region(self) -> Dict[str, pd.DataFrame]:
        """Group domains by region."""
        regions = {}
        for region_id in self.domain_table['region_id'].unique():
            if pd.notna(region_id):
                region_data = self.domain_table[
                    self.domain_table['region_id'] == region_id
                ].copy()
                regions[region_id] = region_data
        return regions
    
    def _calculate_completeness_score(self, domain_types: Set[str], rules: Dict) -> Tuple[float, str]:
        """
        Calculate completeness score based on expected domains.
        
        Returns:
            (completeness_score, completeness_tag)
            
        Completeness score: 0.0-1.0
        - 1.0 = all expected domains present
        - 0.5-0.8 = partial
        - <0.5 = fragment
        
        Tags: full (>0.8), partial (0.5-0.8), fragment (<0.5)
        """
        expected = set(rules.get('expected_domains', []))
        
        if not expected:
            # No expected domains defined, use required + highly_recommended
            expected = set(rules.get('required', [])) | set(rules.get('highly_recommended', []))
        
        if not expected:
            # Still no expected domains, return neutral score
            return 0.5, 'unknown'
        
        # Count how many expected domains are present
        found = len(expected & domain_types)
        total_expected = len(expected)
        
        completeness = found / total_expected if total_expected > 0 else 0.0
        
        # Determine tag
        if completeness > 0.8:
            tag = 'full'
        elif completeness >= 0.5:
            tag = 'partial'
        else:
            tag = 'fragment'
        
        return completeness, tag
    
    def analyze_region(self, region_id: str, region_data: pd.DataFrame) -> Dict:
        """
        Analyze a single region for BGC characteristics.
        
        Returns:
            dict with classification results
        """
        
        # Basic statistics
        genes = region_data['gene_id'].nunique()
        domains = len(region_data)
        domain_types = set(region_data['domain_type'].values)
        
        # Remove 'OTHER' domains for classification
        bgc_domain_types = domain_types - {'OTHER'}
        
        # Calculate gene span
        gene_positions = region_data.groupby('gene_id')['start'].first().values
        gene_span = max(gene_positions) - min(gene_positions) if len(gene_positions) > 1 else 0
        
        # Test each BGC type
        classification_results = {}
        
        for bgc_type, rules in BGC_RULES.items():
            score = self._score_bgc_type(bgc_domain_types, gene_span, rules, bgc_type=bgc_type)
            classification_results[bgc_type] = score
        
        # Determine best classification
        best_type = max(classification_results, key=classification_results.get)
        best_score = classification_results[best_type]
        
        # Calculate completeness score for best type
        completeness_score, completeness_tag = self._calculate_completeness_score(
            bgc_domain_types, 
            BGC_RULES[best_type]
        )

        has_start_codon = bool(region_data['has_start_codon'].fillna(False).all()) if 'has_start_codon' in region_data else False
        has_stop_codon = bool(region_data['has_stop_codon'].fillna(False).all()) if 'has_stop_codon' in region_data else False
        n_content_pct = float(region_data['n_content_pct'].fillna(0.0).max()) if 'n_content_pct' in region_data else 0.0
        
        # Truncated ORF rule: if start or stop codon is missing, mark as partial
        # This takes priority over domain-based completeness scoring
        if not has_start_codon or not has_stop_codon:
            completeness_tag = 'partial'
            completeness_score = 0.5  # Set to mid-range for partial
        
        # Confidence levels
        if best_score >= 0.8:
            confidence = 'high'
        elif best_score >= 0.6:
            confidence = 'medium'
        elif best_score >= 0.4:
            confidence = 'low'
        else:
            confidence = 'very_low'
        
        return {
            'region_id': region_id,
            'genes': genes,
            'domains': domains,
            'bgc_domains': len(bgc_domain_types),
            'domain_types': list(bgc_domain_types),
            'gene_span_bp': gene_span,
            'predicted_type': best_type,
            'confidence_score': best_score,
            'confidence_level': confidence,
            'completeness_score': round(completeness_score, 3),
            'completeness_tag': completeness_tag,
            'completeness': completeness_tag,
            'has_start_codon': has_start_codon,
            'has_stop_codon': has_stop_codon,
            'n_content_pct': round(n_content_pct, 2),
            'type_scores': classification_results,
            'description': BGC_RULES[best_type]['description']
        }
    
    def _score_bgc_type(self, domain_types: Set[str], gene_span: int, rules: Dict, bgc_type: str = None) -> float:
        """
        Score how well a region matches a BGC type.
        
        Returns score between 0 and 1.
        """
        
        # Special RiPP AND logic: require both precursor AND modifying enzyme
        if bgc_type == 'RiPP':
            # Check if any valid lanthipeptide or thiopeptide pair exists
            has_valid_ripp_pair = False
            for ripp_class, pair_rules in RIPP_REQUIRED_PAIRS.items():
                precursor_match = any(p in domain for p in pair_rules['precursor'] for domain in domain_types)
                modifying_match = any(m in domain for m in pair_rules['modifying'] for domain in domain_types)
                if precursor_match and modifying_match:
                    has_valid_ripp_pair = True
                    break
            
            # If no valid pair found, check if there are any RiPP-related domains present
            if not has_valid_ripp_pair:
                # Collect all RiPP-related keywords to check
                ripp_keywords = set()
                for ripp_class, pair_rules in RIPP_REQUIRED_PAIRS.items():
                    ripp_keywords.update(pair_rules['precursor'])
                    ripp_keywords.update(pair_rules['modifying'])
                
                # Check if domain_types contains any RiPP keywords
                has_ripp_keywords = any(
                    any(keyword in domain for keyword in ripp_keywords) 
                    for domain in domain_types
                )
                
                if has_ripp_keywords:
                    # Has RiPP domains but missing required AND pairing - heavily penalize
                    return 0.0
        
        score = 0.0
        max_score = 0.0
        
        # Required domains (essential)
        required = set(rules['required'])
        if required:
            max_score += 0.5
            if required.issubset(domain_types):
                score += 0.5
            else:
                # Partial penalty
                overlap = len(required & domain_types)
                score += 0.5 * (overlap / len(required))
        
        # Highly recommended domains
        recommended = set(rules['highly_recommended'])
        if recommended:
            max_score += 0.3
            overlap = len(recommended & domain_types)
            score += 0.3 * (overlap / len(recommended))
        
        # Optional domains (bonus)
        optional = set(rules['optional'])
        if optional:
            max_score += 0.1
            overlap = len(optional & domain_types)
            score += 0.1 * min(1.0, overlap / max(1, len(optional)))
        
        # Gene distance penalty
        max_distance = rules['max_gene_distance']
        max_score += 0.1
        if gene_span <= max_distance:
            score += 0.1
        elif gene_span <= max_distance * 2:
            score += 0.05  # Partial penalty
        
        # Normalize score
        if max_score > 0:
            score = score / max_score
        
        return min(1.0, score)
    
    def classify_all_regions(self) -> pd.DataFrame:
        """Classify all regions."""
        
        print(f"Classifying {len(self.regions)} regions...")
        
        results = []
        
        for region_id, region_data in self.regions.items():
            result = self.analyze_region(region_id, region_data)
            results.append(result)
        
        df = pd.DataFrame(results)
        
        # Sort by confidence score
        df = df.sort_values('confidence_score', ascending=False)
        
        return df
    
    def filter_candidates(self, min_score: float = 0.4, min_domains: int = 2, 
                         min_completeness: float = 0.5) -> pd.DataFrame:
        """Filter for high-confidence BGC candidates."""
        
        all_results = self.classify_all_regions()
        
        if all_results.empty or 'confidence_score' not in all_results.columns:
            print(f"  Applied filters: score ≥ {min_score}, domains ≥ {min_domains}, completeness ≥ {min_completeness}")
            print(f"  BGC candidates: 0 / 0")
            return pd.DataFrame()

        # Apply filters
        candidates = all_results[
            (all_results['confidence_score'] >= min_score) &
            (all_results['bgc_domains'] >= min_domains) &
            (all_results['completeness_score'] >= min_completeness)
        ].copy()
        
        print(f"  Applied filters: score ≥ {min_score}, domains ≥ {min_domains}, completeness ≥ {min_completeness}")
        print(f"  BGC candidates: {len(candidates)} / {len(all_results)}")
        
        return candidates

def main():
    parser = argparse.ArgumentParser(description="Apply BGC classification rules")
    parser.add_argument("--domain-table", "-d", required=True,
                       help="Domain table CSV from parse_domains.py")
    parser.add_argument("--output", "-o", required=True,
                       help="Output CSV for BGC candidates")
    parser.add_argument("--min-score", "-s", type=float, default=0.4,
                       help="Minimum confidence score (default: 0.4)")
    parser.add_argument("--min-domains", "-m", type=int, default=2,
                       help="Minimum BGC domains required (default: 2)")
    parser.add_argument("--min-completeness", "-c", type=float, default=0.5,
                       help="Minimum completeness score (default: 0.5)")
    parser.add_argument("--all-results", "-a", action="store_true",
                       help="Save all results, not just candidates")
    parser.add_argument("--log", "-l", default=None,
                       help="Output log file (JSON format)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Stage-2: BGC Rule Engine")
    print("=" * 60)
    
    start_time = datetime.now()
    
    try:
        # Load domain table
        print(f"Loading domain table: {args.domain_table}")
        domain_table = pd.read_csv(args.domain_table)
        print(f"  Loaded {len(domain_table)} domain annotations")
        
        # Calculate input hash
        input_hash = hashlib.md5(domain_table.to_json().encode()).hexdigest()[:16]
        print(f"  Input hash: {input_hash}")
        
        # Count contigs
        num_contigs = domain_table['region_id'].nunique() if 'region_id' in domain_table.columns else 0
        
        # Initialize rule engine
        rule_engine = BGCRuleEngine(domain_table)
        
        # Classify regions
        if args.all_results:
            results = rule_engine.classify_all_regions()
            print(f"  Saving all {len(results)} classifications")
        else:
            results = rule_engine.filter_candidates(
                args.min_score, 
                args.min_domains,
                args.min_completeness
            )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # BGCs detected per contig
        bgcs_per_contig = {}
        if len(results) > 0:
            for _, row in results.iterrows():
                region_id = row['region_id']
                # Extract contig ID from region_id (assuming format like contig_1_region_1)
                contig_id = '_'.join(str(region_id).split('_')[:-2]) if '_' in str(region_id) else str(region_id)
                bgcs_per_contig[contig_id] = bgcs_per_contig.get(contig_id, 0) + 1
        
        # Save results
        results.to_csv(args.output, index=False)
        print(f"\n[OK] BGC classification complete!")
        print(f"   Output: {args.output}")
        print(f"   Duration: {duration:.2f}s")
        
        # Structured logging
        log_data = {
            'timestamp': start_time.isoformat(),
            'script': 'classify_bgcs.py',
            'input_file': args.domain_table,
            'input_hash': input_hash,
            'num_contigs': num_contigs,
            'total_bgcs_detected': len(results),
            'bgcs_per_contig': bgcs_per_contig,
            'bgc_classes': results['predicted_type'].value_counts().to_dict() if len(results) > 0 else {},
            'completeness_distribution': results['completeness_tag'].value_counts().to_dict() if len(results) > 0 else {},
            'duration_seconds': round(duration, 2),
            'status': 'success',
            'filters': {
                'min_score': args.min_score,
                'min_domains': args.min_domains,
                'min_completeness': args.min_completeness
            }
        }
        
        # Write log file
        if args.log:
            log_path = Path(args.log)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, 'w') as f:
                json.dump(log_data, f, indent=2)
            print(f"  📝 Wrote log to {args.log}")
        
        # Summary
        if len(results) > 0:
            print(f"\nSummary:")
            print(f"  Total candidates: {len(results)}")
            type_counts = results['predicted_type'].value_counts()
            for bgc_type, count in type_counts.items():
                print(f"    {bgc_type}: {count}")
            
            confidence_counts = results['confidence_level'].value_counts()
            print(f"\n  Confidence levels:")
            for level, count in confidence_counts.items():
                print(f"    {level}: {count}")
            
            completeness_counts = results['completeness_tag'].value_counts()
            print(f"\n  Completeness:")
            for tag, count in completeness_counts.items():
                print(f"    {tag}: {count}")
        else:
            print(f"\n[WARN]  No BGC candidates found!")
            print(f"   Try lowering --min-score or --min-domains")
        
    except Exception as e:
        print(f"\n[ERROR] BGC classification failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
