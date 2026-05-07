"""
Phase 5 — BiG-SCAPE-style BGC Family Clustering
================================================
Groups the 14 virtual BGCs from Phase 3/4 into Gene Cluster Families (GCFs)
using a three-component distance metric that mirrors BiG-SCAPE:

  distance(A, B) = 0.4 * (1 − J_domain)          # Jaccard on domain types
                 + 0.3 * (1 − LCS_order)          # normalised domain-order LCS
                 + 0.3 * (1 − seq_identity)        # representative protein identity

similarity = 1 − distance

An edge is drawn when similarity > SIMILARITY_CUTOFF (default 0.5).
Louvain community detection identifies Gene Cluster Families.
Singletons (family size == 1) are flagged as highest-priority novel systems.

Outputs (phase5_results/):
  bgc_similarity_matrix.json
  bgc_network.graphml
  gcf_clusters.json
  novel_bgc_families.json
  bgc_discovery_report.txt
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Tuple

# ── third-party ───────────────────────────────────────────────────────────────
try:
    import networkx as nx
except ImportError:
    sys.exit("networkx is required.  Run:  pip install networkx")

try:
    from Bio.Align import PairwiseAligner
except ImportError:
    sys.exit("biopython is required.  Run:  pip install biopython")

# ─────────────────────────────────────────────────────────────────────────────
SIMILARITY_CUTOFF = 0.30     # edge threshold (lower = broader families)
WEIGHTS = (0.4, 0.3, 0.3)   # Jaccard, order, sequence
OUTPUT_DIR = Path("phase5_results")

# Input files
VBGC_FILE   = Path("phase3_results/virtual_bgcs.json")
RANKING_FILE = Path("phase4_results/bgc_final_ranking.json")
NOVELTY_FILE = Path("phase3_results/bgc_novelty_scores.json")
BGCRES_FILE  = Path("stage2_production_results/bgc_results.json")


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def load_data() -> List[Dict]:
    """Merge Phase 3, Phase 4, and bgc_results into one record per VBGC."""
    vbgcs   = json.loads(VBGC_FILE.read_text())
    ranking = json.loads(RANKING_FILE.read_text())
    novelty = json.loads(NOVELTY_FILE.read_text())
    bgcres  = json.loads(BGCRES_FILE.read_text())

    # Index by VBGC id
    rank_idx = {r["vbgc_id"]: r for r in ranking}
    nov_idx  = {n["virtual_bgc_id"]: n for n in novelty}

    # Build a lookup: region_id -> list of protein sequences from bgc_results
    region_proteins: Dict[str, List[str]] = defaultdict(list)
    for region in bgcres:
        for gene in region.get("genes", []):
            seq = gene.get("protein_seq", "")
            if seq:
                region_proteins[region["region_id"]].append(seq)

    records = []
    for v in vbgcs:
        vid  = v["virtual_bgc_id"]
        rank = rank_idx.get(vid, {})
        nov  = nov_idx.get(vid, {})

        # Collect all protein sequences from member regions
        proteins: List[str] = []
        for mr in v.get("member_regions", []):
            # member_region strings look like:  "...start=X|end=Y|..."
            # Match against bgc_results region_id (same format)
            seqs = region_proteins.get(mr, [])
            proteins.extend(seqs)
        # Deduplicate while preserving order
        seen: set = set()
        unique_proteins = [p for p in proteins if not (p in seen or seen.add(p))]

        records.append({
            "vbgc_id":          vid,
            "bgc_class":        v.get("bgc_class", "Unknown"),
            "domain_arch":      v.get("domain_architecture", []),
            "member_regions":   v.get("member_regions", []),
            "member_count":     v.get("member_count", 0),
            "confidence":       v.get("confidence_score", 0.0),
            "proteins":         unique_proteins,
            # Phase 4
            "final_score":      rank.get("final_score", 0.0),
            "novelty_score":    rank.get("novelty_score", nov.get("novelty_score", 0.0)),
            "drug_potential":   rank.get("drug_potential_score", 0.0),
            "predicted_metabolite": rank.get("predicted_metabolite", "unknown"),
            "mol_weight":       rank.get("est_mol_weight_Da", 0.0),
            "logP":             rank.get("est_logP", 0.0),
        })
    return records


# ─────────────────────────────────────────────────────────────────────────────
# Component 1 — Domain Jaccard similarity
# ─────────────────────────────────────────────────────────────────────────────

def jaccard(a: List[str], b: List[str]) -> float:
    """Jaccard index on domain type multisets."""
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Component 2 — Domain order similarity (normalised LCS)
# ─────────────────────────────────────────────────────────────────────────────

def lcs_length(a: List[str], b: List[str]) -> int:
    """Standard DP longest common subsequence."""
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0
    # Use O(min(m,n)) space
    if m < n:
        a, b, m, n = b, a, n, m
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(curr[j - 1], prev[j])
        prev = curr
    return prev[n]


def order_similarity(a: List[str], b: List[str]) -> float:
    """Normalised LCS: LCS(a,b) / max(|a|,|b|)."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return lcs_length(a, b) / max(len(a), len(b))


# ─────────────────────────────────────────────────────────────────────────────
# Component 3 — Sequence identity (representative protein pair)
# ─────────────────────────────────────────────────────────────────────────────

_aligner = PairwiseAligner()
_aligner.mode            = "global"
_aligner.match_score     = 1
_aligner.mismatch_score  = 0
_aligner.open_gap_score  = -1
_aligner.extend_gap_score = -0.1


def seq_identity(a_seqs: List[str], b_seqs: List[str]) -> float:
    """
    Compare the single longest representative protein from each VBGC.
    Longer proteins tend to be the core biosynthetic enzyme (KS, A-domain).
    Returns percent identity (0–1).
    """
    if not a_seqs or not b_seqs:
        return 0.0

    rep_a = max(a_seqs, key=len)
    rep_b = max(b_seqs, key=len)

    # Truncate to 200 aa to keep alignment fast (heuristic representative)
    rep_a = rep_a[:200]
    rep_b = rep_b[:200]

    try:
        score = _aligner.score(rep_a, rep_b)
        max_possible = max(len(rep_a), len(rep_b))
        return score / max_possible if max_possible else 0.0
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Pairwise distance / similarity matrix
# ─────────────────────────────────────────────────────────────────────────────

def build_similarity_matrix(records: List[Dict]) -> Tuple[Dict, List[List[float]]]:
    """
    Returns:
      sim_dict  — {vbgc_id: {vbgc_id: similarity}}
      sim_rows  — flat list-of-lists for JSON serialisation
    """
    n = len(records)
    ids   = [r["vbgc_id"] for r in records]
    sim   = {a: {b: 0.0 for b in ids} for a in ids}

    # Diagonal = 1
    for r in records:
        sim[r["vbgc_id"]][r["vbgc_id"]] = 1.0

    w_j, w_o, w_s = WEIGHTS

    total_pairs = n * (n - 1) // 2
    done = 0

    for i, j in combinations(range(n), 2):
        ra, rb = records[i], records[j]

        j_score = jaccard(ra["domain_arch"], rb["domain_arch"])
        o_score = order_similarity(ra["domain_arch"], rb["domain_arch"])
        s_score = seq_identity(ra["proteins"], rb["proteins"])

        dist = w_j * (1 - j_score) + w_o * (1 - o_score) + w_s * (1 - s_score)
        similarity = max(0.0, 1.0 - dist)

        sim[ra["vbgc_id"]][rb["vbgc_id"]] = round(similarity, 4)
        sim[rb["vbgc_id"]][ra["vbgc_id"]] = round(similarity, 4)

        done += 1
        if done % 5 == 0 or done == total_pairs:
            pct = 100 * done / total_pairs
            print(f"  Similarity matrix: {done}/{total_pairs} pairs  ({pct:.0f}%)",
                  end="\r", flush=True)

    print()

    # Serialisable rows (ordered by ids)
    rows = [[sim[a][b] for b in ids] for a in ids]
    return sim, rows, ids


# ─────────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────────

def build_network(records: List[Dict], sim: Dict) -> nx.Graph:
    G = nx.Graph()
    for r in records:
        G.add_node(r["vbgc_id"],
                   bgc_class=r["bgc_class"],
                   novelty=r["novelty_score"],
                   drug_potential=r["drug_potential"],
                   final_score=r["final_score"],
                   member_count=r["member_count"])

    for i, j in combinations(range(len(records)), 2):
        ra, rb = records[i], records[j]
        s = sim[ra["vbgc_id"]][rb["vbgc_id"]]
        if s >= SIMILARITY_CUTOFF:
            G.add_edge(ra["vbgc_id"], rb["vbgc_id"], weight=s)

    return G


# ─────────────────────────────────────────────────────────────────────────────
# Gene Cluster Family detection (Louvain)
# ─────────────────────────────────────────────────────────────────────────────

def detect_gcf(G: nx.Graph, records: List[Dict]) -> List[Dict]:
    """
    Louvain on the similarity graph.  Isolated nodes (no edges above threshold)
    each form their own singleton GCF — those are the most novel clusters.
    """
    record_map = {r["vbgc_id"]: r for r in records}

    # Nodes with at least one edge
    connected = set(G.nodes()) - set(nx.isolates(G))

    gcfs = []
    gcf_id = 0

    if connected:
        subG = G.subgraph(connected).copy()
        communities = nx.community.louvain_communities(
            subG, weight="weight", resolution=1.0, seed=42)
        for comm in communities:
            members = sorted(comm)
            gcfs.append(_make_gcf(gcf_id, members, record_map, singleton=False))
            gcf_id += 1

    # Singletons
    for node in nx.isolates(G):
        gcfs.append(_make_gcf(gcf_id, [node], record_map, singleton=True))
        gcf_id += 1

    return sorted(gcfs, key=lambda g: (-g["is_singleton"], -g["max_novelty"]))


def _make_gcf(gcf_id: int, members: List[str],
              record_map: Dict, singleton: bool) -> Dict:
    recs = [record_map[m] for m in members]
    return {
        "gcf_id":        f"GCF_{gcf_id:04d}",
        "family_size":   len(members),
        "is_singleton":  singleton,
        "members":       members,
        "bgc_classes":   sorted({r["bgc_class"] for r in recs}),
        "max_novelty":   round(max(r["novelty_score"] for r in recs), 4),
        "max_drug_pot":  round(max(r["drug_potential"] for r in recs), 4),
        "top_metabolite": max(recs, key=lambda r: r["novelty_score"])["predicted_metabolite"],
        "member_details": [
            {
                "vbgc_id":    r["vbgc_id"],
                "bgc_class":  r["bgc_class"],
                "novelty":    r["novelty_score"],
                "drug_pot":   r["drug_potential"],
                "final_score": r["final_score"],
                "metabolite": r["predicted_metabolite"],
                "mol_weight": r["mol_weight"],
                "logP":       r["logP"],
            }
            for r in sorted(recs, key=lambda r: -r["novelty_score"])
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Discovery report
# ─────────────────────────────────────────────────────────────────────────────

def write_report(gcfs: List[Dict], records: List[Dict], path: Path) -> None:
    singletons = [g for g in gcfs if g["is_singleton"]]
    multi      = [g for g in gcfs if not g["is_singleton"]]

    lines = [
        "=" * 72,
        "  BGC Family Discovery Report — Phase 5",
        "  Pipeline: eDNA → Domain Annotation → Architecture → QML → GCF Clustering",
        "=" * 72,
        "",
        f"  Total virtual BGCs analysed : {len(records)}",
        f"  Gene Cluster Families found : {len(gcfs)}",
        f"  Singleton (novel) families  : {len(singletons)}",
        f"  Multi-member families       : {len(multi)}",
        "",
        "  Similarity threshold (edge) : {:.2f}".format(SIMILARITY_CUTOFF),
        "  Distance weights            : Jaccard={:.1f}  Order={:.1f}  Sequence={:.1f}".format(*WEIGHTS),
        "",
        "=" * 72,
        "  TOP NOVEL BGC FAMILIES  (singleton — no similar cluster in dataset)",
        "=" * 72,
        "",
        f"  {'VBGC ID':<12} {'Class':<28} {'Novelty':>8} {'Drug Pot':>9} "
        f"{'MW (Da)':>9} {'logP':>6}  Metabolite",
        "  " + "─" * 90,
    ]

    for g in singletons:
        d = g["member_details"][0]
        lines.append(
            f"  {d['vbgc_id']:<12} {d['bgc_class']:<28} {d['novelty']:>8.2f} "
            f"{d['drug_pot']:>9.4f} {d['mol_weight']:>9.0f} {d['logP']:>6.1f}  "
            f"{d['metabolite']}"
        )

    if multi:
        lines += [
            "",
            "=" * 72,
            "  MULTI-MEMBER FAMILIES  (shared biosynthetic logic)",
            "=" * 72,
            "",
        ]
        for g in multi:
            lines.append(
                f"  {g['gcf_id']}  size={g['family_size']}  "
                f"classes={', '.join(g['bgc_classes'])}  "
                f"max_novelty={g['max_novelty']:.2f}"
            )
            for d in g["member_details"]:
                lines.append(
                    f"    ↳ {d['vbgc_id']}  {d['bgc_class']:<28} "
                    f"novelty={d['novelty']:.2f}  drug={d['drug_pot']:.4f}"
                )
            lines.append("")

    lines += [
        "",
        "=" * 72,
        "  FULL RANKING (all BGCs, sorted by novelty)",
        "=" * 72,
        "",
        f"  {'Rank':<5} {'VBGC':<12} {'GCF':<10} {'Singles':^7} "
        f"{'Class':<28} {'Novelty':>8} {'Drug':>7}  Metabolite",
        "  " + "─" * 98,
    ]

    # Build vbgc→gcf mapping
    vbgc_gcf = {}
    for g in gcfs:
        for m in g["members"]:
            vbgc_gcf[m] = (g["gcf_id"], g["is_singleton"])

    sorted_recs = sorted(records, key=lambda r: -r["novelty_score"])
    for rank, r in enumerate(sorted_recs, 1):
        gcfid, is_s = vbgc_gcf.get(r["vbgc_id"], ("?", False))
        marker = "★" if is_s else " "
        lines.append(
            f"  {rank:<5} {r['vbgc_id']:<12} {gcfid:<10} {marker:^7} "
            f"{r['bgc_class']:<28} {r['novelty_score']:>8.2f} "
            f"{r['drug_potential']:>7.4f}  {r['predicted_metabolite']}"
        )

    lines += [
        "",
        "  ★ = singleton family (most likely novel biosynthetic system)",
        "",
        "=" * 72,
    ]

    path.write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 72)
    print("  Phase 5 — BiG-SCAPE-style BGC Family Clustering")
    print("=" * 72)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: load ─────────────────────────────────────────────────────────
    print("\n[1/7] Loading BGC data from Phase 3 & 4...")
    records = load_data()
    print(f"  {len(records)} virtual BGCs loaded.")
    for r in records:
        dlen  = len(r["domain_arch"])
        plen  = len(r["proteins"])
        print(f"  {r['vbgc_id']}  {r['bgc_class']:<30}  "
              f"domains={dlen}  proteins={plen}")

    # ── Step 2–4: pairwise similarity matrix ─────────────────────────────────
    print("\n[2/7] Computing pairwise similarity matrix...")
    print(f"  Components: Jaccard(w={WEIGHTS[0]})  Order(w={WEIGHTS[1]})  "
          f"Sequence(w={WEIGHTS[2]})")
    sim, sim_rows, ids = build_similarity_matrix(records)

    mat_path = OUTPUT_DIR / "bgc_similarity_matrix.json"
    mat_obj = {"labels": ids, "matrix": sim_rows,
               "similarity_threshold": SIMILARITY_CUTOFF}
    mat_path.write_text(json.dumps(mat_obj, indent=2))
    print(f"  Saved -> {mat_path}")

    # Print mini heatmap summary
    print("\n  Similarity matrix (rounded to 2 dp):")
    hdr = "         " + "".join(f"{i:>10}" for i in ids)
    print(f"  {hdr}")
    for i, a in enumerate(ids):
        row = "".join(f"{sim[a][b]:>10.2f}" for b in ids)
        print(f"  {a}: {row}")

    # ── Step 5: build network ─────────────────────────────────────────────────
    print(f"\n[3/7] Building similarity network (threshold={SIMILARITY_CUTOFF})...")
    G = build_network(records, sim)
    n_edges = G.number_of_edges()
    print(f"  Nodes: {G.number_of_nodes()}  Edges: {n_edges}")

    net_path = OUTPUT_DIR / "bgc_network.graphml"
    nx.write_graphml(G, net_path)
    print(f"  Saved -> {net_path}")

    if n_edges == 0:
        print("  ⚠  No edges above threshold — all BGCs are singletons.")
        print(f"     (Consider lowering SIMILARITY_CUTOFF below {SIMILARITY_CUTOFF})")

    # ── Step 6: GCF detection ─────────────────────────────────────────────────
    print("\n[4/7] Detecting Gene Cluster Families (Louvain)...")
    gcfs = detect_gcf(G, records)
    n_sing = sum(1 for g in gcfs if g["is_singleton"])
    n_multi = len(gcfs) - n_sing
    print(f"  {len(gcfs)} GCFs found  ({n_sing} singletons, {n_multi} multi-member)")

    gcf_path = OUTPUT_DIR / "gcf_clusters.json"
    gcf_path.write_text(json.dumps(gcfs, indent=2))
    print(f"  Saved -> {gcf_path}")

    # ── Step 7: novel family detection ───────────────────────────────────────
    print("\n[5/7] Identifying novel singleton families...")
    novel = [g for g in gcfs if g["is_singleton"]]
    novel_path = OUTPUT_DIR / "novel_bgc_families.json"
    novel_path.write_text(json.dumps(novel, indent=2))
    print(f"  {len(novel)} novel singleton families -> {novel_path}")

    # ── Step 8: discovery report ──────────────────────────────────────────────
    print("\n[6/7] Writing discovery report...")
    report_path = OUTPUT_DIR / "bgc_discovery_report.txt"
    write_report(gcfs, records, report_path)
    print(f"  Saved -> {report_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n[7/7] Summary")
    print("=" * 72)
    print(f"\n  Virtual BGCs analysed    : {len(records)}")
    print(f"  Gene Cluster Families    : {len(gcfs)}")
    print(f"  Novel singletons (★)     : {n_sing}")
    print(f"  Multi-member families    : {n_multi}")

    print("\n  Top 5 Novel BGC Candidates (singleton families, by novelty):")
    print(f"  {'VBGC':<12} {'Class':<30} {'Novelty':>8} {'Drug Pot':>9}  Metabolite")
    print("  " + "─" * 80)
    for g in sorted(novel, key=lambda g: -g["max_novelty"])[:5]:
        d = g["member_details"][0]
        print(f"  {d['vbgc_id']:<12} {d['bgc_class']:<30} "
              f"{d['novelty']:>8.2f} {d['drug_pot']:>9.4f}  {d['metabolite']}")

    if n_multi:
        print("\n  Multi-member families (shared biosynthetic logic):")
        for g in [g for g in gcfs if not g["is_singleton"]]:
            members_str = ", ".join(g["members"])
            print(f"  {g['gcf_id']}  [{members_str}]  "
                  f"classes={', '.join(g['bgc_classes'])}")

    print("\n  Output files:")
    for p in sorted(OUTPUT_DIR.glob("*")):
        size = p.stat().st_size
        print(f"    {p.name:40s} {size:>8,} bytes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
