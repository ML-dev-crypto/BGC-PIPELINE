"""
Phase 4: Metabolite Prediction and Drug-Discovery Ranking
==========================================================
Analyzes reconstructed virtual BGCs to predict natural products
and rank their pharmaceutical potential.

Pipeline:
  Step 1 - Load Phase 3 Data
  Step 2 - NRPS Peptide Prediction        → nrps_predictions.json
  Step 3 - PKS Polyketide Prediction      → pks_predictions.json
  Step 4 - Hybrid Pathway Detection       → hybrid_predictions.json
  Step 5 - Molecular Property Estimation  → metabolite_properties.json
  Step 6 - Drug Potential Ranking (QML)   → qml_drug_scores.json
  Step 7 - Final Candidate Ranking        → bgc_final_ranking.json
"""

import json
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

VIRTUAL_BGCS_JSON   = Path("phase3_results/virtual_bgcs.json")
NOVELTY_SCORES_JSON = Path("phase3_results/bgc_novelty_scores.json")
BGC_RESULTS_JSON    = Path("stage2_production_results/bgc_results.json")
OUTPUT_DIR          = Path("phase4_results")

# ──────────────────────────────────────────────────────────────────────────────
# A-domain substrate prediction motifs
# (simplified rule-based; real tools use Stachelhaus code / NRPSpredictor2)
# ──────────────────────────────────────────────────────────────────────────────

NRPS_A_MOTIFS: list[tuple[str, str]] = [
    # (substring in A-domain seq region, predicted amino acid)
    ("DVWIGG",   "Leu"),
    ("DLFIGS",   "Ile"),
    ("DAFIGS",   "Val"),
    ("DAWIGG",   "Val"),
    ("DAWVGG",   "Val"),
    ("DEFVGG",   "Phe"),
    ("DQFIGS",   "Gln"),
    ("DNFIGS",   "Asn"),
    ("DSFIGS",   "Ser"),
    ("DTFIGS",   "Thr"),
    ("DAFVGG",   "Ala"),
    ("DGFVGG",   "Gly"),
    ("STGXPK",   "Ser"),   # X = any
    ("DLWIGE",   "Trp"),
    ("DMFIGS",   "Met"),
    ("DCFIGS",   "Cys"),
    ("DKFIGS",   "Lys"),
    ("DRFIGS",   "Arg"),
    ("DHFIGS",   "His"),
    ("DYFIGS",   "Tyr"),
    ("DWFIGS",   "Trp"),
    ("DPFIGS",   "Pro"),
    ("DEFIGS",   "Glu"),
    ("DDFIGS",   "Asp"),
    ("DLFVGG",   "Leu"),
    ("DIWIGE",   "Ile"),
]

def _match_a_motif(seq: str) -> str:
    """Match an A-domain protein sequence against known substrate motifs."""
    seq_up = seq.upper()
    for motif, aa in NRPS_A_MOTIFS:
        # Allow X as wildcard
        import re
        pattern = motif.replace("X", ".")
        if re.search(pattern, seq_up):
            return aa
    return "Unknown AA"


# ──────────────────────────────────────────────────────────────────────────────
# Step 1 – Load & merge Phase 3 data
# ──────────────────────────────────────────────────────────────────────────────

def load_data() -> list[dict]:
    """
    Load and merge virtual_bgcs, novelty_scores, and bgc_results into a
    unified list of enriched BGC entries.

    Each entry:
        vbgc_id, bgc_class, domain_architecture, novelty_score,
        member_regions, genes (list of gene dicts with protein_seq + domains)
    """
    print("\n── Step 1: Load Phase 3 Data ──────────────────────────────────────")

    vbgcs       = json.loads(VIRTUAL_BGCS_JSON.read_text())
    novelty_raw = json.loads(NOVELTY_SCORES_JSON.read_text())
    bgc_results = json.loads(BGC_RESULTS_JSON.read_text())

    # Index novelty scores by virtual BGC id
    novelty_map: dict[str, float] = {
        ns["virtual_bgc_id"]: ns["novelty_score"] for ns in novelty_raw
    }

    # Index bgc_results by region_id
    region_map: dict[str, dict] = {r["region_id"]: r for r in bgc_results}

    unified = []
    for vbgc in vbgcs:
        vid = vbgc["virtual_bgc_id"]

        # Collect all genes across member regions
        all_genes: list[dict] = []
        for rid in vbgc.get("member_regions", []):
            region = region_map.get(rid, {})
            all_genes.extend(region.get("genes", []))

        unified.append({
            "vbgc_id":            vid,
            "bgc_class":          vbgc["bgc_class"],
            "domain_architecture": vbgc["domain_architecture"],
            "member_regions":     vbgc["member_regions"],
            "member_count":       vbgc["member_count"],
            "novelty_score":      novelty_map.get(vid, 0.0),
            "genes":              all_genes,
        })

    print(f"  Loaded {len(vbgcs)} virtual BGCs")
    print(f"  Novelty scores: {len(novelty_map)}")
    print(f"  BGC regions available: {len(bgc_results)}")
    print(f"  Total genes: {sum(len(e['genes']) for e in unified)}")
    return unified


# ──────────────────────────────────────────────────────────────────────────────
# Step 2 – NRPS Peptide Prediction
# ──────────────────────────────────────────────────────────────────────────────

def predict_nrps(entries: list[dict], output_dir: Path) -> list[dict]:
    """
    For BGCs with NRPS domains, identify A-domain modules and predict the
    substrate amino acid for each using motif matching.
    """
    print("\n── Step 2: NRPS Peptide Prediction ───────────────────────────────")

    predictions = []

    for entry in entries:
        arch = entry["domain_architecture"]
        has_nrps = any(d.startswith("NRPS_") for d in arch)
        if not has_nrps:
            continue

        # Collect A-domain genes
        a_domain_seqs: list[str] = []
        for gene in entry["genes"]:
            for dom in gene.get("domains", []):
                if dom.get("bgc_type") == "NRPS_A":
                    seq = gene.get("protein_seq", "")
                    if seq:
                        a_domain_seqs.append(seq)

        # Predict substrate for each A-domain
        substrates = [_match_a_motif(seq) for seq in a_domain_seqs]

        # If no A-domain sequences extracted, infer count from architecture
        if not substrates:
            n_a = arch.count("NRPS_A")
            substrates = ["Unknown AA"] * max(n_a, 1)

        # Build peptide string
        peptide = "-".join(substrates) if substrates else "Unknown"

        # Count core modules (C+A+T triplets)
        n_c = arch.count("NRPS_C")
        n_t = arch.count("NRPS_T")
        module_count = max(len(substrates), min(n_c, n_t) or 1)

        # Classify peptide type
        if len(substrates) >= 3:
            nrp_type = "cyclic peptide (predicted)"
        elif len(substrates) == 2:
            nrp_type = "dipeptide"
        else:
            nrp_type = "single module"

        has_te = "NRPS_TE" in arch
        cyclization = "cyclized (TE domain)" if has_te else "linear"

        predictions.append({
            "vbgc_id":           entry["vbgc_id"],
            "bgc_class":         entry["bgc_class"],
            "novelty_score":     entry["novelty_score"],
            "nrps_modules":      module_count,
            "a_domain_count":    len(substrates),
            "predicted_substrates": substrates,
            "predicted_peptide": peptide,
            "peptide_type":      nrp_type,
            "cyclization":       cyclization,
            "predicted_metabolite": f"NRP: {peptide}",
        })

    out_path = output_dir / "nrps_predictions.json"
    with open(out_path, "w") as fh:
        json.dump(predictions, fh, indent=2)

    print(f"  {len(predictions)} NRPS BGCs → {out_path}")
    for p in predictions:
        print(f"    {p['vbgc_id']} → {p['predicted_peptide']} ({p['cyclization']})")
    return predictions


# ──────────────────────────────────────────────────────────────────────────────
# Step 3 – PKS Polyketide Prediction
# ──────────────────────────────────────────────────────────────────────────────

def predict_pks(entries: list[dict], output_dir: Path) -> list[dict]:
    """
    Predict PKS polyketide backbone based on reduction domains present
    per KS module.
    """
    print("\n── Step 3: PKS Polyketide Prediction ──────────────────────────────")

    predictions = []

    for entry in entries:
        arch = entry["domain_architecture"]
        has_pks = any(d.startswith("PKS_") for d in arch)
        if not has_pks:
            continue

        n_ks = arch.count("PKS_KS")
        n_at = arch.count("PKS_AT")
        n_kr = arch.count("PKS_KR")
        n_dh = arch.count("PKS_DH")
        n_er = arch.count("PKS_ER")
        n_te = arch.count("PKS_TE")

        if n_ks == 0:
            continue

        # Reduction state per module (majority rule from domain counts)
        if n_er > 0 and n_dh > 0 and n_kr > 0:
            reduction_state = "fully reduced (saturated chain)"
            functional_group = "saturated"
        elif n_dh > 0 and n_kr > 0:
            reduction_state = "dehydrated (double bond)"
            functional_group = "enoyl"
        elif n_kr > 0:
            reduction_state = "partially reduced (β-hydroxyl)"
            functional_group = "hydroxyl"
        else:
            reduction_state = "unreduced (β-keto)"
            functional_group = "keto"

        # Chain length estimate: each KS module adds 2 carbons from malonyl-CoA
        # starter unit typically adds 2 carbons
        chain_length = (n_ks * 2) + 2
        chain_label  = f"C{chain_length}"

        # Starter unit prediction from AT domains
        # Simple heuristic: if AT present, assume typical malonyl-CoA extension
        starter = "acetyl-CoA (C2)"

        release_mech = "thioesterase (macrolactonization)" if n_te else "reductive release"

        predictions.append({
            "vbgc_id":           entry["vbgc_id"],
            "bgc_class":         entry["bgc_class"],
            "novelty_score":     entry["novelty_score"],
            "ks_modules":        n_ks,
            "chain_length_C":    chain_length,
            "chain_label":       chain_label,
            "starter_unit":      starter,
            "reduction_state":   reduction_state,
            "functional_group":  functional_group,
            "release_mechanism": release_mech,
            "domain_composition": {
                "KS": n_ks, "AT": n_at, "KR": n_kr,
                "DH": n_dh, "ER": n_er, "TE": n_te,
            },
            "predicted_metabolite": f"{chain_label} polyketide ({functional_group})",
        })

    out_path = output_dir / "pks_predictions.json"
    with open(out_path, "w") as fh:
        json.dump(predictions, fh, indent=2)

    print(f"  {len(predictions)} PKS BGCs → {out_path}")
    for p in predictions:
        print(f"    {p['vbgc_id']} → {p['chain_label']} {p['reduction_state']}")
    return predictions


# ──────────────────────────────────────────────────────────────────────────────
# Step 4 – Hybrid Pathway Detection
# ──────────────────────────────────────────────────────────────────────────────

def predict_hybrid(entries: list[dict],
                   pks_preds: list[dict],
                   nrps_preds: list[dict],
                   output_dir: Path) -> list[dict]:
    """
    Identify BGCs containing both PKS and NRPS machinery and predict
    the hybrid polyketide–peptide product.
    """
    print("\n── Step 4: Hybrid Pathway Detection ───────────────────────────────")

    pks_ids  = {p["vbgc_id"]: p for p in pks_preds}
    nrps_ids = {p["vbgc_id"]: p for p in nrps_preds}

    predictions = []

    for entry in entries:
        vid  = entry["vbgc_id"]
        arch = entry["domain_architecture"]

        has_pks  = any(d.startswith("PKS_")  for d in arch)
        has_nrps = any(d.startswith("NRPS_") for d in arch)

        if not (has_pks and has_nrps):
            continue

        pks_part  = pks_ids.get(vid, {})
        nrps_part = nrps_ids.get(vid, {})

        chain    = pks_part.get("chain_label",       "PKS chain")
        peptide  = nrps_part.get("predicted_peptide", "peptide")
        red      = pks_part.get("functional_group",  "")

        # Junction type: PKS-first or NRPS-first
        pks_ks_pos  = next((i for i, d in enumerate(arch) if d == "PKS_KS"),  999)
        nrps_c_pos  = next((i for i, d in enumerate(arch) if d == "NRPS_C"),  999)
        order = "PKS → NRPS" if pks_ks_pos < nrps_c_pos else "NRPS → PKS"

        metabolite = (f"{chain} polyketide chain ({red}) + {peptide} peptide tail"
                      if order == "PKS → NRPS"
                      else f"{peptide} peptide head + {chain} polyketide extension")

        predictions.append({
            "vbgc_id":           vid,
            "bgc_class":         entry["bgc_class"],
            "novelty_score":     entry["novelty_score"],
            "order":             order,
            "pks_chain":         chain,
            "nrps_peptide":      peptide,
            "predicted_metabolite": metabolite,
            "hybrid_type":       "PKS-NRPS hybrid",
        })

    out_path = output_dir / "hybrid_predictions.json"
    with open(out_path, "w") as fh:
        json.dump(predictions, fh, indent=2)

    print(f"  {len(predictions)} hybrid BGCs → {out_path}")
    for p in predictions:
        print(f"    {p['vbgc_id']} ({p['order']}) → {p['predicted_metabolite'][:60]}")
    return predictions


# ──────────────────────────────────────────────────────────────────────────────
# Step 5 – Molecular Property Estimation
# ──────────────────────────────────────────────────────────────────────────────

# Lipinski-style class thresholds (rule-of-five inspired, heuristic for NPs)
def estimate_properties(entries: list[dict],
                        pks_preds: list[dict],
                        nrps_preds: list[dict],
                        output_dir: Path) -> list[dict]:
    """
    Estimate molecular properties using heuristic rules derived from
    domain composition and predicted structure.
    """
    print("\n── Step 5: Molecular Property Estimation ──────────────────────────")

    pks_map  = {p["vbgc_id"]: p for p in pks_preds}
    nrps_map = {p["vbgc_id"]: p for p in nrps_preds}

    properties = []

    for entry in entries:
        vid  = entry["vbgc_id"]
        arch = entry["domain_architecture"]
        cls  = entry["bgc_class"]

        pks  = pks_map.get(vid)
        nrps = nrps_map.get(vid)

        # ── Approximate Molecular Weight ─────────────────────────────────
        mw = 100.0  # base
        if pks:
            cl = pks["chain_length_C"]
            mw += cl * 14   # ~14 Da per CH2
            # Reduction state adjustment
            if "saturated"   in pks["functional_group"]: mw += cl * 2
            elif "hydroxyl"  in pks["functional_group"]: mw += 16
            elif "enoyl"     in pks["functional_group"]: mw -= 2
        if nrps:
            # Average amino acid MW ~111 Da
            mw += nrps["a_domain_count"] * 111
        if not pks and not nrps:
            # Estimate from gene count
            mw += len(entry["genes"]) * 50

        # Tailoring adjustments
        tailoring = sum(1 for d in arch if d in
                        {"Methyltransf", "Glycosyltransf", "Oxygenase",
                         "Reductase", "Hydroxylase", "P450"})
        mw += tailoring * 30   # glycosylation / methylation add mass

        # ── Lipophilicity (log P proxy) ──────────────────────────────────
        logp = 1.0
        if pks:
            logp += pks["ks_modules"] * 0.5    # each KS adds hydrophobicity
            if "saturated" in pks["functional_group"]: logp += 1.5
            if "keto"      in pks["functional_group"]: logp -= 0.5
        if nrps:
            logp -= nrps["a_domain_count"] * 0.3   # peptides are more polar
        logp += tailoring * 0.2
        logp = max(-2.0, min(logp, 7.0))  # clamp

        # ── Biosynthetic Complexity ──────────────────────────────────────
        domain_diversity = len(set(arch))
        module_count     = len(entry.get("member_regions", []))
        complexity = (
            domain_diversity * 1.5
            + tailoring * 2.0
            + module_count * 0.5
        )

        # ── Lipinski / natural-product druglikeness ──────────────────────
        # Natural products often violate Ro5, so we use relaxed criteria
        mw_ok   = mw < 1000
        logp_ok = logp < 5
        # Estimated H-bond donors/acceptors
        hbd = max(0, nrps["a_domain_count"] if nrps else 1)
        hba = hbd + tailoring
        np_druglike = mw_ok and logp_ok and hbd <= 5 and hba <= 10

        # Predicted compound class
        if "RiPP" in cls:           compound_class = "ribosomally synthesized peptide"
        elif "NRPS" in cls and pks: compound_class = "hybrid polyketide-NRP"
        elif "NRPS" in cls:         compound_class = "non-ribosomal peptide"
        elif "PKS"  in cls:         compound_class = "polyketide"
        elif "Terpene" in cls:      compound_class = "terpenoid"
        elif "Beta-lactam" in cls:  compound_class = "beta-lactam antibiotic"
        elif "Siderophore" in cls:  compound_class = "siderophore"
        elif "Alkaloid" in cls:     compound_class = "alkaloid"
        else:                       compound_class = "unknown natural product"

        properties.append({
            "vbgc_id":             vid,
            "bgc_class":           cls,
            "compound_class":      compound_class,
            "est_mol_weight_Da":   round(mw, 1),
            "est_logP":            round(logp, 2),
            "biosynthetic_complexity": round(complexity, 2),
            "domain_diversity":    domain_diversity,
            "tailoring_enzymes":   tailoring,
            "np_druglike":         np_druglike,
            "novelty_score":       entry["novelty_score"],
        })

    out_path = output_dir / "metabolite_properties.json"
    with open(out_path, "w") as fh:
        json.dump(properties, fh, indent=2)

    print(f"  Estimated properties for {len(properties)} virtual BGCs → {out_path}")
    return properties


# ──────────────────────────────────────────────────────────────────────────────
# Step 6 – Drug Potential Ranking (QML Module)
# ──────────────────────────────────────────────────────────────────────────────

def _build_feature_matrix(entries: list[dict],
                           properties: list[dict]) -> tuple[np.ndarray, list[str]]:
    """
    Build a feature matrix for QML from the unified entries + properties.
    Features: novelty_score, domain_diversity, tailoring_enzyme_count,
              module_count, cluster_size (gene count), bgc_class_encoded
    """
    prop_map = {p["vbgc_id"]: p for p in properties}

    CLASS_ENCODE = {
        "Type I PKS":            0,
        "Type I PKS (reducing)": 1,
        "NRPS":                  2,
        "PKS-NRPS Hybrid":       3,
        "Multi-class Hybrid":    3,
        "Terpene":               4,
        "Terpene (synthase)":    4,
        "RiPP":                  5,
        "Beta-lactam":           6,
        "Siderophore":           7,
        "Alkaloid":              8,
        "Unknown":               9,
    }

    rows = []
    ids  = []
    for entry in entries:
        vid  = entry["vbgc_id"]
        prop = prop_map.get(vid, {})
        ids.append(vid)
        rows.append([
            entry["novelty_score"],
            prop.get("domain_diversity",       len(set(entry["domain_architecture"]))),
            prop.get("tailoring_enzymes",      0),
            entry["member_count"],
            len(entry["genes"]),
            CLASS_ENCODE.get(entry["bgc_class"], 9),
        ])

    X = np.array(rows, dtype=float)

    # Normalize each feature to [0, 1]
    for col in range(X.shape[1]):
        col_min, col_max = X[:, col].min(), X[:, col].max()
        if col_max > col_min:
            X[:, col] = (X[:, col] - col_min) / (col_max - col_min)
        else:
            X[:, col] = 0.5  # constant feature → neutral

    return X, ids


def _qml_score(X: np.ndarray) -> np.ndarray:
    """
    Variational Quantum Classifier (VQC) used in unsupervised mode:
    compute a quantum embedding distance to a reference state |0⟩⊗n
    as a proxy for drug-discovery potential.

    Architecture:
        n_qubits = 4
        Angle embedding of first 4 features (π × feature)
        3 layers of StronglyEntanglingLayers
        Expectation value of PauliZ on wires 0..3 → drug score
    """
    try:
        import pennylane as qml

        N_QUBITS = 4
        N_LAYERS = 3

        dev = qml.device("default.qubit", wires=N_QUBITS)

        # Initialize trainable weights (random, fixed seed for reproducibility)
        rng     = np.random.default_rng(42)
        weights = rng.uniform(0, np.pi,
                              qml.StronglyEntanglingLayers.shape(N_LAYERS, N_QUBITS))
        weights = np.array(weights)

        @qml.qnode(dev)
        def circuit(features):
            qml.AngleEmbedding(features[:N_QUBITS] * np.pi,
                               wires=range(N_QUBITS),
                               rotation="Y")
            qml.StronglyEntanglingLayers(weights, wires=range(N_QUBITS))
            return [qml.expval(qml.PauliZ(w)) for w in range(N_QUBITS)]

        scores = []
        for feat_vec in X:
            exp_vals = circuit(feat_vec)
            # Map from [-1,1]^4 to [0,1]: mean of (1+expval)/2
            score = float(np.mean([(1 + v) / 2 for v in exp_vals]))
            scores.append(score)

        method = "QML (VQC / AngleEmbedding + StronglyEntanglingLayers)"
        print(f"  QML backend: PennyLane default.qubit | "
              f"{N_QUBITS} qubits | {N_LAYERS} layers")
        return np.array(scores), method

    except Exception as exc:
        print(f"  ⚠ QML unavailable ({exc}), using classical fallback.")
        # Classical fallback: weighted sum of normalized features
        # weights: novelty(0.35) + diversity(0.20) + tailoring(0.15)
        #          + modules(0.10) + genes(0.10) + class(0.10)
        w = np.array([0.35, 0.20, 0.15, 0.10, 0.10, 0.10])
        scores = X @ w
        # Normalize to [0,1]
        lo, hi = scores.min(), scores.max()
        if hi > lo:
            scores = (scores - lo) / (hi - lo)
        method = "Classical (weighted feature sum — PennyLane fallback)"
        return scores, method


def run_qml_classifier(entries: list[dict],
                       properties: list[dict],
                       output_dir: Path) -> list[dict]:
    """Run QML scoring and output per-BGC drug potential scores."""
    print("\n── Step 6: Drug Potential Ranking (QML) ───────────────────────────")

    X, ids = _build_feature_matrix(entries, properties)
    scores, method = _qml_score(X)

    qml_scores = []
    for vid, score in zip(ids, scores):
        qml_scores.append({
            "vbgc_id":            vid,
            "drug_potential_score": round(float(score), 4),
            "method":             method,
        })

    qml_scores.sort(key=lambda x: x["drug_potential_score"], reverse=True)

    out_path = output_dir / "qml_drug_scores.json"
    with open(out_path, "w") as fh:
        json.dump(qml_scores, fh, indent=2)

    print(f"  Scored {len(qml_scores)} BGCs using: {method}")
    print(f"  → {out_path}")
    return qml_scores


# ──────────────────────────────────────────────────────────────────────────────
# Step 7 – Final Candidate Ranking
# ──────────────────────────────────────────────────────────────────────────────

def rank_candidates(entries: list[dict],
                    properties: list[dict],
                    pks_preds: list[dict],
                    nrps_preds: list[dict],
                    hybrid_preds: list[dict],
                    qml_scores: list[dict],
                    output_dir: Path) -> list[dict]:
    """
    Combine novelty_score + drug_potential_score + metabolite_complexity into
    a final ranking score for each virtual BGC.

    final_score = novelty_score
                + drug_potential_score * 10   (scale to comparable range)
                + metabolite_complexity
    """
    print("\n── Step 7: Final Candidate Ranking ────────────────────────────────")

    # Build lookup maps
    prop_map   = {p["vbgc_id"]: p for p in properties}
    qml_map    = {q["vbgc_id"]: q["drug_potential_score"] for q in qml_scores}
    pks_map    = {p["vbgc_id"]: p["predicted_metabolite"] for p in pks_preds}
    nrps_map   = {p["vbgc_id"]: p["predicted_metabolite"] for p in nrps_preds}
    hybrid_map = {p["vbgc_id"]: p["predicted_metabolite"] for p in hybrid_preds}
    entry_map  = {e["vbgc_id"]: e for e in entries}

    ranking = []
    for entry in entries:
        vid  = entry["vbgc_id"]
        prop = prop_map.get(vid, {})

        novelty     = entry["novelty_score"]
        drug_score  = qml_map.get(vid, 0.0)
        complexity  = prop.get("biosynthetic_complexity", 0.0)

        final_score = novelty + drug_score * 10.0 + complexity

        # Best predicted metabolite description
        metabolite = (
            hybrid_map.get(vid)
            or pks_map.get(vid)
            or nrps_map.get(vid)
            or prop.get("compound_class", "unknown")
        )

        ranking.append({
            "rank":                  0,   # filled after sort
            "vbgc_id":               vid,
            "bgc_class":             entry["bgc_class"],
            "predicted_metabolite":  metabolite,
            "final_score":           round(final_score, 4),
            "novelty_score":         round(novelty, 4),
            "drug_potential_score":  round(drug_score, 4),
            "metabolite_complexity": round(complexity, 4),
            "est_mol_weight_Da":     prop.get("est_mol_weight_Da"),
            "est_logP":              prop.get("est_logP"),
            "np_druglike":           prop.get("np_druglike", False),
            "member_regions":        entry["member_regions"],
        })

    ranking.sort(key=lambda x: x["final_score"], reverse=True)
    for i, r in enumerate(ranking, 1):
        r["rank"] = i

    out_path = output_dir / "bgc_final_ranking.json"
    with open(out_path, "w") as fh:
        json.dump(ranking, fh, indent=2)

    print(f"  Ranked {len(ranking)} virtual BGCs → {out_path}")

    # ── Print top-10 summary ─────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  Top Drug Candidates")
    print("=" * 72)
    for r in ranking[:10]:
        met = r["predicted_metabolite"]
        if len(met) > 55:
            met = met[:52] + "..."
        print(f"\n  {r['rank']:>2}  {r['vbgc_id']}")
        print(f"      Class  : {r['bgc_class']}")
        print(f"      Product: {met}")
        print(f"      Score  : {r['final_score']:.4f}  "
              f"(novelty={r['novelty_score']:.2f}  "
              f"drug={r['drug_potential_score']:.2f}  "
              f"complexity={r['metabolite_complexity']:.2f})")
        print(f"      MW ~{r['est_mol_weight_Da']} Da  logP ~{r['est_logP']}  "
              f"druglike={r['np_druglike']}")

    return ranking


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 72)
    print("  Phase 4: Metabolite Prediction and Drug-Discovery Ranking")
    print("=" * 72)

    for path in (VIRTUAL_BGCS_JSON, NOVELTY_SCORES_JSON, BGC_RESULTS_JSON):
        if not path.exists():
            print(f"\n❌ Required input not found: {path}")
            return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nOutputs → {OUTPUT_DIR}/")

    # Step 1
    entries = load_data()

    # Steps 2-4
    nrps_preds   = predict_nrps(entries,   OUTPUT_DIR)
    pks_preds    = predict_pks(entries,    OUTPUT_DIR)
    hybrid_preds = predict_hybrid(entries, pks_preds, nrps_preds, OUTPUT_DIR)

    # Step 5
    properties = estimate_properties(entries, pks_preds, nrps_preds, OUTPUT_DIR)

    # Step 6
    qml_scores = run_qml_classifier(entries, properties, OUTPUT_DIR)

    # Step 7
    ranking = rank_candidates(entries, properties, pks_preds, nrps_preds,
                              hybrid_preds, qml_scores, OUTPUT_DIR)

    # ── File manifest ────────────────────────────────────────────────────
    output_files = [
        OUTPUT_DIR / "nrps_predictions.json",
        OUTPUT_DIR / "pks_predictions.json",
        OUTPUT_DIR / "hybrid_predictions.json",
        OUTPUT_DIR / "metabolite_properties.json",
        OUTPUT_DIR / "qml_drug_scores.json",
        OUTPUT_DIR / "bgc_final_ranking.json",
    ]
    print("\n" + "=" * 72)
    print("  Phase 4 Complete")
    print("=" * 72)
    print("\nOutput files:")
    all_ok = True
    for f in output_files:
        status = "✅" if f.exists() else "❌"
        size   = f"{f.stat().st_size:,} bytes" if f.exists() else "MISSING"
        print(f"  {status}  {f.name:<35}  {size}")
        if not f.exists():
            all_ok = False

    if not all_ok:
        print("\n⚠  Some output files are missing.")
        return 1

    print("\n  Pipeline:")
    print("    DNA")
    print("    ↓  AI detection (Phase 1)")
    print("    ↓  domain annotation (Phase 2)")
    print("    ↓  biosynthetic architecture reconstruction (Phase 3)")
    print("    ↓  metabolite prediction (Phase 4)")
    print("    ↓  quantum drug discovery ranking ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
