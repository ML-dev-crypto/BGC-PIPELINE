import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

import pandas as pd
from classify_bgcs import BGCRuleEngine, RIPP_REQUIRED_PAIRS

def test_tandem_repeat_not_classified_as_ripp():
    """Sequence with only non-RiPP domains should not score RiPP highest"""
    # Create domain table with typical non-RiPP biosynthetic domains
    domain_data = {
        'region_id': ['test_region_1', 'test_region_1'],
        'gene_id': ['gene_1', 'gene_2'],
        'domain_type': ['PKS', 'ACP'],  # Non-RiPP domains
        'domain': ['PKS_KS', 'PCP'],
        'score': [0.95, 0.90],
        'start': [0, 5000],
        'has_start_codon': [True, True],
        'has_stop_codon': [True, True],
        'n_content_pct': [0.0, 0.0],
    }
    df = pd.DataFrame(domain_data)
    
    engine = BGCRuleEngine(df)
    result = engine.analyze_region('test_region_1', df)
    
    # Should classify as PKS or NRPS, not RiPP
    assert result['predicted_type'] != 'RiPP', \
        f"PKS domains should not be classified as RiPP, got: {result['predicted_type']}"
    assert result['predicted_type'] in ['PKS', 'NRPS', 'PKS-NRPS'], \
        f"Should classify as PKS/NRPS family, got: {result['predicted_type']}"

def test_lanthipeptide_requires_both_domains():
    """Only precursor without modifying enzyme should NOT classify as RiPP"""
    # Create domain table with ONLY precursor (LanA) but no modifying enzyme
    domain_data = {
        'region_id': ['test_region_2', 'test_region_2'],
        'gene_id': ['gene_1', 'gene_2'],
        'domain_type': ['LANT_', 'MT'],  # LanA domain but no LanB/LanC/LanM
        'domain': ['LanA', 'MT_enzyme'],
        'score': [0.95, 0.85],
        'start': [0, 5000],
        'has_start_codon': [True, True],
        'has_stop_codon': [True, True],
        'n_content_pct': [0.0, 0.0],
    }
    df = pd.DataFrame(domain_data)
    
    engine = BGCRuleEngine(df)
    result = engine.analyze_region('test_region_2', df)
    
    # Should NOT score RiPP with 0.0 when missing modifying enzyme
    ripp_score = result['type_scores'].get('RiPP', -1.0)
    assert ripp_score == 0.0, \
        f"RiPP with precursor-only should score 0.0 (AND logic), got: {ripp_score}"
    assert result['predicted_type'] != 'RiPP', \
        f"Precursor-only should not be top classification, got: {result['predicted_type']}"

def test_lanthipeptide_with_both_domains():
    """Lanthipeptide with BOTH precursor AND modifying enzyme should score well"""
    # Create domain table with BOTH precursor and modifying enzyme
    domain_data = {
        'region_id': ['test_region_3', 'test_region_3'],
        'gene_id': ['gene_1', 'gene_2'],
        'domain_type': ['LANT_', 'LanB'],
        'domain': ['LanA', 'LanB_enzyme'],
        'score': [0.95, 0.90],
        'start': [0, 5000],
        'has_start_codon': [True, True],
        'has_stop_codon': [True, True],
        'n_content_pct': [0.0, 0.0],
    }
    df = pd.DataFrame(domain_data)
    
    engine = BGCRuleEngine(df)
    result = engine.analyze_region('test_region_3', df)
    
    # Should score RiPP higher when both precursor AND modifying enzyme present
    ripp_score = result['type_scores'].get('RiPP', 0.0)
    assert ripp_score > 0.0, \
        f"RiPP with both precursor and modifying enzyme should score > 0.0, got: {ripp_score}"
