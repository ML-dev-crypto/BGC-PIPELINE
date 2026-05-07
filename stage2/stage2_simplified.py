"""
Stage-2 Simplified Pipeline - Windows Native
Fallback implementation for when WSL tools aren't available.
"""

import os
import re
import json
import pandas as pd
from pathlib import Path
from collections import defaultdict, Counter
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqUtils.ProtParam import ProteinAnalysis

class SimplifiedStage2Pipeline:
    """Simplified Stage-2 that works without external tools."""
    
    def __init__(self, input_fasta, output_dir):
        self.input_fasta = Path(input_fasta)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Simple domain signatures (basic patterns)
        self.domain_patterns = {
            'PKS_KS': r'[FY].{10,30}[GAS][TABS].[TABS].[LIVM].{20,50}[DN].[FY]',
            'NRPS_A': r'[LIV][KR].{10,30}[TABS][GAS][TABS][LIVM].{20,50}[DE].[FY]',
            'Terpene_synth': r'DD[XN][XN]D',
            'P450': r'[FW][XN]{4,8}[GAS][XN][RK][XN][CYS][XN][GAS]',
            'MethylTransf': r'[LIVM][DE][LIVM][GAS][GAS][XN][GAS][TABS]',
        }
        
    def simple_gene_prediction(self, sequence):
        """Basic ORF finding (not as good as Prodigal)."""
        genes = []
        
        # Find ORFs in all 6 frames
        for frame in range(3):
            for strand in [1, -1]:
                if strand == -1:
                    seq = str(Seq(sequence).reverse_complement())
                else:
                    seq = sequence
                
                # Start from frame
                for start_pos in range(frame, len(seq) - 3, 3):
                    codon = seq[start_pos:start_pos+3]
                    
                    if codon.upper() in ['ATG', 'GTG', 'TTG']:  # Start codons
                        # Find stop codon
                        for end_pos in range(start_pos + 3, len(seq) - 3, 3):
                            stop_codon = seq[end_pos:end_pos+3]
                            if stop_codon.upper() in ['TAA', 'TAG', 'TGA']:
                                orf_len = end_pos - start_pos
                                if orf_len >= 300:  # Minimum gene length
                                    
                                    if strand == 1:
                                        actual_start = start_pos
                                        actual_end = end_pos + 3
                                    else:
                                        actual_start = len(sequence) - end_pos - 3
                                        actual_end = len(sequence) - start_pos
                                    
                                    genes.append({
                                        'id': f"gene_{len(genes)+1}",
                                        'start': actual_start,
                                        'end': actual_end,
                                        'strand': '+' if strand == 1 else '-',
                                        'length': orf_len,
                                        'sequence': seq[start_pos:end_pos+3]
                                    })
                                break
                        else:
                            continue
                        break
        
        return genes
    
    def simple_domain_search(self, protein_seq):
        """Basic pattern matching for domains."""
        domains = []
        
        for domain_name, pattern in self.domain_patterns.items():
            # Convert pattern to more flexible regex
            flexible_pattern = pattern.replace('X', '[A-Z]').replace('N', '[A-Z]')
            
            for match in re.finditer(flexible_pattern, protein_seq):
                domains.append({
                    'domain': domain_name,
                    'start': match.start(),
                    'end': match.end(),
                    'sequence': match.group(),
                    'score': len(match.group()),  # Simple scoring
                    'evalue': 1e-3  # Placeholder
                })
        
        return domains
    
    def analyze_protein(self, protein_seq):
        """Analyze protein properties."""
        try:
            analysis = ProteinAnalysis(protein_seq)
            return {
                'length': len(protein_seq),
                'molecular_weight': analysis.molecular_weight(),
                'gravy': analysis.gravy(),  # Hydrophobicity
                'instability_index': analysis.instability_index(),
            }
        except:
            return {
                'length': len(protein_seq),
                'molecular_weight': 0,
                'gravy': 0,
                'instability_index': 0,
            }
    
    def process_region(self, region_id, sequence):
        """Process a single BGC candidate region."""
        
        print(f"  🧬 Processing {region_id} ({len(sequence):,} bp)")
        
        # Step 1: Gene prediction
        genes = self.simple_gene_prediction(sequence)
        print(f"    Found {len(genes)} potential genes")
        
        if not genes:
            return None
        
        # Step 2: Domain annotation
        annotated_genes = []
        total_domains = 0
        
        for gene in genes:
            # Translate to protein
            dna_seq = Seq(gene['sequence'])
            try:
                protein_seq = str(dna_seq.translate()).rstrip('*')
            except:
                continue
            
            # Find domains
            domains = self.simple_domain_search(protein_seq)
            
            # Analyze protein
            protein_props = self.analyze_protein(protein_seq)
            
            gene_result = {
                'gene_id': gene['id'],
                'start': gene['start'],
                'end': gene['end'],
                'strand': gene['strand'],
                'length': gene['length'],
                'protein_sequence': protein_seq,
                'protein_properties': protein_props,
                'domains': domains
            }
            
            annotated_genes.append(gene_result)
            total_domains += len(domains)
        
        print(f"    Found {total_domains} domain hits")
        
        if total_domains == 0:
            return None
        
        # Step 3: BGC scoring
        domain_types = [d['domain'] for gene in annotated_genes for d in gene['domains']]
        domain_counts = Counter(domain_types)
        
        # Simple BGC scoring
        bgc_score = 0
        if 'PKS_KS' in domain_counts:
            bgc_score += domain_counts['PKS_KS'] * 3
        if 'NRPS_A' in domain_counts:
            bgc_score += domain_counts['NRPS_A'] * 3
        if 'Terpene_synth' in domain_counts:
            bgc_score += domain_counts['Terpene_synth'] * 2
        bgc_score += len([d for d in domain_types if d in ['P450', 'MethylTransf']])
        
        region_result = {
            'region_id': region_id,
            'sequence_length': len(sequence),
            'total_genes': len(annotated_genes),
            'total_domains': total_domains,
            'domain_counts': dict(domain_counts),
            'bgc_score': bgc_score,
            'genes': annotated_genes
        }
        
        return region_result
    
    def run_pipeline(self):
        """Run the complete simplified Stage-2 pipeline."""
        
        print("🔬 Starting Simplified Stage-2 Pipeline...")
        print(f"📁 Input: {self.input_fasta}")
        print(f"📂 Output: {self.output_dir}")
        
        if not self.input_fasta.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_fasta}")
        
        # Load sequences
        print("📖 Loading candidate regions...")
        sequences = {}
        for record in SeqIO.parse(self.input_fasta, 'fasta'):
            sequences[record.id] = str(record.seq)
        
        print(f"   Loaded {len(sequences)} regions")
        
        # Process each region
        results = []
        bgc_candidates = []
        
        for region_id, sequence in sequences.items():
            result = self.process_region(region_id, sequence)
            if result:
                results.append(result)
                if result['bgc_score'] >= 3:  # Minimum score threshold
                    bgc_candidates.append(result)
        
        print(f"\n📊 Pipeline Results:")
        print(f"   Total regions processed: {len(sequences)}")
        print(f"   Regions with domains: {len(results)}")
        print(f"   BGC candidates (score ≥3): {len(bgc_candidates)}")
        
        # Save results
        self.save_results(results, bgc_candidates)
        
        return results, bgc_candidates
    
    def save_results(self, results, bgc_candidates):
        """Save pipeline results."""
        
        # Save full results as JSON
        full_results_path = self.output_dir / "full_results.json"
        with open(full_results_path, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"💾 Saved full results: {full_results_path}")
        
        # Save BGC candidates as JSON
        bgc_results_path = self.output_dir / "bgc_candidates.json"
        with open(bgc_results_path, 'w') as f:
            json.dump(bgc_candidates, f, indent=2)
        print(f"💾 Saved BGC candidates: {bgc_results_path}")
        
        # Create summary table
        summary_data = []
        for result in bgc_candidates:
            row = {
                'region_id': result['region_id'],
                'length_bp': result['sequence_length'],
                'total_genes': result['total_genes'],
                'total_domains': result['total_domains'],
                'bgc_score': result['bgc_score'],
                'PKS_domains': result['domain_counts'].get('PKS_KS', 0),
                'NRPS_domains': result['domain_counts'].get('NRPS_A', 0),
                'Terpene_domains': result['domain_counts'].get('Terpene_synth', 0),
                'Other_domains': sum(v for k, v in result['domain_counts'].items() 
                                   if k not in ['PKS_KS', 'NRPS_A', 'Terpene_synth'])
            }
            summary_data.append(row)
        
        if summary_data:
            summary_df = pd.DataFrame(summary_data)
            summary_path = self.output_dir / "bgc_candidates_summary.tsv"
            summary_df.to_csv(summary_path, sep='\t', index=False)
            print(f"📋 Saved summary table: {summary_path}")
            
            # Print top candidates
            print(f"\n🏆 Top BGC Candidates:")
            top_candidates = summary_df.nlargest(10, 'bgc_score')
            for _, row in top_candidates.iterrows():
                print(f"   {row['region_id']}: Score={row['bgc_score']}, "
                      f"Genes={row['total_genes']}, Domains={row['total_domains']}")

def main():
    """Main execution function."""
    
    # Configuration
    INPUT_FASTA = "stage2_test_results/extracted_regions.fasta"
    OUTPUT_DIR = "stage2_simplified_results"
    
    print("🧬 Simplified Stage-2 BGC Pipeline")
    print("=" * 50)
    print("⚠️  Note: This is a simplified fallback version.")
    print("   For full accuracy, use Prodigal + HMMER + Pfam.")
    print()
    
    # Run pipeline
    pipeline = SimplifiedStage2Pipeline(INPUT_FASTA, OUTPUT_DIR)
    results, bgc_candidates = pipeline.run_pipeline()
    
    print("\n✅ Simplified Stage-2 Complete!")
    print(f"   Check results in: {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()