"""
Stage-2 Gene Miner: BGC Rule Engine
====================================
Apply biological logic to filter real BGCs from false positives.

This is where biology beats statistics.
"""

import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple
import pandas as pd

# BGC classification rules
BGC_RULES = {
    'PKS': {
        'required': ['PKS', 'ACP'],
        'highly_recommended': ['AT', 'KR'],
        'optional': ['DH', 'ER', 'TE', 'MT'],
        'max_gene_distance': 20000,  # bp
        'min_domains': 2,
        'description': 'Polyketide synthase cluster'
    },
    
    'NRPS': {
        'required': ['A', 'PCP'],
        'highly_recommended': ['C'],
        'optional': ['E', 'TE', 'MT'],
        'max_gene_distance': 20000,
        'min_domains': 2,
        'description': 'Non-ribosomal peptide synthetase cluster'
    },
    
    'PKS-NRPS': {
        'required': ['PKS', 'A'],
        'highly_recommended': ['ACP', 'PCP'],
        'optional': ['AT', 'C', 'KR', 'TE'],
        'max_gene_distance': 25000,
        'min_domains': 3,
        'description': 'Hybrid PKS-NRPS cluster'
    },
    
    'RiPP': {
        'required': [],  # RiPPs are diverse
        'highly_recommended': ['Lasso', 'Lanthi', 'Thiopep'],
        'optional': ['P450', 'MT', 'HAL'],
        'max_gene_distance': 15000,
        'min_domains': 1,
        'description': 'Ribosomally synthesized post-translationally modified peptide'
    },
    
    'Terpene': {
        'required': [],
        'highly_recommended': ['Terpene_synth', 'Terpene_cyclase'],
        'optional': ['P450', 'MT'],
        'max_gene_distance': 15000,
        'min_domains': 1,
        'description': 'Terpene biosynthetic cluster'
    },
    
    'Other': {
        'required': [],
        'highly_recommended': ['P450', 'MT', 'GT'],
        'optional': ['ABC', 'MFS', 'FAD', 'NAD'],
        'max_gene_distance': 20000,
        'min_domains': 2,
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
            score = self._score_bgc_type(bgc_domain_types, gene_span, rules)
            classification_results[bgc_type] = score
        
        # Determine best classification
        best_type = max(classification_results, key=classification_results.get)
        best_score = classification_results[best_type]
        
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
            'type_scores': classification_results,
            'description': BGC_RULES[best_type]['description']
        }
    
    def _score_bgc_type(self, domain_types: Set[str], gene_span: int, rules: Dict) -> float:
        """
        Score how well a region matches a BGC type.
        
        Returns score between 0 and 1.
        """
        
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
    
    def filter_candidates(self, min_score: float = 0.4, min_domains: int = 2) -> pd.DataFrame:
        """Filter for high-confidence BGC candidates."""
        
        all_results = self.classify_all_regions()
        
        # Apply filters
        candidates = all_results[
            (all_results['confidence_score'] >= min_score) &
            (all_results['bgc_domains'] >= min_domains)
        ].copy()
        
        print(f"  Applied filters: score ≥ {min_score}, domains ≥ {min_domains}")
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
    parser.add_argument("--all-results", "-a", action="store_true",
                       help="Save all results, not just candidates")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Stage-2: BGC Rule Engine")
    print("=" * 60)
    
    try:
        # Load domain table
        print(f"Loading domain table: {args.domain_table}")
        domain_table = pd.read_csv(args.domain_table)
        print(f"  Loaded {len(domain_table)} domain annotations")
        
        # Initialize rule engine
        rule_engine = BGCRuleEngine(domain_table)
        
        # Classify regions
        if args.all_results:
            results = rule_engine.classify_all_regions()
            print(f"  Saving all {len(results)} classifications")
        else:
            results = rule_engine.filter_candidates(args.min_score, args.min_domains)
        
        # Save results
        results.to_csv(args.output, index=False)
        print(f"\n✅ BGC classification complete!")
        print(f"   Output: {args.output}")
        
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
        else:
            print(f"\n⚠️  No BGC candidates found!")
            print(f"   Try lowering --min-score or --min-domains")
        
    except Exception as e:
        print(f"\n❌ BGC classification failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()