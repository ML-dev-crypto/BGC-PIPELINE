#!/usr/bin/env python3
"""Tests for completeness metadata propagation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from classify_bgcs import BGCRuleEngine  # noqa: E402
from parse_domains import build_domain_table, extract_gene_metadata, load_region_metadata  # noqa: E402


def test_parse_domains_extracts_partial_and_n_content(tmp_path):
    proteins_faa = tmp_path / "proteins.faa"
    regions_fasta = tmp_path / "regions.fasta"

    proteins_faa.write_text(
        ">BGC_terpene_002_1 # 1 # 90 # 1 # ID=1_1;partial=01;start_type=ATG\n"
        "MSTIEQK\n",
        encoding="utf-8",
    )
    regions_fasta.write_text(
        ">BGC_terpene_002\nATGAAANNNTAA\n",
        encoding="utf-8",
    )

    domains_df = pd.DataFrame(
        [
            {
                "target_name": "BGC_terpene_002_1",
                "query_name": "Terpene_synth",
                "domain_type": "Terpene_synth",
                "evalue": 1e-20,
                "score": 250.0,
                "seq_from": 1,
                "seq_to": 40,
            }
        ]
    )

    genes_df = extract_gene_metadata(str(proteins_faa))
    regions_df = load_region_metadata(str(regions_fasta))
    domain_table = build_domain_table(domains_df, genes_df, regions_df)

    row = domain_table.iloc[0]
    assert row["partial"] == "01"
    assert bool(row["has_start_codon"]) is True
    assert bool(row["has_stop_codon"]) is False
    assert float(row["n_content_pct"]) == 25.0


def test_classifier_emits_schema_consistent_completeness_fields():
    domain_table = pd.DataFrame(
        [
            {
                "region_id": "BGC_terpene_002",
                "gene_id": "BGC_terpene_002_1",
                "domain_type": "Terpene_synth",
                "start": 1,
                "has_start_codon": True,
                "has_stop_codon": False,
                "n_content_pct": 25.0,
            }
        ]
    )

    result = BGCRuleEngine(domain_table).analyze_region("BGC_terpene_002", domain_table)

    assert result["completeness"] == result["completeness_tag"]
    assert result["has_start_codon"] is True
    assert result["has_stop_codon"] is False
    assert result["n_content_pct"] == 25.0

