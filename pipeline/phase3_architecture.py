"""
Phase 3: Biosynthetic Architecture Reconstruction
===================================================
Reconstructs virtual BGC architectures from domain-level data.

Pipeline:
  Step 1 - Domain Extraction        → phase3_results/domains.fasta
  Step 2 - Domain Clustering        → phase3_results/domain_clusters.json
  Step 3 - Co-occurrence Graph      → phase3_results/domain_network.graphml
  Step 4 - Community Detection      → phase3_results/domain_communities.json
  Step 5 - Virtual BGC Reconstruction → phase3_results/virtual_bgcs.json
  Step 6 - Novelty Scoring          → phase3_results/bgc_novelty_scores.json
"""

import json
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import networkx as nx
from networkx.algorithms.community import louvain_communities, greedy_modularity_communities

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

INPUT_JSON   = Path("stage2_production_results/bgc_results.json")
OUTPUT_DIR   = Path("phase3_results")

# Minimum protein length (aa) to include in domains.fasta
MIN_PROTEIN_LENGTH = 100  # lowered from 300 to avoid empty extraction if needed

# Primary biosynthetic domains to extract
BIOSYNTHETIC_DOMAIN_TYPES = {
    # PKS
    "PKS_KS", "PKS_AT", "PKS_ACP", "PKS_TE", "PKS_KR", "PKS_DH", "PKS_ER",
    # NRPS
    "NRPS_C", "NRPS_A", "NRPS_T", "NRPS_TE",
    # Terpene
    "Terpene_synth", "Terpene_synth_C",
    # RiPP
    "RiPP_precursor", "RiPP_modifying",
    # Beta-lactam / siderophore / alkaloid
    "BetaLactam_IPNS", "BetaLactam_DAOCS",
    "Siderophore_synth", "Siderophore_NRPS",
    "Alkaloid_synth",
}

# Tailoring / auxiliary domains
TAILORING_DOMAIN_TYPES = {
    "Methyltransf", "Glycosyltransf", "Oxygenase", "Reductase",
    "Epimerase", "Hydroxylase", "Cyclase", "Oxidase",
}

# Greedy clustering identity threshold
CLUSTER_IDENTITY = 0.60

# k-mer pre-filter: skip expensive alignment if k-mer similarity is below this
KMER_PREFILTER = 0.50

# Louvain resolution for community detection
LOUVAIN_RESOLUTION = 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_results(path: Path) -> list:
    with open(path) as fh:
        return json.load(fh)


def kmer_similarity(seq_a: str, seq_b: str, k: int = 4) -> float:
    """Fast k-mer Jaccard similarity between two protein sequences."""
    if not seq_a or not seq_b:
        return 0.0
    set_a = {seq_a[i:i+k] for i in range(len(seq_a) - k + 1)}
    set_b = {seq_b[i:i+k] for i in range(len(seq_b) - k + 1)}
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return len(set_a & set_b) / union


def pairwise_identity(seq_a: str, seq_b: str) -> float:
    """
    Global pairwise sequence identity via Needleman-Wunsch (globalxx).

    identity = identical positions / alignment length

    Uses Bio.pairwise2 which ships with Biopython (already a project dep).
    Returns 0.0 if alignment fails or sequences are empty.
    """
    if not seq_a or not seq_b:
        return 0.0
    try:
        from Bio import pairwise2
        alignments = pairwise2.align.globalxx(seq_a, seq_b,
                                              one_alignment_only=True,
                                              score_only=False)
        if not alignments:
            return 0.0
        aln = alignments[0]
        aligned_a, aligned_b = aln.seqA, aln.seqB
        aln_len = len(aligned_a)
        if aln_len == 0:
            return 0.0
        matches = sum(a == b and a != '-' for a, b in zip(aligned_a, aligned_b))
        return matches / aln_len
    except Exception:
        return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 – Domain Extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_domains(results: list, output_dir: Path) -> list:
    """
    Extract proteins that carry at least one biosynthetic domain.

    Returns:
        domain_entries: list of dicts with keys
            id, region_id, gene_id, protein_seq, bgc_class,
            domain_types, domain_info
    """
    print("\n── Step 1: Domain Extraction ──────────────────────────────────────")

    entries = []
    seen_ids = set()

    for region in results:
        region_id  = region["region_id"]
        bgc_class  = region.get("bgc_class", "Unknown")

        for gene in region.get("genes", []):
            protein_seq = gene.get("protein_seq", "")
            gene_id     = gene["gene_id"]
            length      = gene.get("length", len(protein_seq))

            if length < MIN_PROTEIN_LENGTH or not protein_seq:
                continue

            domains = gene.get("domains", [])
            bgc_domain_types = [
                d["bgc_type"] for d in domains
                if d.get("bgc_type") and d["bgc_type"] != "Other"
            ]

            if not bgc_domain_types:
                continue  # only keep proteins with annotated BGC domains

            # Unique FASTA id
            safe_id = re.sub(r"[^A-Za-z0-9_\-]", "_", gene_id)[:60]
            if safe_id in seen_ids:
                safe_id = f"{safe_id}_{len(seen_ids)}"
            seen_ids.add(safe_id)

            entries.append({
                "id":           safe_id,
                "region_id":    region_id,
                "gene_id":      gene_id,
                "bgc_class":    bgc_class,
                "protein_seq":  protein_seq,
                "domain_types": list(set(bgc_domain_types)),
                "domain_info":  domains,
                "length":       length,
            })

    # Write FASTA
    fasta_path = output_dir / "domains.fasta"
    with open(fasta_path, "w") as fh:
        for e in entries:
            fh.write(f">{e['id']} region={e['region_id']} class={e['bgc_class']} "
                     f"domains={','.join(e['domain_types'])}\n")
            # Wrap at 80 chars
            seq = e["protein_seq"]
            for i in range(0, len(seq), 80):
                fh.write(seq[i:i+80] + "\n")

    print(f"  Extracted {len(entries):,} biosynthetic proteins → {fasta_path}")
    return entries


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 – Domain Clustering (k-mer pre-filter + alignment refinement)
# ──────────────────────────────────────────────────────────────────────────────

def cluster_domains(entries: list, output_dir: Path) -> dict:
    """
    Greedy single-linkage clustering of domain proteins.

    Two-stage pipeline per candidate pair:
      1. k-mer Jaccard similarity (fast) — skip alignment if < KMER_PREFILTER
      2. Global Needleman-Wunsch identity  — cluster if ≥ CLUSTER_IDENTITY

    This avoids false positives from shared k-mers in structurally distinct
    proteins (e.g. two enzymes sharing repetitive motifs but different folds).

    Returns:
        dict with keys 'clusters' and 'entry_to_cluster'
    """
    print("\n── Step 2: Domain Clustering ──────────────────────────────────────")
    print(f"  Method: k-mer pre-filter (>{KMER_PREFILTER:.0%}) "
          f"+ global alignment identity (≥{CLUSTER_IDENTITY:.0%})")

    # Group by primary domain type — only compare within the same functional family
    by_dtype: dict[str, list] = defaultdict(list)
    for e in entries:
        primary = e["domain_types"][0] if e["domain_types"] else "Other"
        by_dtype[primary].append(e)

    clusters: dict[str, list] = {}          # cluster_id → [entry IDs]
    entry_to_cluster: dict[str, str] = {}
    cluster_reps: dict[str, dict] = {}      # cluster_id → representative entry

    cluster_idx = 0
    aln_calls = 0
    kmer_rejections = 0

    for dtype, group in by_dtype.items():
        prefix = f"CLU_{dtype[:10]}"
        # Collect only the cluster IDs that belong to this dtype
        dtype_clusters = {cid: cluster_reps[cid]
                          for cid in cluster_reps
                          if cid.startswith(prefix)}

        for entry in group:
            seq_a    = entry["protein_seq"]
            assigned = False

            for cid, rep in dtype_clusters.items():
                rep_seq = rep["protein_seq"]

                # ── Stage 1: k-mer pre-filter ────────────────────────────────
                kmer_sim = kmer_similarity(seq_a, rep_seq)
                if kmer_sim < KMER_PREFILTER:
                    kmer_rejections += 1
                    continue   # too dissimilar even at k-mer level → skip

                # ── Stage 2: pairwise alignment identity ─────────────────────
                aln_calls += 1
                identity = pairwise_identity(seq_a, rep_seq)
                if identity >= CLUSTER_IDENTITY:
                    clusters[cid].append(entry["id"])
                    entry_to_cluster[entry["id"]] = cid
                    assigned = True
                    break

            if not assigned:
                cid = f"{prefix}_{cluster_idx:04d}"
                clusters[cid] = [entry["id"]]
                cluster_reps[cid] = entry
                dtype_clusters[cid] = entry
                entry_to_cluster[entry["id"]] = cid
                cluster_idx += 1

    print(f"  {len(entries):,} proteins → {len(clusters):,} clusters")
    print(f"  Alignments run: {aln_calls:,}  |  k-mer rejections: {kmer_rejections:,}")

    # Build output structure
    cluster_out = []
    for cid, members in clusters.items():
        cluster_out.append({
            "cluster_id": cid,
            "size":       len(members),
            "members":    members,
        })

    out_path = output_dir / "domain_clusters.json"
    with open(out_path, "w") as fh:
        json.dump(cluster_out, fh, indent=2)
    print(f"  → {out_path}")

    # CD-HIT compatible .clstr summary
    clstr_path = output_dir / "domain_clusters.clstr"
    with open(clstr_path, "w") as fh:
        for i, (cid, members) in enumerate(clusters.items()):
            fh.write(f">Cluster {i}\n")
            for j, m in enumerate(members):
                flag = " *" if j == 0 else ""
                fh.write(f"{j}\t{m}{flag}\n")

    return {"clusters": clusters, "entry_to_cluster": entry_to_cluster}


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 – Co-occurrence Graph
# ──────────────────────────────────────────────────────────────────────────────

def build_cooccurrence_graph(results: list, output_dir: Path) -> nx.Graph:
    """
    Build a weighted co-occurrence graph where:
      nodes = domain types (bgc_type labels)
      edges = co-occurrence in the same BGC region
      weight = number of regions sharing both domain types
    """
    print("\n── Step 3: Co-occurrence Graph ────────────────────────────────────")

    G = nx.Graph()
    cooccurrence: dict[tuple, int] = defaultdict(int)

    for region in results:
        # Collect all unique domain types in this region
        region_domains: set[str] = set()
        for gene in region.get("genes", []):
            for d in gene.get("domains", []):
                dtype = d.get("bgc_type")
                if dtype and dtype != "Other":
                    region_domains.add(dtype)

        if not region_domains:
            continue

        # Add self-occurrence (node count)
        for dt in region_domains:
            if not G.has_node(dt):
                G.add_node(dt, count=0, bgc_classes=defaultdict(int))
            G.nodes[dt]["count"] += 1
            G.nodes[dt]["bgc_classes"][region.get("bgc_class", "Unknown")] += 1

        # Add pair co-occurrences
        for dt_a, dt_b in combinations(sorted(region_domains), 2):
            cooccurrence[(dt_a, dt_b)] += 1

    for (dt_a, dt_b), weight in cooccurrence.items():
        G.add_edge(dt_a, dt_b, weight=weight)

    # Serialize node attributes for graphml (convert defaultdict → dict)
    for n in G.nodes:
        classes = dict(G.nodes[n].get("bgc_classes", {}))
        G.nodes[n]["bgc_classes"] = json.dumps(classes)

    out_path = output_dir / "domain_network.graphml"
    nx.write_graphml(G, str(out_path))

    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges → {out_path}")
    return G


# ──────────────────────────────────────────────────────────────────────────────
# Step 4 – Community Detection (Louvain via NetworkX 3.x)
# ──────────────────────────────────────────────────────────────────────────────

def detect_communities(G: nx.Graph, output_dir: Path) -> list:
    """
    Run Louvain community detection.  Falls back to greedy modularity if the
    graph has too few edges for Louvain.

    Returns:
        communities_out: list of dicts with community_id, members, size,
                         dominant_class, modularity_contribution
    """
    print("\n── Step 4: Community Detection ────────────────────────────────────")

    communities_out = []

    if G.number_of_nodes() == 0:
        print("  ⚠ Empty graph – skipping community detection.")
        out_path = output_dir / "domain_communities.json"
        with open(out_path, "w") as fh:
            json.dump([], fh, indent=2)
        return []

    try:
        if G.number_of_edges() >= 2:
            partitions = louvain_communities(G, weight="weight",
                                             resolution=LOUVAIN_RESOLUTION,
                                             seed=42)
            method = "Louvain"
        else:
            partitions = list(greedy_modularity_communities(G, weight="weight"))
            method = "Greedy Modularity"
    except Exception as exc:
        print(f"  ⚠ Community detection error ({exc}); using connected components.")
        partitions = [list(c) for c in nx.connected_components(G)]
        method = "Connected Components"

    # Collect node metadata
    node_meta = {n: json.loads(G.nodes[n].get("bgc_classes", "{}"))
                 for n in G.nodes}

    for i, part in enumerate(partitions):
        members = list(part)
        # Aggregate class distribution across all member nodes
        class_totals: dict[str, int] = defaultdict(int)
        for m in members:
            for cls, cnt in node_meta.get(m, {}).items():
                class_totals[cls] += cnt
        dominant = max(class_totals, key=class_totals.get) if class_totals else "Unknown"

        communities_out.append({
            "community_id": f"COM_{i:03d}",
            "method":       method,
            "size":         len(members),
            "members":      members,
            "dominant_bgc_class": dominant,
            "class_distribution": dict(class_totals),
        })

    # Sort by size descending
    communities_out.sort(key=lambda x: x["size"], reverse=True)

    out_path = output_dir / "domain_communities.json"
    with open(out_path, "w") as fh:
        json.dump(communities_out, fh, indent=2)

    print(f"  {len(communities_out)} communities ({method}) → {out_path}")
    return communities_out


# ──────────────────────────────────────────────────────────────────────────────
# Step 5 – Virtual BGC Reconstruction
# ──────────────────────────────────────────────────────────────────────────────

def reconstruct_virtual_bgcs(results: list, communities: list,
                              cluster_data: dict, output_dir: Path) -> list:
    """
    Group BGC regions that share the same community-level domain composition
    to form 'virtual BGCs' – hypothetical complete clusters assembled from
    fragmented genomic evidence.

    Returns:
        virtual_bgcs: list of virtual BGC dicts
    """
    print("\n── Step 5: Virtual BGC Reconstruction ─────────────────────────────")

    entry_to_cluster = cluster_data.get("entry_to_cluster", {})

    # Build region → set of domain types for quick lookup
    region_domains: dict[str, set] = {}
    region_class:   dict[str, str] = {}
    region_arch:    dict[str, list] = {}

    for region in results:
        rid = region["region_id"]
        dtypes: set[str] = set()
        for gene in region.get("genes", []):
            for d in gene.get("domains", []):
                dt = d.get("bgc_type")
                if dt and dt != "Other":
                    dtypes.add(dt)
        region_domains[rid] = dtypes
        region_class[rid]   = region.get("bgc_class", "Unknown")
        region_arch[rid]    = region.get("domain_architecture", [])

    # Build community membership lookup: domain_type → community_id
    domain_to_community: dict[str, str] = {}
    for comm in communities:
        for m in comm["members"]:
            domain_to_community[m] = comm["community_id"]

    # Assign each region to a community based on dominant domain membership
    region_to_comm: dict[str, str] = defaultdict(lambda: "COM_UNKNOWN")
    for rid, dtypes in region_domains.items():
        votes: dict[str, int] = defaultdict(int)
        for dt in dtypes:
            cid = domain_to_community.get(dt, "COM_UNKNOWN")
            votes[cid] += 1
        if votes:
            region_to_comm[rid] = max(votes, key=votes.get)

    # Group regions by (community, bgc_class) → virtual BGC
    vbgc_groups: dict[tuple, list] = defaultdict(list)
    for rid in region_domains:
        cid = region_to_comm[rid]
        cls = region_class.get(rid, "Unknown")
        vbgc_groups[(cid, cls)].append(rid)

    virtual_bgcs = []
    for (cid, cls), members in sorted(vbgc_groups.items(),
                                       key=lambda x: len(x[1]), reverse=True):
        # Union of all domain types across members
        union_domains: set[str] = set()
        for rid in members:
            union_domains |= region_domains.get(rid, set())

        # Architecture as sorted unique sequence
        arch = sorted(union_domains)

        # Confidence: fraction of expected core domains present
        expected = _expected_core_domains(cls)
        present  = len(union_domains & expected) if expected else len(union_domains)
        denom    = len(expected) if expected else max(len(union_domains), 1)
        confidence = min(present / denom, 1.0)

        virtual_bgcs.append({
            "virtual_bgc_id":     f"VBGC_{len(virtual_bgcs):04d}",
            "community_id":       cid,
            "bgc_class":          cls,
            "member_regions":     members,
            "member_count":       len(members),
            "domain_architecture": arch,
            "total_domains":      len(union_domains),
            "confidence_score":   round(confidence, 4),
        })

    out_path = output_dir / "virtual_bgcs.json"
    with open(out_path, "w") as fh:
        json.dump(virtual_bgcs, fh, indent=2)

    print(f"  Reconstructed {len(virtual_bgcs)} virtual BGCs → {out_path}")
    return virtual_bgcs


def _expected_core_domains(bgc_class: str) -> set:
    """Return the expected set of core domain types for a BGC class."""
    mapping = {
        "Type I PKS":             {"PKS_KS", "PKS_AT", "PKS_ACP"},
        "Type I PKS (reducing)":  {"PKS_KS", "PKS_AT", "PKS_ACP", "PKS_KR"},
        "NRPS":                   {"NRPS_C", "NRPS_A", "NRPS_T"},
        "PKS-NRPS Hybrid":        {"PKS_KS", "PKS_AT", "NRPS_C", "NRPS_A"},
        "Terpene":                 {"Terpene_synth"},
        "RiPP":                    {"RiPP_precursor"},
        "Beta-lactam":             {"BetaLactam_IPNS"},
        "Siderophore":             {"Siderophore_synth"},
        "Alkaloid":                {"Alkaloid_synth"},
    }
    for key, domains in mapping.items():
        if key.lower() in bgc_class.lower() or bgc_class.lower() in key.lower():
            return domains
    return set()


# ──────────────────────────────────────────────────────────────────────────────
# Step 6 – Novelty Scoring
# ──────────────────────────────────────────────────────────────────────────────

# Known canonical BGC architectures (reference "fingerprints")
CANONICAL_FINGERPRINTS: dict[str, frozenset] = {
    "Type I PKS":      frozenset({"PKS_KS", "PKS_AT", "PKS_ACP", "PKS_TE"}),
    "NRPS":            frozenset({"NRPS_C", "NRPS_A", "NRPS_T", "NRPS_TE"}),
    "PKS-NRPS Hybrid": frozenset({"PKS_KS", "PKS_AT", "NRPS_C", "NRPS_A"}),
    "Terpene":         frozenset({"Terpene_synth", "Terpene_synth_C"}),
    "RiPP":            frozenset({"RiPP_precursor", "RiPP_modifying"}),
}

def _jaccard_distance(set_a: frozenset, set_b: frozenset) -> float:
    if not set_a and not set_b:
        return 0.0
    return 1.0 - len(set_a & set_b) / len(set_a | set_b)


def score_novelty(virtual_bgcs: list, results: list, output_dir: Path) -> list:
    """
    Assign a novelty score to each virtual BGC.

    Score = (unique_domain_count × 2)
          + (tailoring_domain_count × 0.5)
          + (min_canonical_distance × 10)
          + (multi_class_bonus × 3)

    ∈ [0, ∞) — higher = more divergent from known archetypes
    """
    print("\n── Step 6: Novelty Scoring ────────────────────────────────────────")

    # Build per-region domain counts for rarity weighting
    domain_freq: dict[str, int] = defaultdict(int)
    total_regions = len(results)
    for region in results:
        seen_in_region: set[str] = set()
        for gene in region.get("genes", []):
            for d in gene.get("domains", []):
                dt = d.get("bgc_type")
                if dt and dt != "Other":
                    seen_in_region.add(dt)
        for dt in seen_in_region:
            domain_freq[dt] += 1

    novelty_scores = []

    for vbgc in virtual_bgcs:
        arch_set = frozenset(vbgc["domain_architecture"])

        unique_domains   = len(arch_set)
        tailoring_count  = sum(1 for d in arch_set if d in TAILORING_DOMAIN_TYPES)

        # Rarity bonus: sum of (1 - freq/total) for each domain
        rarity_bonus = sum(
            1.0 - domain_freq.get(d, 0) / max(total_regions, 1)
            for d in arch_set
        )

        # Canonical distance: min Jaccard distance to known archetypes
        if arch_set:
            min_dist = min(
                _jaccard_distance(arch_set, fp)
                for fp in CANONICAL_FINGERPRINTS.values()
            )
        else:
            min_dist = 0.0

        # Multi-class bonus (regions from different BGC classes in same virtual BGC)
        class_set = {
            r.get("bgc_class", "Unknown")
            for vr in vbgc["member_regions"]
            for r in results
            if r["region_id"] == vr
        }
        multi_class_bonus = max(0, len(class_set) - 1)

        score = (
            unique_domains  * 2.0
            + tailoring_count    * 0.5
            + rarity_bonus       * 1.0
            + min_dist           * 10.0
            + multi_class_bonus  * 3.0
        )

        novelty_scores.append({
            "virtual_bgc_id":       vbgc["virtual_bgc_id"],
            "bgc_class":            vbgc["bgc_class"],
            "novelty_score":        round(score, 4),
            "unique_domain_count":  unique_domains,
            "tailoring_domains":    tailoring_count,
            "rarity_bonus":         round(rarity_bonus, 4),
            "canonical_distance":   round(min_dist, 4),
            "multi_class_bonus":    multi_class_bonus,
            "domain_architecture":  list(arch_set),
        })

    # Sort by novelty score descending
    novelty_scores.sort(key=lambda x: x["novelty_score"], reverse=True)

    out_path = output_dir / "bgc_novelty_scores.json"
    with open(out_path, "w") as fh:
        json.dump(novelty_scores, fh, indent=2)

    print(f"  Scored {len(novelty_scores)} virtual BGCs → {out_path}")

    # Print top-10 summary
    print("\n  Top virtual BGCs by novelty:")
    print(f"  {'Rank':<5} {'VBGC ID':<14} {'Class':<30} {'Score':>8}  {'Dist':>6}")
    print("  " + "─" * 70)
    for rank, ns in enumerate(novelty_scores[:10], 1):
        print(f"  {rank:<5} {ns['virtual_bgc_id']:<14} {ns['bgc_class']:<30} "
              f"{ns['novelty_score']:>8.2f}  {ns['canonical_distance']:>6.3f}")

    return novelty_scores


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  Phase 3: Biosynthetic Architecture Reconstruction")
    print("=" * 72)

    # Validate input
    if not INPUT_JSON.exists():
        print(f"\n❌ Input not found: {INPUT_JSON}")
        print("   Run stage2_windows_production.py first (protein_seq now included).")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nInput : {INPUT_JSON}")
    print(f"Output: {OUTPUT_DIR}/")

    # Load data
    results = load_results(INPUT_JSON)
    print(f"\nLoaded {len(results)} BGC regions from JSON.")

    # Check if protein sequences are present
    sample_genes = [g for r in results for g in r.get("genes", [])]
    has_seqs = any(g.get("protein_seq") for g in sample_genes)
    if not has_seqs:
        print("\n⚠  protein_seq not found in JSON.")
        print("  Re-run stage2_windows_production.py to regenerate with sequences.")
        print("  Continuing with domain-type-level analysis only.\n")

    # ── Step 1 ──────────────────────────────────────────────────────────────
    domain_entries = extract_domains(results, OUTPUT_DIR)

    # ── Step 2 ──────────────────────────────────────────────────────────────
    cluster_data = cluster_domains(domain_entries, OUTPUT_DIR)

    # ── Step 3 ──────────────────────────────────────────────────────────────
    G = build_cooccurrence_graph(results, OUTPUT_DIR)

    # ── Step 4 ──────────────────────────────────────────────────────────────
    communities = detect_communities(G, OUTPUT_DIR)

    # ── Step 5 ──────────────────────────────────────────────────────────────
    virtual_bgcs = reconstruct_virtual_bgcs(results, communities, cluster_data, OUTPUT_DIR)

    # ── Step 6 ──────────────────────────────────────────────────────────────
    novelty_scores = score_novelty(virtual_bgcs, results, OUTPUT_DIR)

    # ── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  Phase 3 Complete")
    print("=" * 72)

    output_files = [
        OUTPUT_DIR / "domains.fasta",
        OUTPUT_DIR / "domain_clusters.json",
        OUTPUT_DIR / "domain_network.graphml",
        OUTPUT_DIR / "domain_communities.json",
        OUTPUT_DIR / "virtual_bgcs.json",
        OUTPUT_DIR / "bgc_novelty_scores.json",
    ]
    print("\nOutput files:")
    all_ok = True
    for f in output_files:
        status = "✅" if f.exists() else "❌"
        size   = f"{f.stat().st_size:,} bytes" if f.exists() else "missing"
        print(f"  {status}  {f.name:<35}  {size}")
        if not f.exists():
            all_ok = False

    if not all_ok:
        print("\n⚠  Some output files are missing.")
    else:
        print("\nAll outputs generated successfully.")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
