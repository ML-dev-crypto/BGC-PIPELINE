"""
Stage-2 Production Pipeline - Windows Native
=============================================
Uses Windows Prodigal + pyhmmer for full biological validation.

Provides:
- Real gene prediction (Prodigal)
- Proper domain architecture (KS/AT/A-domain combinations)
- Cluster completeness signals
- NRPS-class: mono/bi-modular, truncated/full analysis
"""

import os
import re
import sys
import gzip
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict

from Bio import SeqIO
from Bio.Seq import Seq

# Try to import pyhmmer
try:
    import pyhmmer
    from pyhmmer.plan7 import HMMFile
    from pyhmmer.easel import SequenceFile, TextSequence, Alphabet
    PYHMMER_AVAILABLE = True
except ImportError:
    PYHMMER_AVAILABLE = False
    print("WARNING: pyhmmer not available. Install with: pip install pyhmmer")

# ================= CONFIGURATION =================
INPUT_FASTA = "stage2_test_results/extracted_regions.fasta"
OUTPUT_DIR = "stage2_production_results"
PFAM_DB = "pfam_data/Pfam-A.hmm"
PRODIGAL_BIN = "tools/prodigal.exe"

# Analysis parameters
E_VALUE_CUTOFF = 1e-5
MIN_GENE_LENGTH = 100  # amino acids

# BGC Core Domain Definitions (Pfam accessions)
BGC_CORE_DOMAINS = {
    # ── TYPE I PKS (Polyketide Synthase) ─────────────────────────────────────
    'PKS_KS': ['PF00109', 'PF02801'],
    'PKS_AT': ['PF00698'],
    'PKS_ACP': ['PF00550'],
    'PKS_KR': ['PF08659'],
    'PKS_DH': ['PF14765'],
    'PKS_ER': ['PF08030'],
    'PKS_TE': ['PF00975'],

    # ── TYPE II PKS (iterative, aromatic polyketides e.g. actinorhodin) ──────
    # NOTE: The canonical Type II KS beta (CLF) Pfam is NOT in standard Pfam-A
    # as a standalone entry in this build.  PF04673 (Cyclase_polyket) is the
    # best available proxy — it is the aromatic polyketide cyclase/aromatase
    # found exclusively in Type II PKS clusters.
    'PKS2_CYC':  ['PF04673'],         # aromatase/cyclase (Type II PKS specific)

    # ── TYPE III PKS (chalcone synthase family, germicidin, resveratrol) ─────
    # PF00195 = chalcone synthase N-terminal; PF02797 = C-terminal domain
    # Both should be present in a genuine Type III PKS enzyme.
    'PKS3_CHS_N': ['PF00195'],        # chalcone/stilbene synthase N-term
    'PKS3_CHS_C': ['PF02797'],        # chalcone/stilbene synthase C-term

    # ── NRPS (Non-Ribosomal Peptide Synthetase) ───────────────────────────────
    'NRPS_A': ['PF00501', 'PF13623'],
    'NRPS_C': ['PF00668', 'PF08415'],
    'NRPS_T': ['PF00550'],
    'NRPS_E': ['PF08415'],
    'NRPS_TE': ['PF00975'],

    # ── Terpene (Terpenoid) ───────────────────────────────────────────────────
    # PF01397 = terpene synthase N-terminal; PF03936 = C-terminal metal-binding
    # PF00348 = polyprenyl synthase (farnesyl/geranyl PP synthase)
    # PF00494 = squalene/phytoene synthase (SQS_PSY) — hopene/triterpenes
    # PF13243 = squalene-hopene cyclase C-term; PF13249 = N-term
    # PF13243 removed from Terpene_bact \u2014 this IS the hopene cyclase, not sesquiterpene
    'Terpene_synth':  ['PF01397', 'PF03936', 'PF00348'],
    'Terpene_cyclase':['PF01348', 'PF13243', 'PF13249'],  # added hopene N-term
    'Terpene_presynth':['PF02223'],
    'Terpene_squal':  ['PF00494', 'PF06330'],  # SQS_PSY + TRI5 squalene synthase
    'Terpene_bact':   [],              # PF19086 removed (promiscuous); no good replacement yet

    # ── RiPP (Ribosomally synthesized & Post-translationally modified) ────────
    'RiPP_LANTHI': ['PF14867'],          # PF05147 (AMP-binding) removed — too promiscuous
    'RiPP_NISIN':  ['PF13602'],
    'RiPP_THIO':   ['PF03798'],
    'RiPP_LAP':    ['PF10439'],
    'RiPP_BACT':   ['PF00040', 'PF00141'],

    # ── Beta-lactam ───────────────────────────────────────────────────────────
    # PF05483 = isopenicillin N synthase (IPNS)
    # PF03400 = beta-lactam synthetase (BLS, carbapenem/clavulanic acid)
    'BetaLactam_synthase':      ['PF05483', 'PF03400'],
    'BetaLactam_transpeptidase':['PF00905'],
    'BetaLactam_cyclase':       ['PF05483'],

    # ── Siderophore (Iron Chelation) ─────────────────────────────────────────
    # PF04183 = IucA_IucC = NIS synthetase (aerobactin, desferrioxamine)
    # PF08541 = NIS synthetase (alternate entry)
    # PF00501 listed as Siderophore_NRPS but is the broad AMP-binding domain;
    # only counts for siderophore when ≥2 Siderophore_ domain types are present.
    'Siderophore_NRPS':    ['PF00501'],
    'Siderophore_synthase':['PF04320'],
    'Siderophore_NIS':     ['PF08541', 'PF04183'],  # NIS synthetase + IucA/IucC
    'Siderophore_ORF':     ['PF01116', 'PF13621'],

    # ── Alkaloid (Indole / tryptophan-derived) ────────────────────────────────
    # PF04183 (IucA/IucC) moved to Siderophore_NIS above
    'Indole_synthase':   [],
    'Indole_prenyl':     [],           # removed promiscuous PF02223/PF00175
    'Indole_cyclase':    [],
    'Tryptophan_oxidase':['PF02226'],

    # ── Tailoring Enzymes ─────────────────────────────────────────────────────
    'P450':          ['PF00067'],
    'Methyltransf':  ['PF08241', 'PF08242', 'PF13489'],
    'Glycosyltransf':['PF00201', 'PF00534', 'PF07470'],
    'Aminotransf':   ['PF00155', 'PF00265'],
    'Dehydrogenase': ['PF00106', 'PF08270'],
    'Acyltransf':    ['PF03905', 'PF04604'],
}

# Domain architecture patterns for classification
MODULE_PATTERNS = {
    'PKS_minimal': ['PKS_KS', 'PKS_AT'],
    'PKS_reducing': ['PKS_KS', 'PKS_AT', 'PKS_KR'],
    'PKS_complete': ['PKS_KS', 'PKS_AT', 'PKS_KR', 'PKS_DH', 'PKS_ER'],
    'NRPS_minimal': ['NRPS_A'],
    'NRPS_complete': ['NRPS_C', 'NRPS_A', 'NRPS_T'],
}


@dataclass
class Gene:
    """Predicted gene with annotations."""
    gene_id: str
    start: int
    end: int
    strand: str
    protein_seq: str
    domains: List[Dict] = field(default_factory=list)
    
    def __post_init__(self):
        self.length = len(self.protein_seq)


@dataclass
class BGCRegion:
    """Analyzed BGC candidate region."""
    region_id: str
    sequence_length: int
    genes: List[Gene] = field(default_factory=list)
    domain_architecture: List[str] = field(default_factory=list)
    bgc_class: str = "Unknown"
    module_count: int = 0
    completeness: str = "Unknown"
    score: float = 0.0


class ProductionStage2Pipeline:
    """Production-grade Stage-2 pipeline for Windows."""
    
    def __init__(self, input_fasta: str, output_dir: str, 
                 pfam_db: str, prodigal_bin: str):
        self.input_fasta = Path(input_fasta)
        self.output_dir = Path(output_dir)
        self.pfam_db = Path(pfam_db)
        self.prodigal_bin = Path(prodigal_bin)
        
        self.output_dir.mkdir(exist_ok=True)
        
        # Load Pfam HMM database
        self.hmm_db = None
        self.pfam_acc_to_name = {}
        
    def load_pfam_database(self) -> bool:
        """Load Pfam HMM database for pyhmmer."""
        if not PYHMMER_AVAILABLE:
            print("❌ pyhmmer not available")
            return False
            
        if not self.pfam_db.exists():
            # Check for gzipped version
            gz_path = self.pfam_db.with_suffix('.hmm.gz')
            if gz_path.exists():
                print(f"📦 Decompressing {gz_path}...")
                import gzip
                import shutil
                with gzip.open(gz_path, 'rb') as f_in:
                    with open(self.pfam_db, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                print("✅ Decompression complete")
            else:
                print(f"❌ Pfam database not found: {self.pfam_db}")
                return False
        
        print(f"📚 Loading Pfam database: {self.pfam_db}")
        print("   (This may take a minute...)")
        
        try:
            # Load HMMs into memory for faster searching - CORRECT binary file handle
            with open(self.pfam_db, 'rb') as f:
                self.hmms = list(pyhmmer.plan7.HMMFile(f))
            
            # Build accession to name mapping
            for hmm in self.hmms:
                raw_acc  = hmm.accession if hmm.accession else hmm.name
                raw_name = hmm.name
                acc  = raw_acc  if isinstance(raw_acc,  str) else raw_acc.decode()
                name = raw_name if isinstance(raw_name, str) else raw_name.decode()
                self.pfam_acc_to_name[acc] = name
                # Also map by base accession (without version)
                base_acc = acc.split('.')[0]
                self.pfam_acc_to_name[base_acc] = name
            
            print(f"✅ Loaded {len(self.hmms):,} Pfam HMMs")

            # ── Optimization: keep only BGC-relevant HMMs ────────────────
            # Collect all Pfam accessions referenced in BGC_CORE_DOMAINS
            bgc_accs: set[str] = set()
            for acc_list in BGC_CORE_DOMAINS.values():
                for a in acc_list:
                    bgc_accs.add(a.split('.')[0])  # strip version suffix

            filtered = []
            for hmm in self.hmms:
                raw_acc = hmm.accession if hmm.accession else hmm.name
                a = raw_acc if isinstance(raw_acc, str) else raw_acc.decode()
                if a.split('.')[0] in bgc_accs:
                    filtered.append(hmm)

            print(f"🎯 Filtered to {len(filtered):,} BGC-relevant HMMs "
                  f"(from {len(self.hmms):,} total)")
            self.hmms = filtered
            # ────────────────────────────────────────────────────────────

            return True
            
        except Exception as e:
            print(f"❌ Failed to load Pfam database: {e}")
            return False
    
    def run_prodigal(self, sequence: str, region_id: str) -> List[Gene]:
        """Run Prodigal gene prediction on a sequence."""
        genes = []
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Write input sequence
            input_file = temp_path / "input.fasta"
            with open(input_file, 'w') as f:
                f.write(f">{region_id}\n{sequence}\n")
            
            # Output files
            protein_file = temp_path / "proteins.faa"
            gff_file = temp_path / "genes.gff"
            
            # Run Prodigal
            cmd = [
                str(self.prodigal_bin),
                '-i', str(input_file),
                '-a', str(protein_file),
                '-o', str(gff_file),
                '-f', 'gff',
                '-p', 'meta',  # Metagenomic mode (single short sequences)
                '-q'  # Quiet
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"    ⚠️  Prodigal failed: {e.stderr[:100]}")
                return genes
            except FileNotFoundError:
                print(f"    ❌ Prodigal not found at {self.prodigal_bin}")
                return genes
            
            # Parse protein output
            if protein_file.exists():
                for record in SeqIO.parse(protein_file, 'fasta'):
                    # Parse Prodigal header: >region_1 # 1 # 300 # 1 # ID=1_1;...
                    header = record.description
                    parts = header.split(' # ')
                    
                    if len(parts) >= 5:
                        try:
                            start = int(parts[1])
                            end = int(parts[2])
                            strand = '+' if parts[3] == '1' else '-'
                        except (ValueError, IndexError):
                            start, end, strand = 0, 0, '+'
                    else:
                        start, end, strand = 0, 0, '+'
                    
                    protein_seq = str(record.seq).rstrip('*')
                    
                    if len(protein_seq) >= MIN_GENE_LENGTH:
                        gene = Gene(
                            gene_id=record.id,
                            start=start,
                            end=end,
                            strand=strand,
                            protein_seq=protein_seq
                        )
                        genes.append(gene)
        
        return genes
    
    def search_domains(self, genes: List[Gene]) -> List[Gene]:
        """Search Pfam domains using pyhmmer.hmmscan (version-safe)."""
        
        if not PYHMMER_AVAILABLE or not self.hmms:
            return genes
        
        alphabet = pyhmmer.easel.Alphabet.amino()
        sequences = []
        seq_to_gene = {}
        
        for gene in genes:
            try:
                seq = pyhmmer.easel.TextSequence(
                    name=gene.gene_id.encode(),
                    sequence=gene.protein_seq
                ).digitize(alphabet)
                
                sequences.append(seq)
                seq_to_gene[gene.gene_id] = gene
            except Exception:
                continue
        
        if not sequences:
            return genes
        
        print(f"    🔍 Scanning {len(sequences)} proteins against {len(self.hmms):,} Pfam HMMs...")
        
        try:
            # ✅ VERSION-SAFE CALL - Windows build expects (sequences, hmms) order
            hits = pyhmmer.hmmscan(
                sequences,
                self.hmms,
                E=E_VALUE_CUTOFF,
                domE=E_VALUE_CUTOFF
            )
            
            domains_found = []
            
            for top_hits in hits:                          # one protein
                # Version-safe decoding (Windows vs Linux pyhmmer)
                protein_id = top_hits.query.name
                protein_id = protein_id if isinstance(protein_id, str) else protein_id.decode()
                
                for hit in top_hits:                       # one Pfam HMM
                    pfam_name = hit.name
                    pfam_name = pfam_name if isinstance(pfam_name, str) else pfam_name.decode()
                    
                    pfam_acc = hit.accession
                    pfam_acc = (
                        pfam_acc if isinstance(pfam_acc, str)
                        else pfam_acc.decode() if pfam_acc else pfam_name
                    )
                    
                    for domain in hit.domains:
                        if domain.included:
                            domains_found.append({
                                "protein_id": protein_id,
                                "pfam_acc": pfam_acc.split(".")[0],
                                "pfam_name": pfam_name,
                                "start": domain.env_from,
                                "end": domain.env_to,
                                "evalue": domain.i_evalue,
                                "score": domain.score,
                                "bgc_type": self._classify_domain(pfam_acc.split(".")[0])
                            })
            
            for d in domains_found:
                gene = seq_to_gene.get(d["protein_id"])
                if gene:
                    gene.domains.append(d)
            
            print(f"    ✅ Found {len(domains_found)} domain hits")
        
        except Exception as e:
            print(f"    ⚠️  Domain search error: {e}")
        
        return genes
    
    def _classify_domain(self, pfam_acc: str) -> str:
        """Classify a Pfam domain into BGC type."""
        for bgc_type, accessions in BGC_CORE_DOMAINS.items():
            if pfam_acc in accessions:
                return bgc_type
        return "Other"
    
    def analyze_architecture(self, genes: List[Gene]) -> Tuple[List[str], str, int, str]:
        """Analyze domain architecture and classify BGC."""
        # Collect all domains in order
        all_domains = []
        for gene in sorted(genes, key=lambda g: g.start):
            for domain in sorted(gene.domains, key=lambda d: d['start']):
                if domain['bgc_type'] != 'Other':
                    all_domains.append(domain['bgc_type'])
        
        if not all_domains:
            return [], "No BGC domains", 0, "No domains"
        
        # Count domain types
        domain_counts = Counter(all_domains)
        
        # Determine BGC class
        bgc_class = self._determine_bgc_class(domain_counts)
        
        # Count modules
        module_count = self._count_modules(all_domains)
        
        # Assess completeness
        completeness = self._assess_completeness(domain_counts, bgc_class)
        
        return all_domains, bgc_class, module_count, completeness
    
    def _determine_bgc_class(self, domain_counts: Counter) -> str:
        """Determine BGC class from domain counts (8 classes + hybrids)."""

        # ── Type I PKS ──────────────────────────────────────────────────────
        # Require KS + AT (≥2) co-present. Fatty acid synthase (FAS) clusters
        # carry a single acyltransferase (AT=1) alongside many KS domains;
        # genuine PKS clusters have one AT per module, so ≥2 ATs is a reliable
        # signal while AT=1 alone can be FAS contamination.
        has_pks1_core = (domain_counts.get('PKS_KS', 0) >= 1 and
                         domain_counts.get('PKS_AT', 0) >= 2)

        # ── NRPS ────────────────────────────────────────────────────────────
        NRPS_CORE = ('NRPS_A', 'NRPS_C', 'NRPS_E', 'NRPS_TE')
        has_nrps = any(d in domain_counts for d in NRPS_CORE)

        # Reducing-domain hint: counts as PKS only in context of NRPS (hybrid)
        _has_pks_reduct = any(d in domain_counts
                              for d in ('PKS_ER', 'PKS_KR', 'PKS_DH'))
        has_pks1 = has_pks1_core or (_has_pks_reduct and has_nrps)

        # ── Type II PKS (aromatic polyketides: actinorhodin, tetracyclines) ─
        # PF04673 (Cyclase_polyket) is the best Pfam-A proxy for Type II PKS.
        has_pks2 = domain_counts.get('PKS2_CYC', 0) >= 1

        # ── Type III PKS (chalcone synthase family: germicidin, flavonoids) ─
        # Require BOTH N- and C-terminal chalcone domains, OR ≥2 N-term hits.
        has_pks3 = ((domain_counts.get('PKS3_CHS_N', 0) >= 1 and
                     domain_counts.get('PKS3_CHS_C', 0) >= 1) or
                    domain_counts.get('PKS3_CHS_N', 0) >= 2)

        # Aggregate PKS flag for hybrid detection
        has_pks = has_pks1 or has_pks2 or has_pks3

        # ── Terpene ─────────────────────────────────────────────────────────
        # Broadened to include squalene/phytoene (PF06330: hopene) and the
        # terpenoid cyclase superfamily (PF13243). Terpene_bact (PF13243) also
        # requires ≥2 hits to avoid isolated cyclase domain noise.
        has_terpene = (any(d in domain_counts
                           for d in ('Terpene_synth', 'Terpene_cyclase',
                                     'Terpene_presynth', 'Terpene_squal')) or
                       domain_counts.get('Terpene_bact', 0) >= 2)

        # ── RiPP ─────────────────────────────────────────────────────────────
        # Require ≥2 distinct RiPP domain types to avoid single-hit noise.
        ripp_types = {d for d in domain_counts if d.startswith('RiPP_')}
        has_ripp = len(ripp_types) >= 2

        # ── Beta-lactam ──────────────────────────────────────────────────────
        has_betalactam = any(d.startswith('BetaLactam_') for d in domain_counts)

        # ── Siderophore ──────────────────────────────────────────────────────
        # NIS synthetase (PF08541/PF04183) alone is not reliable — require ≥2
        # NIS hits, OR ≥2 distinct siderophore domain types.
        sid_types = {d for d in domain_counts if d.startswith('Siderophore_')}
        has_siderophore = (len(sid_types) >= 2 or
                           domain_counts.get('Siderophore_NIS', 0) >= 2)

        has_indole = any(d.startswith('Indole_') and domain_counts[d] > 0
                         for d in domain_counts)

        # ── Hybrid detection (2+ primary classes) ───────────────────────────
        primary_classes = sum([has_pks, has_nrps, has_terpene, has_ripp,
                               has_betalactam, has_siderophore, has_indole])

        if primary_classes >= 2:
            if has_pks and has_nrps:
                return "PKS-NRPS Hybrid"
            elif has_pks and has_terpene:
                return "PKS-Terpene Hybrid"
            elif has_nrps and has_terpene:
                return "NRPS-Terpene Hybrid"
            else:
                return "Multi-class Hybrid"

        # ── Single-class assignments ─────────────────────────────────────────
        if has_pks3:
            return "Type III PKS"
        if has_pks2:
            return "Type II PKS"
        if has_pks1:
            if domain_counts.get('PKS_KR', 0) > 0:
                return "Type I PKS (reducing)"
            return "Type I PKS"
        if has_nrps:
            return "NRPS"
        if has_terpene:
            # Bacterial sesquiterpene synthase (geosmin, 2-MIB)
            if domain_counts.get('Terpene_bact', 0) > 0:
                return "Terpene (bacterial sesquiterpene)"
            if domain_counts.get('Terpene_squal', 0) > 0:
                return "Terpene (squalene/triterpene)"
            if domain_counts.get('Terpene_cyclase', 0) > 0:
                return "Terpene (cyclase)"
            return "Terpene (synthase)"
        if has_ripp:
            if domain_counts.get('RiPP_LANTHI', 0) > 0:
                return "RiPP (Lanthipeptide)"
            if domain_counts.get('RiPP_THIO', 0) > 0:
                return "RiPP (Thioamides)"
            return "RiPP"
        if has_betalactam:
            return "Beta-lactam"
        if has_siderophore:
            if any(d in domain_counts
                   for d in ('Siderophore_NIS',)):
                return "Siderophore (NIS)"
            if domain_counts.get('Siderophore_NRPS', 0) > 0:
                return "Siderophore (NRPS-based)"
            return "Siderophore"
        if has_indole:
            return "Alkaloid (Indole pathway)"
        return "Unknown"
    
    def _count_modules(self, domains: List[str]) -> int:
        """Count biosynthetic modules."""
        # Count KS domains (each indicates PKS module)
        # Count A domains (each indicates NRPS module)
        ks_count = domains.count('PKS_KS')
        a_count = domains.count('NRPS_A')
        return ks_count + a_count
    
    def _assess_completeness(self, domain_counts: Counter, bgc_class: str) -> str:
        """Assess module completeness for all BGC types."""
        
        # TYPE I PKS completeness
        if "PKS" in bgc_class and "NRPS" not in bgc_class:
            has_ks = domain_counts.get('PKS_KS', 0) > 0
            has_at = domain_counts.get('PKS_AT', 0) > 0
            has_acp = domain_counts.get('PKS_ACP', 0) > 0
            has_te = domain_counts.get('PKS_TE', 0) > 0
            has_kr = domain_counts.get('PKS_KR', 0) > 0
            has_dh = domain_counts.get('PKS_DH', 0) > 0
            
            score = sum([has_ks, has_at, has_acp, has_te, has_kr, has_dh])
            if score == 6:
                return "Complete (full cycle: KS+AT+ACP+TE+KR+DH)"
            elif has_ks and has_at and has_acp and has_te:
                return "Complete (loading + extension + termination)"
            elif has_ks and has_at and has_acp:
                return "Partial (extension modules)"
            elif has_ks and has_at:
                return "Partial (minimal modules)"
            else:
                return "Truncated"
        
        # NRPS completeness
        elif "NRPS" in bgc_class and "PKS" not in bgc_class:
            has_c = domain_counts.get('NRPS_C', 0) > 0
            has_a = domain_counts.get('NRPS_A', 0) > 0
            has_t = domain_counts.get('NRPS_T', 0) > 0
            has_e = domain_counts.get('NRPS_E', 0) > 0
            has_te = domain_counts.get('NRPS_TE', 0) > 0
            
            score = sum([has_c, has_a, has_t, has_e, has_te])
            if score == 5:
                return "Complete C-A-T-E-TE modules"
            elif has_c and has_a and has_t:
                return "Complete C-A-T module"
            elif has_a:
                a_count = domain_counts.get('NRPS_A', 0)
                if a_count == 1:
                    return "Mono-modular (1 A-domain)"
                elif a_count == 2:
                    return "Bi-modular (2 A-domains)"
                else:
                    return f"Multi-modular ({a_count} A-domains)"
            else:
                return "Truncated"
        
        # Terpene completeness
        elif "Terpene" in bgc_class:
            has_synth = domain_counts.get('Terpene_synth', 0) > 0
            has_cyclase = domain_counts.get('Terpene_cyclase', 0) > 0
            has_presynth = domain_counts.get('Terpene_presynth', 0) > 0
            
            if has_synth and has_cyclase:
                return "Complete (synthase + cyclase)"
            elif has_synth:
                return "Partial (synthase only)"
            else:
                return "Truncated"
        
        # RiPP completeness
        elif "RiPP" in bgc_class:
            has_peptide = domain_counts.get('RiPP_BACT', 0) > 0
            has_mod = any(d.startswith('RiPP_') for d in domain_counts 
                         if d not in ['RiPP_BACT'])
            
            if has_peptide and has_mod:
                return "Complete (precursor + modification)"
            elif has_peptide:
                return "Partial (precursor only)"
            else:
                return "Truncated"
        
        # Beta-lactam completeness
        elif "Beta-lactam" in bgc_class:
            has_synthase = domain_counts.get('BetaLactam_synthase', 0) > 0
            has_cyclase = domain_counts.get('BetaLactam_cyclase', 0) > 0
            has_transpeptidase = domain_counts.get('BetaLactam_transpeptidase', 0) > 0
            
            if has_synthase and has_cyclase:
                return "Complete (synthase + cyclase)"
            elif has_synthase:
                return "Partial (synthase only)"
            else:
                return "Truncated"
        
        # Siderophore completeness
        elif "Siderophore" in bgc_class:
            has_nrps = domain_counts.get('Siderophore_NRPS', 0) > 0
            has_synthase = domain_counts.get('Siderophore_synthase', 0) > 0
            has_orf = domain_counts.get('Siderophore_ORF', 0) > 0
            
            if has_nrps or has_synthase:
                if has_orf:
                    return "Complete (NRPS/synthase + ORF)"
                else:
                    return "Partial (NRPS/synthase)"
            else:
                return "Truncated"
        
        # Alkaloid (Indole) completeness
        elif "Alkaloid" in bgc_class or "Indole" in bgc_class:
            has_indole_synth = domain_counts.get('Indole_synthase', 0) > 0
            has_cyclase = domain_counts.get('Indole_cyclase', 0) > 0
            has_prenyl = domain_counts.get('Indole_prenyl', 0) > 0
            
            if has_indole_synth and (has_cyclase or has_prenyl):
                return "Complete (synthase + modification)"
            elif has_indole_synth:
                return "Partial (synthase only)"
            else:
                return "Truncated"
        
        # Hybrid completeness
        elif "Hybrid" in bgc_class:
            has_pks = any(d.startswith('PKS_') for d in domain_counts)
            has_nrps = any(d.startswith('NRPS_') for d in domain_counts)
            pks_score = sum([domain_counts.get(d, 0) > 0 for d in 
                           ['PKS_KS', 'PKS_AT', 'PKS_ACP', 'PKS_TE']])
            nrps_score = sum([domain_counts.get(d, 0) > 0 for d in 
                            ['NRPS_C', 'NRPS_A', 'NRPS_T', 'NRPS_TE']])
            
            if pks_score >= 3 and nrps_score >= 3:
                return "Complete (both PKS and NRPS modules)"
            elif pks_score >= 2 and nrps_score >= 2:
                return "Partial (incomplete PKS or NRPS)"
            else:
                return "Truncated"
        
        return "Unknown"
    
    def process_region(self, region_id: str, sequence: str) -> Optional[BGCRegion]:
        """Process a single BGC candidate region."""
        print(f"  🧬 {region_id[:50]}... ({len(sequence):,} bp)")
        
        # Step 1: Gene prediction with Prodigal
        genes = self.run_prodigal(sequence, region_id)
        print(f"    📍 Genes: {len(genes)}")
        
        if not genes:
            return None
        
        # Step 2: Domain annotation with pyhmmer
        genes = self.search_domains(genes)
        
        total_domains = sum(len(g.domains) for g in genes)
        bgc_domains = sum(
            1 for g in genes 
            for d in g.domains 
            if d['bgc_type'] != 'Other'
        )
        print(f"    🔍 Domains: {total_domains} total, {bgc_domains} BGC-related")
        
        # Step 3: Analyze architecture
        architecture, bgc_class, module_count, completeness = self.analyze_architecture(genes)
        print(f"    🏷️  Class: {bgc_class} | Modules: {module_count} | {completeness}")
        
        # Create result
        region = BGCRegion(
            region_id=region_id,
            sequence_length=len(sequence),
            genes=genes,
            domain_architecture=architecture,
            bgc_class=bgc_class,
            module_count=module_count,
            completeness=completeness,
            score=self._calculate_score(bgc_domains, module_count, completeness)
        )
        
        return region
    
    def _calculate_score(self, bgc_domains: int, modules: int, completeness: str) -> float:
        """Calculate BGC quality score."""
        score = 0.0
        
        # Base score from domain count
        score += min(bgc_domains * 2, 10)
        
        # Module bonus
        score += min(modules * 3, 15)
        
        # Completeness bonus
        if "Complete" in completeness:
            score += 10
        elif "Multi-modular" in completeness or "Bi-modular" in completeness:
            score += 7
        elif "Mono-modular" in completeness:
            score += 5
        elif "Partial" in completeness:
            score += 3
        
        return score
    
    def run_pipeline(self) -> List[BGCRegion]:
        """Run the complete Stage-2 pipeline."""
        print("🔬 Stage-2 Production Pipeline")
        print("=" * 60)
        print(f"📁 Input: {self.input_fasta}")
        print(f"📂 Output: {self.output_dir}")
        print(f"🧬 Prodigal: {self.prodigal_bin}")
        print(f"📚 Pfam: {self.pfam_db}")
        print()
        
        # Load Pfam database
        if PYHMMER_AVAILABLE:
            if not self.load_pfam_database():
                print("⚠️  Continuing without domain annotation...")
        else:
            print("⚠️  pyhmmer not available - domain annotation disabled")
        
        # Check Prodigal
        if not self.prodigal_bin.exists():
            print(f"❌ Prodigal not found: {self.prodigal_bin}")
            return []
        
        # Load sequences
        print("\n📖 Loading candidate regions...")
        if not self.input_fasta.exists():
            print(f"❌ Input file not found: {self.input_fasta}")
            return []
        
        sequences = {}
        for record in SeqIO.parse(self.input_fasta, 'fasta'):
            sequences[record.id] = str(record.seq)
        
        print(f"   Found {len(sequences)} regions")
        
        # Process each region
        print("\n🔄 Processing regions...")
        results = []
        
        for i, (region_id, sequence) in enumerate(sequences.items(), 1):
            print(f"\n[{i}/{len(sequences)}]", end="")
            region = self.process_region(region_id, sequence)
            if region and region.score > 0:
                results.append(region)
        
        # Sort by score
        results.sort(key=lambda r: r.score, reverse=True)
        
        # Save results
        self.save_results(results)
        
        return results
    
    def save_results(self, results: List[BGCRegion]):
        """Save pipeline results."""
        print("\n💾 Saving results...")
        
        # Convert to serializable format
        def gene_to_dict(gene: Gene) -> dict:
            return {
                'gene_id': gene.gene_id,
                'start': gene.start,
                'end': gene.end,
                'strand': gene.strand,
                'length': gene.length,
                'protein_seq': gene.protein_seq,
                'domains': gene.domains
            }
        
        def region_to_dict(region: BGCRegion) -> dict:
            return {
                'region_id': region.region_id,
                'sequence_length': region.sequence_length,
                'bgc_class': region.bgc_class,
                'module_count': region.module_count,
                'completeness': region.completeness,
                'score': region.score,
                'domain_architecture': region.domain_architecture,
                'genes': [gene_to_dict(g) for g in region.genes]
            }
        
        # Save full JSON
        full_results = [region_to_dict(r) for r in results]
        json_path = self.output_dir / "bgc_results.json"
        with open(json_path, 'w') as f:
            json.dump(full_results, f, indent=2)
        print(f"   ✅ {json_path}")
        
        # Save summary TSV
        import pandas as pd
        summary_data = []
        for r in results:
            domain_str = ' → '.join(r.domain_architecture[:10])
            if len(r.domain_architecture) > 10:
                domain_str += f" ... (+{len(r.domain_architecture)-10} more)"
            
            summary_data.append({
                'region_id': r.region_id,
                'length_bp': r.sequence_length,
                'bgc_class': r.bgc_class,
                'modules': r.module_count,
                'completeness': r.completeness,
                'score': r.score,
                'total_genes': len(r.genes),
                'bgc_domains': len(r.domain_architecture),
                'architecture': domain_str
            })
        
        if summary_data:
            df = pd.DataFrame(summary_data)
            tsv_path = self.output_dir / "bgc_summary.tsv"
            df.to_csv(tsv_path, sep='\t', index=False)
            print(f"   ✅ {tsv_path}")
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 STAGE-2 RESULTS SUMMARY")
        print("=" * 60)
        print(f"Total regions processed: {len(results)}")
        
        # Class breakdown
        class_counts = Counter(r.bgc_class for r in results)
        print("\n🏷️  BGC Class Distribution:")
        for cls, count in class_counts.most_common():
            print(f"   {cls}: {count}")
        
        # Top candidates
        print("\n🏆 Top 10 BGC Candidates:")
        for i, r in enumerate(results[:10], 1):
            print(f"   {i}. {r.region_id[:40]}...")
            print(f"      Class: {r.bgc_class} | Modules: {r.module_count} | Score: {r.score:.1f}")
            print(f"      {r.completeness}")
        
        print("\n✅ Stage-2 Production Complete!")


def main():
    """Main entry point."""
    pipeline = ProductionStage2Pipeline(
        input_fasta=INPUT_FASTA,
        output_dir=OUTPUT_DIR,
        pfam_db=PFAM_DB,
        prodigal_bin=PRODIGAL_BIN
    )
    
    results = pipeline.run_pipeline()
    
    if results:
        print(f"\n🎉 Found {len(results)} validated BGC candidates!")
    else:
        print("\n❌ No BGC candidates found.")


if __name__ == "__main__":
    main()
