"""
Stage-2 Gene Miner: Domain Annotation Parser
=============================================
Parse HMMER domain annotation results and build domain tables.

Input:  HMMER domtblout file + protein FASTA
Output: Structured domain table for BGC analysis
"""

import os
import re
import argparse
from pathlib import Path
from typing import List, Dict, Tuple
import pandas as pd
from Bio import SeqIO

# Key BGC domains (Pfam HMM names)
BGC_DOMAINS = {
    # PKS domains
    'PKS': ['PKS_KS', 'KS', 'Ketoacyl-synt_C', 'Ketoacyl-synt_M', 'PKS_synthase_CT'],
    'AT': ['PKS_AT', 'AT_domain', 'Acyl-CoA_dh_M', 'Acyl-CoA_dh_1'],
    'ACP': ['ACP_syn', 'ACP_beta', 'Acyl_carrier', 'PP-binding'],
    'KR': ['PKS_KR', 'KR_domain', 'ketoacyl-synt', 'adh_short', 'adh_short_C2'],
    'DH': ['PKS_DH', 'DH_domain'],
    'ER': ['PKS_ER', 'ER_domain'],
    'TE': ['Thioesterase', 'Thioest', 'TE_domain', 'Abhydrolase_1'],

    # NRPS domains
    'A': ['AMP-binding', 'A_domain', 'AMP-binding_C'],
    'C': ['Condensation', 'C_domain', 'Cond_subdomain'],
    'PCP': ['PCP', 'Thiolation', 'PP-binding'],
    'E': ['Epimerization'],

    # Modifying enzymes
    'MT': ['Methyltransf_', 'SAM_MT', 'Methyltransf_2', 'Methyltransf_3',
           'Methyltransf_11', 'Methyltransf_12', 'Methyltransf_23', 'NNMT_PNMT_TEMT'],
    'HAL': ['Halogenase', 'Trp_halogenase'],
    'P450': ['p450', 'Cyt-b5'],
    'GT': ['Glycos_transf_', 'Glycos_transf_1', 'Glycos_transf_2', 'Glyco_tran_28_C'],

    # RiPPs
    'Lasso': ['Lasso_Fused_RRE', 'PF13471', 'RRE_domain'],
    'Lanthi': ['Lant_dehydr_N', 'Lant_dehydr_C', 'DUF4135'],
    'Thiopep': ['Thiopep_cyc', 'YcaO', 'ATP-grasp'],

    # Terpenes
    'Terpene_synth': ['Terpene_synth', 'Terpene_synth_C', 'TRI5_like',
                      'Bflower', 'Bflower_2', 'SQHop_cyclase', 'SQHop_cyclase_C',
                      'Prenyltrans', 'GGPP_synth', 'Polyprenyl_synt',
                      'Terpene_cyclase', 'Gp5_trimer', 'Gp5_trimer_C'],
    'Terpene_cyclase': ['SQHop_cyclase', 'SQHop_cyclase_C', 'Terpene_cyclase',
                        'Lycopene_cycl', 'Terpene_synth_C'],

    # Resistance
    'ABC': ['ABC_tran', 'ABC_membrane', 'ABC_membrane_2', 'ABC_tran_2'],
    'MFS': ['MFS_1', 'MFS_2'],

    # Regulation
    'LuxR': ['LuxR_C_like', 'GerE'],
    'TetR': ['TetR_N', 'TetR_C'],

    # Other BGC-associated
    'FAD': ['FAD_binding_', 'FAD_binding_2', 'FAD_binding_3', 'PCMH-type_FAD'],
    'NAD': ['NAD_binding_', 'NAD_binding_1', 'NAD_binding_4', 'Rossmann-like'],
    'Oxidoreductase': ['2OG-FeII_Oxy', 'PhyH', 'Orn_DAP_Arg_mut', 'RmlD_sub_bind'],
    'Aminotransferase': ['Aminotran_', 'Aminotran_1_2', 'Aminotran_3', 'Aminotran_5'],
}

def flatten_domain_mapping():
    """Create HMM name -> domain type mapping."""
    mapping = {}
    for domain_type, hmm_names in BGC_DOMAINS.items():
        for hmm_name in hmm_names:
            mapping[hmm_name] = domain_type
    return mapping

def parse_domtblout(domtblout_path: str, evalue_cutoff: float = 1e-5) -> pd.DataFrame:
    """
    Parse HMMER domtblout file.
    
    Returns DataFrame with columns:
    - target_name (protein ID)
    - query_name (HMM model name) 
    - domain_type (PKS, NRPS, etc.)
    - evalue
    - score
    - hmm_from, hmm_to (HMM coordinates)
    - seq_from, seq_to (sequence coordinates)
    """
    
    print(f"Parsing domain annotations from {domtblout_path}...")
    
    if not os.path.exists(domtblout_path):
        raise FileNotFoundError(f"Domain table not found: {domtblout_path}")
    
    # Parse domtblout format
    domains = []
    domain_mapping = flatten_domain_mapping()
    
    with open(domtblout_path) as f:
        for line in f:
            if line.startswith('#'):
                continue
                
            fields = line.strip().split()
            if len(fields) < 22:
                continue
            
            # hmmscan domtblout format:
            # col 0 = HMM/profile name (target)
            # col 3 = protein/query name (query)
            query_name  = fields[0]   # HMM model name  (e.g. Terpene_synth)
            target_name = fields[3]   # protein sequence ID
            evalue = float(fields[6])   # full-seq E-value
            score = float(fields[7])    # bit score
            hmm_from = int(fields[15])  # HMM coord start
            hmm_to = int(fields[16])    # HMM coord end
            seq_from = int(fields[19])  # sequence coord start
            seq_to = int(fields[20])    # sequence coord end
            
            # Filter by E-value
            if evalue > evalue_cutoff:
                continue
            
            # Map HMM to domain type
            domain_type = None
            for hmm_pattern in domain_mapping:
                if hmm_pattern in query_name:
                    domain_type = domain_mapping[hmm_pattern]
                    break
            
            if domain_type is None:
                domain_type = 'OTHER'
            
            domains.append({
                'target_name': target_name,
                'query_name': query_name,
                'domain_type': domain_type,
                'evalue': evalue,
                'score': score,
                'hmm_from': hmm_from,
                'hmm_to': hmm_to,
                'seq_from': seq_from,
                'seq_to': seq_to
            })
    
    df = pd.DataFrame(domains)
    print(f"  Found {len(df)} significant domains (E-value < {evalue_cutoff})")
    
    if len(df) > 0:
        domain_counts = df['domain_type'].value_counts()
        print("  Domain distribution:")
        for domain, count in domain_counts.head(10).items():
            print(f"    {domain}: {count}")
    
    return df

def load_region_metadata(regions_fasta: str) -> pd.DataFrame:
    """Load per-region metadata from the original input FASTA."""
    regions = []

    for record in SeqIO.parse(regions_fasta, "fasta"):
        sequence = str(record.seq).upper()
        n_content_pct = round((sequence.count('N') / len(sequence) * 100), 2) if sequence else 0.0
        regions.append({
            'region_id': record.id,
            'region_header': record.description,
            'n_content_pct': n_content_pct,
        })

    return pd.DataFrame(regions)


def extract_gene_metadata(protein_fasta: str) -> pd.DataFrame:
    """
    Extract gene metadata from Prodigal protein FASTA headers.
    
    Prodigal format: >REGION_00001 # 123 # 456 # 1 # ID=1_1;partial=00;start_type=ATG
    
    Returns DataFrame with:
    - gene_id
    - region_id  
    - start, end
    - strand
    - partial
    """
    
    print(f"Extracting gene metadata from {protein_fasta}...")
    
    genes = []
    
    for record in SeqIO.parse(protein_fasta, "fasta"):
        header = record.description
        gene_id = record.id
        
        # Parse Prodigal header format
        # Example: >REGION_00001 # 123 # 456 # 1 # ID=1_1;partial=00;start_type=ATG
        parts = header.split(' # ')
        if len(parts) >= 4:
            try:
                start = int(parts[1])
                end = int(parts[2])
                strand = int(parts[3])  # 1 = forward, -1 = reverse
                
                # Extract region ID from gene ID
                # Gene ID format: REGIONNAME_00001
                region_match = re.match(r'(.+)_\d+$', gene_id)
                region_id = region_match.group(1) if region_match else "unknown"
                
                attributes = {}
                if len(parts) >= 5:
                    for field in parts[4].split(';'):
                        if '=' in field:
                            key, value = field.split('=', 1)
                            attributes[key] = value

                partial = attributes.get('partial', '')
                has_start_codon = len(partial) >= 1 and partial[0] == '0'
                has_stop_codon = len(partial) >= 2 and partial[1] == '0'

                genes.append({
                    'gene_id': gene_id,
                    'region_id': region_id,
                    'start': start,
                    'end': end,
                    'strand': strand,
                    'length': abs(end - start) + 1,
                    'partial': partial,
                    'has_start_codon': has_start_codon,
                    'has_stop_codon': has_stop_codon,
                })
            except ValueError:
                print(f"  Warning: Could not parse coordinates for {gene_id}")
    
    df = pd.DataFrame(genes)
    print(f"  Extracted metadata for {len(df)} genes")
    
    return df

def build_domain_table(
    domains_df: pd.DataFrame,
    genes_df: pd.DataFrame,
    regions_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build comprehensive domain table by joining domains with gene metadata.
    """
    
    print("Building comprehensive domain table...")
    
    # Join domains with gene metadata
    domain_table = domains_df.merge(
        genes_df, 
        left_on='target_name', 
        right_on='gene_id', 
        how='left'
    )

    if regions_df is not None and not regions_df.empty:
        domain_table = domain_table.merge(
            regions_df[['region_id', 'n_content_pct']],
            on='region_id',
            how='left',
        )
    elif 'n_content_pct' not in domain_table.columns:
        domain_table['n_content_pct'] = 0.0

    domain_table['n_content_pct'] = domain_table['n_content_pct'].fillna(0.0).astype(float)
    
    # Calculate domain coordinates in genomic context
    domain_table['domain_start'] = domain_table['start'] + domain_table['seq_from'] * 3
    domain_table['domain_end'] = domain_table['start'] + domain_table['seq_to'] * 3
    
    # Sort by region and genomic position
    domain_table = domain_table.sort_values(['region_id', 'start', 'seq_from'])
    
    print(f"  Built domain table with {len(domain_table)} entries")
    
    return domain_table

def main():
    parser = argparse.ArgumentParser(description="Parse HMMER domain annotations")
    parser.add_argument("--domtblout", "-d", required=True,
                       help="HMMER domtblout file")
    parser.add_argument("--proteins", "-p", required=True,
                       help="Protein FASTA from Prodigal")
    parser.add_argument("--regions-fasta", default=None,
                       help="Original input FASTA to propagate region metadata")
    parser.add_argument("--output", "-o", required=True,
                       help="Output CSV file for domain table")
    parser.add_argument("--evalue", "-e", type=float, default=1e-5,
                       help="E-value cutoff for domains (default: 1e-5)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Stage-2: Domain Annotation Parser")
    print("=" * 60)
    
    try:
        # Parse domain annotations
        domains_df = parse_domtblout(args.domtblout, args.evalue)
        
        # Extract gene metadata
        genes_df = extract_gene_metadata(args.proteins)
        regions_df = load_region_metadata(args.regions_fasta) if args.regions_fasta else None
        
        if len(domains_df) == 0:
            print("[WARN]  No significant domains found!")
            print("   Check your HMMER results and E-value cutoff")
        
        # Build comprehensive domain table
        domain_table = build_domain_table(domains_df, genes_df, regions_df)
        
        # Save results
        domain_table.to_csv(args.output, index=False)
        print(f"\n[OK] Domain table saved to: {args.output}")
        print(f"   Total domains: {len(domain_table)}")
        
        # Summary statistics
        if len(domain_table) > 0:
            bgc_domains = domain_table[domain_table['domain_type'] != 'OTHER']
            print(f"   BGC-relevant domains: {len(bgc_domains)}")
            print(f"   Regions with domains: {domain_table['region_id'].nunique()}")
        
    except Exception as e:
        print(f"\n[ERROR] Domain parsing failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
