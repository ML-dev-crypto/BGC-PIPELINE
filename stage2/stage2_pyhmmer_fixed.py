"""
Stage-2 Gene Miner: Windows Production Pipeline (FIXED)
========================================================
Uses Windows Prodigal binary + pyhmmer for real HMMER domain search.

FIXES APPLIED:
1. Correct pyhmmer API usage (binary file handle, not string)
2. Correct domain extraction (hit.name, hit.domains, domain.score)
3. Windows-native paths (no WSL required)
4. Real Pfam domain annotation
"""

import os
import re
import sys
import json
import gzip
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from Bio import SeqIO
from Bio.Seq import Seq

# ================= CONFIGURATION =================
INPUT_FASTA = "stage2_test_results/extracted_regions.fasta"
OUTPUT_DIR = "stage2_production_results"

# Windows paths
PRODIGAL_BIN = "D:/web.dv/tools/prodigal.exe"
PFAM_DB = "D:/web.dv/pfam_data/Pfam-A.hmm.gz"

# Analysis parameters
E_VALUE_CUTOFF = 1e-5
DOM_E_VALUE_CUTOFF = 1e-5

# BGC domain families (Pfam accessions) - for classification
BGC_DOMAIN_FAMILIES = {
    # PKS core domains
    'PKS_KS': ['PF00109', 'PF02801', 'ketoacyl-synt', 'KS'],
    'PKS_AT': ['PF00698', 'Acyl_transf', 'AT'],
    'PKS_ACP': ['PF00550', 'PP-binding', 'ACP'],
    'PKS_KR': ['PF08659', 'KR'],
    'PKS_DH': ['PF14765', 'PS-DH', 'DH'],
    'PKS_ER': ['PF08030', 'ER'],
    
    # NRPS core domains  
    'NRPS_A': ['PF00501', 'AMP-binding', 'A_domain'],
    'NRPS_C': ['PF00668', 'Condensation', 'C_domain'],
    'NRPS_PCP': ['PF00550', 'PP-binding', 'PCP'],
    'NRPS_E': ['PF00668'],
    
    # Terpene
    'Terpene_synth': ['PF03936', 'PF01397', 'Terpene_synth'],
    
    # Common tailoring
    'TE': ['PF00975', 'Thioesterase'],
    'P450': ['PF00067', 'p450'],
    'MT': ['PF13489', 'PF13649', 'Methyltransf'],
    'Glycosyltransf': ['PF00534', 'PF00535'],
}


class PyHMMERDomainSearcher:
    """Correct pyhmmer implementation for domain search."""
    
    def __init__(self, pfam_path: str):
        self.pfam_path = pfam_path
        self.hmms = None
        self.alphabet = None
        
    def load_pfam(self) -> bool:
        """Load Pfam database correctly using binary file handle."""
        try:
            import pyhmmer
            from pyhmmer.plan7 import HMMFile
            from pyhmmer.easel import Alphabet
            
            print(f"📚 Loading Pfam database from {self.pfam_path}...")
            
            self.alphabet = Alphabet.amino()
            
            # Check if compressed
            if self.pfam_path.endswith('.gz'):
                print("   Decompressing and loading (this may take a minute)...")
                with gzip.open(self.pfam_path, 'rb') as gz_file:
                    # Write to temp file for HMMFile
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.hmm') as tmp:
                        tmp.write(gz_file.read())
                        tmp_path = tmp.name
                
                # Load from temp file with binary handle (CORRECT WAY)
                with open(tmp_path, 'rb') as f:
                    self.hmms = list(HMMFile(f))
                
                # Cleanup
                os.unlink(tmp_path)
            else:
                # Load directly with binary file handle (CORRECT WAY)
                with open(self.pfam_path, 'rb') as f:
                    self.hmms = list(HMMFile(f))
            
            print(f"   ✅ Loaded {len(self.hmms)} Pfam HMM profiles")
            return True
            
        except Exception as e:
            print(f"   ❌ Failed to load Pfam: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def search_proteins(self, proteins_fasta: str) -> List[Dict]:
        """Search proteins against Pfam using pyhmmer correctly."""
        try:
            import pyhmmer
            from pyhmmer.easel import TextSequence
            from pyhmmer.plan7 import Pipeline
            
            if self.hmms is None:
                print("   ❌ Pfam not loaded")
                return []
            
            # Load protein sequences correctly
            print("   Loading protein sequences...")
            sequences = []
            seq_names = []
            
            for record in SeqIO.parse(proteins_fasta, 'fasta'):
                # Create digital sequence for pyhmmer
                seq_bytes = bytes(str(record.seq), 'utf-8')
                name_bytes = bytes(record.id, 'utf-8')
                
                try:
                    digital_seq = TextSequence(
                        name=name_bytes,
                        sequence=seq_bytes
                    ).digitize(self.alphabet)
                    sequences.append(digital_seq)
                    seq_names.append(record.id)
                except Exception as e:
                    # Skip sequences with invalid amino acids
                    continue
            
            if not sequences:
                print("   ⚠️ No valid protein sequences to search")
                return []
            
            print(f"   Searching {len(sequences)} proteins against {len(self.hmms)} Pfam profiles...")
            print("   (This may take several minutes for large datasets)")
            
            # Run hmmscan-style search (proteins vs HMM database)
            domains_found = []
            
            pipeline = Pipeline(self.alphabet, E=E_VALUE_CUTOFF, domE=DOM_E_VALUE_CUTOFF)
            
            for i, seq in enumerate(sequences):
                if i > 0 and i % 100 == 0:
                    print(f"   Processed {i}/{len(sequences)} proteins...")
                
                # Search this protein against all HMMs
                for hmm in self.hmms:
                    try:
                        hits = pipeline.search_hmm(hmm, [seq])
                        
                        for hit in hits:
                            if hit.evalue <= E_VALUE_CUTOFF:
                                # Extract HMM name (Pfam family)
                                pfam_name = hmm.name.decode() if hasattr(hmm.name, 'decode') else str(hmm.name)
                                pfam_acc = hmm.accession.decode() if hmm.accession and hasattr(hmm.accession, 'decode') else ""
                                
                                # Extract domains from hit (CORRECT WAY)
                                for dom in hit.domains:
                                    if dom.score > 0:  # Only positive scores
                                        domains_found.append({
                                            'protein_id': seq_names[i],
                                            'pfam_name': pfam_name,
                                            'pfam_accession': pfam_acc,
                                            'score': float(dom.score),
                                            'evalue': float(hit.evalue),
                                            'env_from': int(dom.env_from),
                                            'env_to': int(dom.env_to),
                                        })
                    except Exception as e:
                        continue
                
                # Clear pipeline for next sequence
                pipeline.clear()
            
            print(f"   ✅ Found {len(domains_found)} domain hits")
            return domains_found
            
        except Exception as e:
            print(f"   ❌ Domain search failed: {e}")
            import traceback
            traceback.print_exc()
            return []


class Stage2ProductionPipeline:
    """Complete Stage-2 pipeline with correct tool usage."""
    
    def __init__(self, input_fasta: str, output_dir: str):
        self.input_fasta = Path(input_fasta)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        self.domain_searcher = PyHMMERDomainSearcher(PFAM_DB)
        
    def run_prodigal(self, region_fasta: str) -> Tuple[str, str]:
        """Run Prodigal gene prediction using Windows binary."""
        
        proteins_fasta = self.output_dir / "all_proteins.faa"
        genes_gff = self.output_dir / "all_genes.gff"
        
        print("🧬 Running Prodigal gene prediction...")
        
        cmd = [
            PRODIGAL_BIN,
            '-i', str(region_fasta),
            '-a', str(proteins_fasta),
            '-o', str(genes_gff),
            '-f', 'gff',
            '-p', 'meta',  # Metagenome mode
            '-q'  # Quiet
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Count proteins
            protein_count = 0
            if proteins_fasta.exists():
                for _ in SeqIO.parse(proteins_fasta, 'fasta'):
                    protein_count += 1
            
            print(f"   ✅ Predicted {protein_count} genes/proteins")
            return str(proteins_fasta), str(genes_gff)
            
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Prodigal failed: {e.stderr}")
            return None, None
        except FileNotFoundError:
            print(f"   ❌ Prodigal not found at {PRODIGAL_BIN}")
            return None, None
    
    def parse_prodigal_proteins(self, proteins_fasta: str) -> Dict[str, Dict]:
        """Parse Prodigal protein output with robust header parsing."""
        
        proteins = {}
        
        for record in SeqIO.parse(proteins_fasta, 'fasta'):
            header = record.description
            parts = header.split(' # ')
            
            protein_id = record.id
            
            try:
                if len(parts) >= 4:
                    start = int(parts[1])
                    end = int(parts[2])
                    strand = '+' if int(parts[3]) == 1 else '-'
                else:
                    match = re.search(r'#\s*(\d+)\s*#\s*(\d+)\s*#\s*(-?\d+)', header)
                    if match:
                        start = int(match.group(1))
                        end = int(match.group(2))
                        strand = '+' if int(match.group(3)) == 1 else '-'
                    else:
                        start, end, strand = 0, len(record.seq) * 3, '+'
                
                region_match = re.match(r'(.+)_(\d+)$', protein_id)
                if region_match:
                    region_id = region_match.group(1)
                    gene_num = int(region_match.group(2))
                else:
                    region_id = protein_id.rsplit('_', 1)[0] if '_' in protein_id else protein_id
                    gene_num = 1
                
                proteins[protein_id] = {
                    'protein_id': protein_id,
                    'region_id': region_id,
                    'gene_num': gene_num,
                    'start': start,
                    'end': end,
                    'strand': strand,
                    'length': len(record.seq),
                    'sequence': str(record.seq),
                    'domains': []
                }
                
            except Exception as e:
                continue
        
        return proteins
    
    def annotate_domains(self, proteins: Dict, domain_hits: List[Dict]) -> Dict:
        """Add domain annotations to proteins."""
        
        for hit in domain_hits:
            protein_id = hit['protein_id']
            if protein_id in proteins:
                domain_class = self.classify_domain(hit['pfam_name'], hit.get('pfam_accession', ''))
                
                proteins[protein_id]['domains'].append({
                    'pfam_name': hit['pfam_name'],
                    'pfam_accession': hit.get('pfam_accession', ''),
                    'domain_class': domain_class,
                    'score': hit['score'],
                    'evalue': hit['evalue'],
                    'start': hit.get('env_from', 0),
                    'end': hit.get('env_to', 0),
                })
        
        return proteins
    
    def classify_domain(self, pfam_name: str, pfam_acc: str) -> str:
        """Classify a Pfam domain into BGC domain class."""
        
        name_lower = pfam_name.lower()
        
        for domain_class, identifiers in BGC_DOMAIN_FAMILIES.items():
            for identifier in identifiers:
                if identifier.lower() in name_lower or identifier in pfam_acc:
                    return domain_class
        
        return 'OTHER'
    
    def build_bgc_graphs(self, proteins: Dict) -> Dict[str, Dict]:
        """Build BGC graphs from annotated proteins."""
        
        regions = defaultdict(list)
        for protein_id, protein in proteins.items():
            regions[protein['region_id']].append(protein)
        
        bgc_graphs = {}
        
        for region_id, region_proteins in regions.items():
            region_proteins.sort(key=lambda x: x['start'])
            
            all_domains = []
            domain_classes = defaultdict(int)
            
            for protein in region_proteins:
                for domain in protein['domains']:
                    all_domains.append(domain)
                    domain_classes[domain['domain_class']] += 1
            
            bgc_score = 0
            bgc_type = 'Unknown'
            
            pks_core = domain_classes.get('PKS_KS', 0)
            pks_at = domain_classes.get('PKS_AT', 0)
            nrps_a = domain_classes.get('NRPS_A', 0)
            nrps_c = domain_classes.get('NRPS_C', 0)
            terpene = domain_classes.get('Terpene_synth', 0)
            
            if pks_core >= 1 and nrps_a >= 1:
                bgc_type = 'PKS-NRPS_hybrid'
                bgc_score = (pks_core + nrps_a) * 10 + pks_at * 3 + nrps_c * 3
            elif pks_core >= 1:
                bgc_type = f'PKS_type-I' if pks_at >= 1 else 'PKS'
                bgc_score = pks_core * 10 + pks_at * 5
                if pks_core >= 3:
                    bgc_type += '_multimodular'
                elif pks_core == 1:
                    bgc_type += '_monomodular'
            elif nrps_a >= 1:
                bgc_type = 'NRPS'
                bgc_score = nrps_a * 10 + nrps_c * 5
                if nrps_a >= 3:
                    bgc_type += '_multimodular'
                elif nrps_a == 2:
                    bgc_type += '_bimodular'
                elif nrps_a == 1:
                    bgc_type += '_monomodular'
            elif terpene >= 1:
                bgc_type = 'Terpene'
                bgc_score = terpene * 8
            elif len(all_domains) > 0:
                bgc_type = 'Other'
                bgc_score = len(all_domains) * 2
            
            completeness = 'unknown'
            if bgc_type.startswith('NRPS'):
                has_a = nrps_a > 0
                has_c = nrps_c > 0
                has_te = domain_classes.get('TE', 0) > 0
                if has_a and has_c and has_te:
                    completeness = 'complete'
                elif has_a and (has_c or has_te):
                    completeness = 'partial'
                else:
                    completeness = 'fragment'
            elif bgc_type.startswith('PKS'):
                has_ks = pks_core > 0
                has_at = pks_at > 0
                has_te = domain_classes.get('TE', 0) > 0
                if has_ks and has_at and has_te:
                    completeness = 'complete'
                elif has_ks and has_at:
                    completeness = 'partial'
                else:
                    completeness = 'fragment'
            
            bgc_graphs[region_id] = {
                'region_id': region_id,
                'bgc_type': bgc_type,
                'bgc_score': bgc_score,
                'completeness': completeness,
                'total_genes': len(region_proteins),
                'total_domains': len(all_domains),
                'domain_counts': dict(domain_classes),
                'genes': region_proteins,
                'domain_architecture': self.get_domain_architecture(region_proteins),
            }
        
        return bgc_graphs
    
    def get_domain_architecture(self, proteins: List[Dict]) -> str:
        """Get linear domain architecture string."""
        
        architecture = []
        for protein in proteins:
            if protein['domains']:
                domains = sorted(protein['domains'], key=lambda x: x.get('start', 0))
                domain_str = '-'.join([d['domain_class'] for d in domains if d['domain_class'] != 'OTHER'])
                if domain_str:
                    architecture.append(f"[{domain_str}]")
        
        return ' → '.join(architecture) if architecture else 'No BGC domains'
    
    def run_pipeline(self):
        """Run the complete Stage-2 pipeline."""
        
        print("=" * 60)
        print("🔬 Stage-2 Production Pipeline (Windows + pyhmmer)")
        print("=" * 60)
        print(f"📁 Input: {self.input_fasta}")
        print(f"📂 Output: {self.output_dir}")
        print()
        
        if not self.input_fasta.exists():
            print(f"❌ Input file not found: {self.input_fasta}")
            return None
        
        # Step 1: Load Pfam database
        if not self.domain_searcher.load_pfam():
            print("❌ Cannot proceed without Pfam database")
            return None
        
        # Step 2: Run Prodigal
        proteins_fasta, genes_gff = self.run_prodigal(str(self.input_fasta))
        if not proteins_fasta:
            print("❌ Prodigal failed")
            return None
        
        # Step 3: Parse proteins
        print("📖 Parsing Prodigal output...")
        proteins = self.parse_prodigal_proteins(proteins_fasta)
        print(f"   ✅ Parsed {len(proteins)} proteins")
        
        # Step 4: Domain search
        print("🔍 Running domain search with pyhmmer...")
        domain_hits = self.domain_searcher.search_proteins(proteins_fasta)
        
        # Step 5: Annotate proteins
        print("📝 Annotating proteins with domains...")
        proteins = self.annotate_domains(proteins, domain_hits)
        
        proteins_with_domains = sum(1 for p in proteins.values() if p['domains'])
        print(f"   ✅ {proteins_with_domains} proteins have domain annotations")
        
        # Step 6: Build BGC graphs
        print("🔗 Building BGC graphs...")
        bgc_graphs = self.build_bgc_graphs(proteins)
        print(f"   ✅ Built {len(bgc_graphs)} region graphs")
        
        # Step 7: Filter BGC candidates
        bgc_candidates = {k: v for k, v in bgc_graphs.items() 
                         if v['bgc_score'] > 0 and v['total_domains'] > 0}
        
        print()
        print("📊 Results Summary:")
        print(f"   Total regions: {len(bgc_graphs)}")
        print(f"   BGC candidates: {len(bgc_candidates)}")
        
        # Step 8: Save results
        self.save_results(bgc_graphs, bgc_candidates)
        
        # Step 9: Print top candidates
        self.print_top_candidates(bgc_candidates)
        
        return bgc_candidates
    
    def save_results(self, all_graphs: Dict, candidates: Dict):
        """Save results to files."""
        
        full_path = self.output_dir / "all_bgc_graphs.json"
        with open(full_path, 'w') as f:
            json.dump(all_graphs, f, indent=2, default=str)
        print(f"💾 Saved full results: {full_path}")
        
        candidates_path = self.output_dir / "bgc_candidates.json"
        with open(candidates_path, 'w') as f:
            json.dump(candidates, f, indent=2, default=str)
        print(f"💾 Saved candidates: {candidates_path}")
        
        summary_path = self.output_dir / "bgc_summary.tsv"
        with open(summary_path, 'w') as f:
            headers = ['region_id', 'bgc_type', 'completeness', 'score', 
                      'genes', 'domains', 'architecture']
            f.write('\t'.join(headers) + '\n')
            
            for region_id, bgc in sorted(candidates.items(), 
                                         key=lambda x: x[1]['bgc_score'], 
                                         reverse=True):
                row = [
                    region_id,
                    bgc['bgc_type'],
                    bgc['completeness'],
                    str(bgc['bgc_score']),
                    str(bgc['total_genes']),
                    str(bgc['total_domains']),
                    bgc['domain_architecture']
                ]
                f.write('\t'.join(row) + '\n')
        
        print(f"📋 Saved summary: {summary_path}")
    
    def print_top_candidates(self, candidates: Dict):
        """Print top BGC candidates."""
        
        if not candidates:
            print("\n⚠️ No BGC candidates found")
            return
        
        sorted_candidates = sorted(candidates.items(), 
                                   key=lambda x: x[1]['bgc_score'], 
                                   reverse=True)[:15]
        
        print("\n🏆 Top BGC Candidates:")
        print("-" * 80)
        
        for region_id, bgc in sorted_candidates:
            print(f"\n📍 {region_id[:60]}...")
            print(f"   Type: {bgc['bgc_type']} | Completeness: {bgc['completeness']}")
            print(f"   Score: {bgc['bgc_score']} | Genes: {bgc['total_genes']} | Domains: {bgc['total_domains']}")
            print(f"   Architecture: {bgc['domain_architecture']}")
            
            if bgc['domain_counts']:
                counts = ', '.join([f"{k}:{v}" for k, v in bgc['domain_counts'].items() 
                                   if k != 'OTHER'])
                if counts:
                    print(f"   Domain counts: {counts}")


def main():
    """Main execution."""
    
    print()
    print("🧬 BGC Discovery Pipeline - Stage 2")
    print("   Windows Production Version (pyhmmer)")
    print()
    
    if not os.path.exists(PRODIGAL_BIN):
        print(f"❌ Prodigal not found at {PRODIGAL_BIN}")
        return
    
    if not os.path.exists(PFAM_DB):
        print(f"❌ Pfam database not found at {PFAM_DB}")
        return
    
    pipeline = Stage2ProductionPipeline(INPUT_FASTA, OUTPUT_DIR)
    results = pipeline.run_pipeline()
    
    if results:
        print("\n✅ Stage-2 Complete!")
        print(f"   Results in: {OUTPUT_DIR}/")
    else:
        print("\n❌ Stage-2 failed")


if __name__ == "__main__":
    main()
