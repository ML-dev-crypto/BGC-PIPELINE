"""
VQC Ranking Module
==================
Trains a Variational Quantum Classifier (VQC) on MiBIG 4.0 BGCs and
scores the candidates produced by bgc_candidates.csv.

This is extracted from pipeline/phase6_qml_training.py and adapted to
operate on the per-run bgc_candidates.csv produced by classify_bgcs.py
rather than the full virtual-BGC set from Phase 3.

Public API
----------
    run_vqc_ranking(bgc_csv, domain_table_csv, mibig_dir, output_dir)
        → dict with keys:
            vqc_available   bool   – True if PennyLane was found
            vqc_accuracy    float  – real trained accuracy (or None)
            vqc_roc_auc     float  – real ROC-AUC (or None)
            candidates      list   – per-BGC dicts with quantum_score
            weights_path    str    – path to saved qml_model_weights.npy
            fallback_reason str    – set when VQC unavailable
"""

from __future__ import annotations

import csv
import json
import sys
import time
import warnings
from collections import Counter
from pathlib import Path
from typing import Optional

import numpy as np

warnings.filterwarnings("ignore")

# ── optional heavy deps — all failures are graceful ──────────────────────────
try:
    import pennylane as qml
    from pennylane import numpy as anp
    PENNYLANE_OK = True
except ImportError:
    PENNYLANE_OK = False

try:
    import torch
    _TORCH_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    TORCH_OK = True
except ImportError:
    TORCH_OK = False
    _TORCH_DEVICE = None

try:
    from sklearn.decomposition import PCA
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, roc_auc_score,
    )
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

try:
    from Bio import SeqIO
    BIO_OK = True
except ImportError:
    BIO_OK = False

# ── VQC hyper-parameters (match phase6_qml_training.py) ──────────────────────
N_QUBITS    = 6
N_LAYERS    = 3
EPOCHS      = 60
BATCH_SIZE  = 5
LR          = 0.02
PCA_COMPONENTS = N_QUBITS   # 20 raw features → 6 for quantum embedding (one per qubit)
QML_TRAIN_LIMIT = 250
QML_VAL_LIMIT   = 80

# ── MiBIG feature definition (identical to phase6) ───────────────────────────
FEATURE_DOMAINS = [
    "PKS_KS", "PKS_AT", "PP-binding",
    "mod_KS", "hyb_KS", "itr_KS",
    "AMP-binding", "Condensation",
    "p450",
    "Glycos_transf_1", "MGT",
    "adh_short", "ADH_zinc_N",
    "Abhydrolase_6",
    "RmlD_sub_bind",
]
STRUCT_FEATURES = ["cluster_length_kb", "module_count"]

# ── Three new biological features (Steps 4) ──────────────────────────────────
# domain_entropy      : Shannon entropy of domain-type distribution per BGC
#                       High entropy = diverse biosynthetic machinery = richer chemistry
# tailoring_count     : P450 + glycosyltransferase + methyltransferase hits
#                       Tailoring enzymes strongly predict drug-like activity
# resistance_count    : ABC transporter + efflux + self-resistance domain hits
#                       Resistance genes co-located with BGCs signal real bioactivity
BIO_EXTRA_FEATURES = ["domain_entropy", "tailoring_count", "resistance_count"]

ALL_FEATURES = FEATURE_DOMAINS + STRUCT_FEATURES + BIO_EXTRA_FEATURES  # 20 total
N_FEATURES   = len(ALL_FEATURES)

# Domain sets for new features
_TAILORING_DOMAINS = {
    # P450 hydroxylases
    "p450", "P450", "CYP", "Cyt_P450",
    # Glycosyltransferases
    "Glycos_transf_1", "Glycos_transf_2", "MGT", "Glycosyltransf",
    # Methyltransferases
    "Methyltransf_2", "Methyltransf_3", "Methyltransf_11",
    "AdoMet_MTase", "SAMT",
    # Halogenases
    "Trp_halogenase", "Flavin_halogenase",
    # Oxidoreductases
    "FAD_binding_3", "Oxidored_FMN",
}

_RESISTANCE_DOMAINS = {
    # ABC transporters (self-resistance)
    "ABC_tran", "ABC_membrane", "ABC2_membrane",
    # Efflux pumps
    "MFS_1", "RND_mfp", "Drug_efflux",
    # Resistance methyltransferases
    "rRNA_methylase", "Methyltransf_6",
    # Beta-lactamase (self-resistance)
    "Beta-lactamase", "Abhydrolase_6",
    # Ribosome protection
    "TetM", "Tet_RPP",
}

ACTIVE_CLASSES   = {"PKS", "NRPS", "ribosomal", "terpene"}
INACTIVE_CLASSES = {"saccharide", "other"}
KNOWN_ACTIVE_STEMS = {
    "antibiotic", "antimicrobial", "antifungal", "anticancer",
    "antitumor", "cytotoxic", "antiviral", "herbicidal",
}

# Crosswalk from domain_table domain_type → FEATURE_DOMAINS names
# domain_table column "domain_type" uses values like: PKS_KS, PKS_AT,
# ACP, A, Condensation, P450, MT, NAD, Terpene_synth, OTHER, …
_DOMAIN_CROSSWALK: dict[str, list[str]] = {
    "PKS_KS":          ["PKS_KS", "mod_KS", "hyb_KS", "itr_KS"],
    "PKS_AT":          ["PKS_AT"],
    "ACP":             ["PP-binding"],
    "A":               ["AMP-binding"],
    "Condensation":    ["Condensation"],
    "P450":            ["p450"],
    "MT":              ["MGT"],
    "Terpene_synth":   ["RmlD_sub_bind"],  # best available proxy
    "NAD":             ["adh_short", "ADH_zinc_N"],
    "BetaLactam":      ["Abhydrolase_6"],
    "Glycosyltransf":  ["Glycos_transf_1"],
}


# ─────────────────────────────────────────────────────────────────────────────
# MiBIG parsing (identical to phase6)
# ─────────────────────────────────────────────────────────────────────────────

def _label_from_mibig(label_str: str, comment: str) -> int:
    parts = {p.strip().lower() for p in label_str.split(",")}
    if parts & {a.lower() for a in ACTIVE_CLASSES}:
        return 1
    if parts & {i.lower() for i in INACTIVE_CLASSES}:
        return 0
    comment_lower = comment.lower()
    if any(kw in comment_lower for kw in KNOWN_ACTIVE_STEMS):
        return 1
    return 0


def _count_modules(sec_domains: list[str]) -> int:
    ks_types = {"PKS_KS", "mod_KS", "hyb_KS", "itr_KS", "tra_KS"}
    a_types  = {"AMP-binding"}
    return sum(1 for d in sec_domains if d in ks_types) + \
           sum(1 for d in sec_domains if d in a_types)


def _domain_entropy(sec_domains: list[str]) -> float:
    """
    Shannon entropy of domain-type distribution.
    H = -Σ p_i * log2(p_i) over unique domain types.
    High entropy → diverse biosynthetic machinery → richer potential chemistry.
    Empty domain list → 0.0.
    """
    if not sec_domains:
        return 0.0
    counts = Counter(sec_domains)
    total  = float(len(sec_domains))
    return float(-sum(
        (c / total) * np.log2(c / total)
        for c in counts.values() if c > 0
    ))


def _tailoring_count(sec_domains: list[str]) -> float:
    """
    Count of tailoring enzyme domains (P450, glycosyltransferases,
    methyltransferases, halogenases, oxidoreductases).
    Tailoring enzymes are strong predictors of drug-like bioactivity.
    """
    return float(sum(1 for d in sec_domains if d in _TAILORING_DOMAINS))


def _resistance_count(sec_domains: list[str]) -> float:
    """
    Count of self-resistance gene domains (ABC transporters, efflux pumps,
    resistance methyltransferases, beta-lactamases).
    Co-located resistance genes strongly signal genuine bioactive BGCs.
    """
    return float(sum(1 for d in sec_domains if d in _RESISTANCE_DOMAINS))


def _parse_mibig(gbk_dir: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Parse MiBIG GBKs → feature matrix, labels, ids."""
    if not BIO_OK:
        raise ImportError("biopython required for MiBIG parsing")

    gbks = sorted(gbk_dir.glob("*.gbk"))
    print(f"  [VQC] Parsing {len(gbks)} MiBIG GBKs for training...")

    X_rows, y, ids = [], [], []
    skipped = 0

    for gbk in gbks:
        try:
            rec = next(SeqIO.parse(gbk, "genbank"))
        except Exception:
            skipped += 1
            continue

        label_str = "other"
        for feat in rec.features:
            if feat.type == "subregion":
                label_str = feat.qualifiers.get("label", ["other"])[0]
                break

        comment  = rec.annotations.get("comment", "")
        activity = _label_from_mibig(label_str, comment)

        sec_domains: list[str] = []
        for feat in rec.features:
            if feat.type != "CDS":
                continue
            for smd in feat.qualifiers.get("sec_met_domain", []):
                sec_domains.append(smd.split(" ")[0])

        dc  = Counter(sec_domains)
        row = [float(dc.get(d, 0)) for d in FEATURE_DOMAINS]
        row.append(len(rec) / 1000.0)
        row.append(float(_count_modules(sec_domains)))

        # New biological features
        row.append(_domain_entropy(sec_domains))
        row.append(_tailoring_count(sec_domains))
        row.append(_resistance_count(sec_domains))

        X_rows.append(row)
        y.append(activity)
        ids.append(gbk.stem)

    if skipped:
        print(f"  [VQC] ⚠  {skipped} GBKs skipped")

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y,      dtype=np.int32)
    print(f"  [VQC] Training set: {len(ids)} BGCs  "
          f"active={y.sum()}  inactive={len(y) - y.sum()}")
    return X, y, ids


# ─────────────────────────────────────────────────────────────────────────────
# Feature extraction from bgc_candidates.csv + domain_table.csv
# ─────────────────────────────────────────────────────────────────────────────

def _features_from_csv(
    bgc_csv: Path,
    domain_table_csv: Path,
) -> tuple[list[str], np.ndarray]:
    """
    Build 20-feature vectors for each candidate in bgc_candidates.csv.

    Returns (region_ids, X) where X has shape (n_candidates, N_FEATURES).
    """
    # Load domain table: region_id → list of domain_types
    region_domains: dict[str, list[str]] = {}
    if domain_table_csv.exists():
        with open(domain_table_csv, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                rid = row.get("region_id", row.get("query_name", ""))
                dt  = row.get("domain_type", "OTHER")
                region_domains.setdefault(rid, []).append(dt)

    # Load candidate list
    region_ids: list[str] = []
    with open(bgc_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rid = row.get("region_id", "")
            if rid:
                region_ids.append(rid)

    if not region_ids:
        return [], np.zeros((0, N_FEATURES), dtype=np.float32)

    rows = []
    for rid in region_ids:
        raw_domains = region_domains.get(rid, [])

        # Map domain_type → FEATURE_DOMAIN counts using crosswalk
        feat_counts: dict[str, float] = {d: 0.0 for d in FEATURE_DOMAINS}
        for dt in raw_domains:
            for feat_name in _DOMAIN_CROSSWALK.get(dt, []):
                if feat_name in feat_counts:
                    feat_counts[feat_name] += 1.0

        row = [feat_counts[d] for d in FEATURE_DOMAINS]

        # Structural features: rough cluster size + module proxy
        n_domains = len(raw_domains)
        row.append(float(n_domains * 2.0))   # rough kb estimate
        row.append(float(sum(
            1 for dt in raw_domains if dt in ("PKS_KS", "A")
        )))

        # New biological features (crosswalk from domain_type to sec_met names)
        # domain_entropy over raw domain_type values
        row.append(_domain_entropy(raw_domains))
        # tailoring: P450, MT, Glycosyltransf map to tailoring domains
        tailoring_proxy = {"P450", "MT", "Glycosyltransf", "Glycos_transf_1"}
        row.append(float(sum(1 for dt in raw_domains if dt in tailoring_proxy)))
        # resistance: ABC transporter, MFS efflux proxy
        resistance_proxy = {"ABC", "MFS", "BetaLactam", "Abhydrolase_6"}
        row.append(float(sum(1 for dt in raw_domains if dt in resistance_proxy)))

        rows.append(row)

    return region_ids, np.array(rows, dtype=np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation (identical to phase6)
# ─────────────────────────────────────────────────────────────────────────────

def _normalise(
    X_train: np.ndarray,
    X_val: np.ndarray,
) -> tuple[tuple[np.ndarray, np.ndarray], np.ndarray, np.ndarray]:
    mn  = X_train.min(axis=0)
    rng = X_train.max(axis=0) - mn
    rng[rng == 0] = 1.0

    def _scale(X: np.ndarray) -> np.ndarray:
        return 2.0 * ((X - mn) / rng) - 1.0

    return (_scale(X_train), _scale(X_val)), mn, rng


def _scale_with_stats(
    X: np.ndarray,
    mn: np.ndarray,
    rng: np.ndarray,
) -> np.ndarray:
    rng_safe = np.where(rng == 0, 1.0, rng)
    return 2.0 * ((X - mn) / rng_safe) - 1.0


# ─────────────────────────────────────────────────────────────────────────────
# VQC circuit (identical to phase6)
# ─────────────────────────────────────────────────────────────────────────────

def _best_pennylane_backend() -> str:
    """
    Auto-detect the fastest available PennyLane backend.
    Priority: lightning.gpu > lightning.qubit > default.qubit
    lightning.qubit is a C++ accelerated CPU simulator — 2-5× faster
    than default.qubit with no extra hardware required.
    """
    # lightning.gpu: requires pennylane-lightning-gpu + CUDA
    if TORCH_OK and torch.cuda.is_available():
        try:
            dev = qml.device("lightning.gpu", wires=2)
            # quick sanity check
            @qml.qnode(dev)
            def _t(x): return qml.expval(qml.PauliZ(0))
            _t(0.0)
            print(f"  [VQC] lightning.gpu available ✓ ({torch.cuda.get_device_name(0)})")
            return "lightning.gpu"
        except Exception:
            pass

    # lightning.qubit: C++ CPU kernel, no GPU needed
    try:
        dev = qml.device("lightning.qubit", wires=2)
        @qml.qnode(dev)
        def _t(x): return qml.expval(qml.PauliZ(0))
        _t(0.0)
        print("  [VQC] lightning.qubit available ✓ (C++ CPU kernel)")
        return "lightning.qubit"
    except Exception:
        pass

    print("  [VQC] Using default.qubit (install pennylane-lightning for 2-5× speedup)")
    return "default.qubit"


def _build_vqc(backend: str | None = None, n_qubits: int = N_QUBITS,
               n_layers: int = N_LAYERS):
    """Return (circuit, weights).  Prefers torch/GPU, falls back to autograd.
    Auto-detects the fastest available PennyLane backend if none specified.
    """
    if backend is None:
        backend = _best_pennylane_backend()

    use_torch = TORCH_OK and PENNYLANE_OK

    # lightning.gpu uses adjoint differentiation — backprop not supported
    diff_method = "adjoint" if backend == "lightning.gpu" else "backprop"
    # lightning.qubit supports backprop
    if backend == "lightning.qubit":
        diff_method = "best"

    if use_torch and backend != "lightning.gpu":
        dev = qml.device(backend, wires=n_qubits)

        @qml.qnode(dev, interface="torch", diff_method=diff_method)
        def circuit(weights, x):
            qml.templates.AngleEmbedding(
                x[:n_qubits], wires=range(n_qubits), rotation="Y")
            qml.templates.StronglyEntanglingLayers(
                weights, wires=range(n_qubits))
            return qml.expval(qml.PauliZ(0))

        shape = qml.templates.StronglyEntanglingLayers.shape(
            n_layers=n_layers, n_wires=n_qubits)
        rng_np = np.random.default_rng(42)
        init   = torch.tensor(
            rng_np.uniform(-np.pi / 4, np.pi / 4, shape),
            dtype=torch.float64, device=_TORCH_DEVICE,
        )
        weights = torch.nn.Parameter(init)
        device_str = str(_TORCH_DEVICE)
        print(f"  [VQC] Backend: {backend} | PyTorch ({device_str}) | "
              f"diff={diff_method} | {n_qubits}q × {n_layers}L")

    elif use_torch and backend == "lightning.gpu":
        # lightning.gpu uses its own interface
        dev = qml.device(backend, wires=n_qubits)

        @qml.qnode(dev, interface="torch", diff_method="adjoint")
        def circuit(weights, x):
            qml.templates.AngleEmbedding(
                x[:n_qubits], wires=range(n_qubits), rotation="Y")
            qml.templates.StronglyEntanglingLayers(
                weights, wires=range(n_qubits))
            return qml.expval(qml.PauliZ(0))

        shape   = qml.templates.StronglyEntanglingLayers.shape(
            n_layers=n_layers, n_wires=n_qubits)
        rng_np  = np.random.default_rng(42)
        init    = torch.tensor(
            rng_np.uniform(-np.pi / 4, np.pi / 4, shape),
            dtype=torch.float64, device=_TORCH_DEVICE)
        weights = torch.nn.Parameter(init)
        print(f"  [VQC] Backend: lightning.gpu | {n_qubits}q × {n_layers}L")

    else:
        dev = qml.device(backend, wires=n_qubits)

        @qml.qnode(dev, interface="autograd")
        def circuit(weights, x):
            qml.templates.AngleEmbedding(
                x[:n_qubits], wires=range(n_qubits), rotation="Y")
            qml.templates.StronglyEntanglingLayers(
                weights, wires=range(n_qubits))
            return qml.expval(qml.PauliZ(0))

        shape   = qml.templates.StronglyEntanglingLayers.shape(
            n_layers=n_layers, n_wires=n_qubits)
        rng_np  = np.random.default_rng(42)
        weights = anp.array(
            rng_np.uniform(-np.pi / 4, np.pi / 4, shape),
            requires_grad=True,
        )
        print(f"  [VQC] Backend: {backend} | autograd CPU | "
              f"{n_qubits}q × {n_layers}L")

    return circuit, weights


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-float(x)))


def _vqc_probs_torch(circuit, weights, X: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        X_t  = torch.tensor(X, dtype=torch.float64, device=_TORCH_DEVICE)
        raw  = torch.stack([circuit(weights, x) for x in X_t])
        return torch.sigmoid(raw).cpu().numpy()


def _bce(probs: np.ndarray, labels: np.ndarray) -> float:
    eps = 1e-7
    p   = np.clip(probs, eps, 1 - eps)
    return float(-np.mean(labels * np.log(p) + (1 - labels) * np.log(1 - p)))


# ─────────────────────────────────────────────────────────────────────────────
# Training loop (identical to phase6)
# ─────────────────────────────────────────────────────────────────────────────

def _train_vqc(circuit, weights,
               X_tr: np.ndarray, y_tr: np.ndarray,
               X_val: np.ndarray, y_val: np.ndarray):
    use_torch   = TORCH_OK and isinstance(weights, torch.nn.Parameter)
    n           = len(X_tr)
    rng         = np.random.default_rng(0)
    best_val    = float("inf")
    MAX_W       = 3.0

    n_pos = float(y_tr.sum())
    n_neg = float(n - n_pos)
    pos_w = min(n / (2.0 * n_pos), MAX_W) if n_pos > 0 else 1.0
    neg_w = min(n / (2.0 * n_neg), MAX_W) if n_neg > 0 else 1.0
    sw    = np.where(y_tr == 1, pos_w, neg_w).astype(np.float64)

    n_params = N_QUBITS * N_LAYERS * 3
    print(f"  [VQC] Training: {N_QUBITS}q × {N_LAYERS}L ({n_params} params)  "
          f"{EPOCHS} epochs  batch={BATCH_SIZE}  lr={LR}")
    print(f"  [VQC] Class weights — active:{pos_w:.3f}  inactive:{neg_w:.3f}")

    train_losses: list[float] = []
    val_losses:   list[float] = []

    if use_torch:
        opt          = torch.optim.Adam([weights], lr=LR)
        best_weights = weights.data.clone()

        for epoch in range(1, EPOCHS + 1):
            idx        = rng.permutation(n)
            epoch_loss = 0.0
            n_batches  = 0

            weights.requires_grad_(True)
            for start in range(0, n, BATCH_SIZE):
                bidx = idx[start: start + BATCH_SIZE]
                X_b  = torch.tensor(X_tr[bidx],
                                    dtype=torch.float64, device=_TORCH_DEVICE)
                y_b  = torch.tensor(y_tr[bidx].astype(np.float64),
                                    dtype=torch.float64, device=_TORCH_DEVICE)
                sw_b = torch.tensor(sw[bidx],
                                    dtype=torch.float64, device=_TORCH_DEVICE)

                opt.zero_grad()
                raw  = torch.stack([circuit(weights, x) for x in X_b])
                prob = torch.sigmoid(raw)
                eps  = 1e-7
                p    = torch.clamp(prob, eps, 1.0 - eps)
                bce  = -(y_b * torch.log(p) + (1.0 - y_b) * torch.log(1.0 - p))
                loss = (sw_b * bce).mean()
                loss.backward()
                opt.step()

                epoch_loss += float(loss.item())
                n_batches  += 1

            tl = epoch_loss / max(n_batches, 1)
            vp = _vqc_probs_torch(circuit, weights, X_val)
            vl = _bce(vp, y_val.astype(np.float64))

            train_losses.append(tl)
            val_losses.append(vl)

            if vl < best_val:
                best_val     = vl
                best_weights = weights.data.clone()

            if epoch % 20 == 0 or epoch == 1:
                tp  = _vqc_probs_torch(circuit, weights, X_tr)
                ta  = float(np.mean((tp > 0.5) == y_tr))
                va  = float(np.mean((vp > 0.5) == y_val))
                print(f"  [VQC] Epoch {epoch:3d}/{EPOCHS}  "
                      f"train_loss={tl:.4f}  val_loss={vl:.4f}  "
                      f"train_acc={ta:.3f}  val_acc={va:.3f}")

        weights.data.copy_(best_weights)
        return weights, train_losses, val_losses

    else:   # autograd path
        opt          = qml.AdamOptimizer(stepsize=LR)
        best_weights = weights.copy()

        for epoch in range(1, EPOCHS + 1):
            idx        = rng.permutation(n)
            epoch_loss = 0.0
            n_batches  = 0

            for start in range(0, n, BATCH_SIZE):
                bidx = idx[start: start + BATCH_SIZE]
                X_b  = X_tr[bidx]
                y_b  = y_tr[bidx].astype(np.float64)
                sw_b = sw[bidx]

                def cost(w, _X=X_b, _y=y_b, _sw=sw_b):
                    raw  = anp.stack([circuit(w, x) for x in _X])
                    prob = 1.0 / (1.0 + anp.exp(-raw))
                    eps  = 1e-7
                    p    = anp.clip(prob, eps, 1.0 - eps)
                    bce  = -(_y * anp.log(p) + (1.0 - _y) * anp.log(1.0 - p))
                    return anp.mean(_sw * bce)

                weights, loss_val = opt.step_and_cost(cost, weights)
                epoch_loss += float(loss_val)
                n_batches  += 1

            tl = epoch_loss / max(n_batches, 1)
            vp = np.array([_sigmoid(circuit(weights, x)) for x in X_val])
            vl = _bce(vp, y_val.astype(np.float64))

            train_losses.append(tl)
            val_losses.append(vl)

            if vl < best_val:
                best_val     = vl
                best_weights = weights.copy()

            if epoch % 20 == 0 or epoch == 1:
                tp = np.array([_sigmoid(circuit(weights, x)) for x in X_tr])
                ta = float(np.mean((tp > 0.5) == y_tr))
                va = float(np.mean((vp > 0.5) == y_val))
                print(f"  [VQC] Epoch {epoch:3d}/{EPOCHS}  "
                      f"train_loss={tl:.4f}  val_loss={vl:.4f}  "
                      f"train_acc={ta:.3f}  val_acc={va:.3f}")

        return best_weights, train_losses, val_losses


def _evaluate_vqc(circuit, weights, X: np.ndarray, y: np.ndarray) -> dict:
    if TORCH_OK and isinstance(weights, torch.nn.Parameter):
        probs = _vqc_probs_torch(circuit, weights, X)
    else:
        probs = np.array([_sigmoid(circuit(weights, x)) for x in X])
    preds = (probs > 0.5).astype(int)
    return {
        "accuracy":  float(np.mean(preds == y)),
        "precision": float(precision_score(y, preds, zero_division=0)),
        "recall":    float(recall_score(y, preds, zero_division=0)),
        "roc_auc":   float(roc_auc_score(y, probs))
                     if len(np.unique(y)) > 1 else 0.0,
        "probs":     probs.tolist(),
    }


def _infer_vqc(circuit, weights, X: np.ndarray) -> list[float]:
    """Return per-sample drug-potential probabilities."""
    if TORCH_OK and isinstance(weights, torch.nn.Parameter):
        probs = _vqc_probs_torch(circuit, weights, X)
    else:
        probs = np.array([_sigmoid(circuit(weights, x)) for x in X])
    return [round(float(p), 4) for p in probs]


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_vqc_ranking(
    bgc_csv: str,
    domain_table_csv: str,
    mibig_dir: str,
    output_dir: str,
) -> dict:
    """
    Train VQC on MiBIG, score candidates in bgc_csv, write vqc_results.json.

    Parameters
    ----------
    bgc_csv          : path to bgc_candidates.csv from classify_bgcs.py
    domain_table_csv : path to domain_table.csv from parse_domains.py
    mibig_dir        : path to mibig_gbk_4.0/ directory
    output_dir       : directory to write vqc_results.json and weights

    Returns
    -------
    dict with keys: vqc_available, vqc_accuracy, vqc_roc_auc,
                    candidates, weights_path, fallback_reason
    """
    t0          = time.time()
    out_dir     = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bgc_csv_p   = Path(bgc_csv)
    dt_csv_p    = Path(domain_table_csv)
    mibig_dir_p = Path(mibig_dir)

    # ── Pre-flight checks ────────────────────────────────────────────────────
    if not PENNYLANE_OK:
        msg = "PennyLane not installed — pip install pennylane"
        print(f"  [VQC] ⚠  {msg}")
        return _fallback_result(bgc_csv_p, msg)

    if not SKLEARN_OK:
        msg = "scikit-learn not installed — pip install scikit-learn"
        print(f"  [VQC] ⚠  {msg}")
        return _fallback_result(bgc_csv_p, msg)

    if not BIO_OK:
        msg = "biopython not installed — pip install biopython"
        print(f"  [VQC] ⚠  {msg}")
        return _fallback_result(bgc_csv_p, msg)

    if not mibig_dir_p.exists():
        msg = f"MiBIG directory not found: {mibig_dir_p}"
        print(f"  [VQC] ⚠  {msg}")
        return _fallback_result(bgc_csv_p, msg)

    if not bgc_csv_p.exists() or bgc_csv_p.stat().st_size == 0:
        msg = f"bgc_candidates.csv missing or empty: {bgc_csv_p}"
        print(f"  [VQC] ⚠  {msg}")
        return _fallback_result(bgc_csv_p, msg)

    # ── Step 1: Extract candidate features ──────────────────────────────────
    print("  [VQC] Extracting features from bgc_candidates.csv ...")
    region_ids, X_cand = _features_from_csv(bgc_csv_p, dt_csv_p)

    if len(region_ids) == 0:
        msg = "No candidates in bgc_candidates.csv"
        print(f"  [VQC] ⚠  {msg}")
        return _fallback_result(bgc_csv_p, msg)

    print(f"  [VQC] {len(region_ids)} candidate(s) to score")

    # ── Step 2: Build MiBIG training set ────────────────────────────────────
    try:
        X_mibig, y_mibig, _ = _parse_mibig(mibig_dir_p)
    except Exception as exc:
        msg = f"MiBIG parsing failed: {exc}"
        print(f"  [VQC] ⚠  {msg}")
        return _fallback_result(bgc_csv_p, msg)

    if len(X_mibig) < 20:
        msg = f"Too few MiBIG BGCs to train ({len(X_mibig)})"
        print(f"  [VQC] ⚠  {msg}")
        return _fallback_result(bgc_csv_p, msg)

    # ── Step 3: Train/val split ──────────────────────────────────────────────
    print("  [VQC] Splitting and preparing training data ...")
    X_tr_full, X_val, y_tr_full, y_val = train_test_split(
        X_mibig, y_mibig, test_size=0.15, random_state=42, stratify=y_mibig)

    if len(X_tr_full) > QML_TRAIN_LIMIT:
        X_qml_tr, _, y_qml_tr, _ = train_test_split(
            X_tr_full, y_tr_full,
            train_size=QML_TRAIN_LIMIT, random_state=42, stratify=y_tr_full)
    else:
        X_qml_tr, y_qml_tr = X_tr_full, y_tr_full

    if len(X_val) > QML_VAL_LIMIT:
        X_qml_val, _, y_qml_val, _ = train_test_split(
            X_val, y_val,
            train_size=QML_VAL_LIMIT, random_state=42, stratify=y_val)
    else:
        X_qml_val, y_qml_val = X_val, y_val

    # ── Step 4: PCA 17→6 + normalise ────────────────────────────────────────
    scaler_pca = StandardScaler()
    scaler_pca.fit(X_tr_full)

    pca = PCA(n_components=PCA_COMPONENTS, random_state=42)
    pca.fit(scaler_pca.transform(X_tr_full))
    pca_var = float(pca.explained_variance_ratio_.sum())
    print(f"  [VQC] PCA variance explained: {pca_var:.1%}")

    def _to_pca_norm(X: np.ndarray, mn: np.ndarray, rng: np.ndarray) -> np.ndarray:
        return _scale_with_stats(pca.transform(scaler_pca.transform(X)), mn, rng)

    (X_tr_n, X_val_n), mn_pca, rng_pca = _normalise(
        pca.transform(scaler_pca.transform(X_qml_tr)),
        pca.transform(scaler_pca.transform(X_qml_val)),
    )

    print(f"  [VQC] QML train: {len(X_qml_tr)}  val: {len(X_qml_val)}")
    print(f"  [VQC] Class balance: active={y_mibig.sum()}/{len(y_mibig)} "
          f"({100*y_mibig.mean():.1f}%)")

    # ── Step 5: Train VQC ────────────────────────────────────────────────────
    print("  [VQC] Building circuit ...")
    circuit, weights = _build_vqc()

    print("  [VQC] Training VQC on MiBIG BGCs ...")
    best_weights, train_losses, val_losses = _train_vqc(
        circuit, weights, X_tr_n, y_qml_tr, X_val_n, y_qml_val)

    # ── Step 6: Evaluate ─────────────────────────────────────────────────────
    print("  [VQC] Evaluating on validation set ...")
    metrics = _evaluate_vqc(circuit, best_weights, X_val_n, y_qml_val)
    print(f"  [VQC] ✓ acc={metrics['accuracy']:.3f}  "
          f"auc={metrics['roc_auc']:.3f}  "
          f"precision={metrics['precision']:.3f}  "
          f"recall={metrics['recall']:.3f}")

    # ── Step 7: Save weights ─────────────────────────────────────────────────
    wt_path = out_dir / "qml_model_weights.npy"
    if TORCH_OK and isinstance(best_weights, torch.nn.Parameter):
        wt_arr = best_weights.data.cpu().numpy()
    else:
        wt_arr = np.array(best_weights)
    np.save(wt_path, wt_arr)
    print(f"  [VQC] Weights saved → {wt_path}")

    # ── Step 8: Score candidates ─────────────────────────────────────────────
    print(f"  [VQC] Scoring {len(region_ids)} candidate(s) ...")
    X_cand_n = _to_pca_norm(X_cand, mn_pca, rng_pca)
    scores   = _infer_vqc(circuit, best_weights, X_cand_n)

    # ── Step 9: Load candidate metadata and merge scores ────────────────────
    candidates: list[dict] = []
    with open(bgc_csv_p, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows   = list(reader)

    score_map = dict(zip(region_ids, scores))
    for row in rows:
        rid = row.get("region_id", "")
        qs  = score_map.get(rid, 0.5)  # default 0.5 if region not in map
        candidates.append({
            "region_id":        rid,
            "predicted_type":   row.get("predicted_type", "unknown"),
            "confidence_score": _safe_float(row.get("confidence_score")),
            "confidence_level": row.get("confidence_level", "unknown"),
            "completeness":     row.get("completeness", "unknown"),
            "quantum_score":    qs,
            # composite: 0.6 × novelty proxy (confidence) + 0.4 × QML
            "final_score": round(
                0.6 * _safe_float(row.get("confidence_score")) + 0.4 * qs, 4),
        })

    candidates.sort(key=lambda c: -c["final_score"])

    # ── Step 10: Persist vqc_results.json ────────────────────────────────────
    elapsed = round(time.time() - t0, 2)
    result  = {
        "vqc_available":   True,
        "vqc_accuracy":    round(metrics["accuracy"],  4),
        "vqc_roc_auc":     round(metrics["roc_auc"],   4),
        "vqc_precision":   round(metrics["precision"], 4),
        "vqc_recall":      round(metrics["recall"],    4),
        "pca_variance":    round(pca_var, 4),
        "train_samples":   int(len(X_qml_tr)),
        "val_samples":     int(len(X_qml_val)),
        "architecture":    f"{N_QUBITS}q × {N_LAYERS}L StronglyEntanglingLayers",
        "epochs":          EPOCHS,
        "mibig_bgcs_used": int(len(X_mibig)),
        "training_time_s": elapsed,
        "weights_path":    str(wt_path),
        "fallback_reason": None,
        "candidates":      candidates,
        "train_losses":    [round(float(l), 6) for l in (train_losses or [])],
        "val_losses":      [round(float(l), 6) for l in (val_losses   or [])],
    }

    vqc_out = out_dir / "vqc_results.json"
    with open(vqc_out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    print(f"  [VQC] Results saved → {vqc_out}")
    print(f"  [VQC] Done in {elapsed}s")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _fallback_result(bgc_csv_p: Path, reason: str) -> dict:
    """
    Return a graceful fallback result when VQC cannot run.
    Scores every candidate with quantum_score=None and vqc_accuracy=None.
    """
    candidates: list[dict] = []
    if bgc_csv_p.exists():
        try:
            with open(bgc_csv_p, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    rid = row.get("region_id", "")
                    if rid:
                        candidates.append({
                            "region_id":        rid,
                            "predicted_type":   row.get("predicted_type", "unknown"),
                            "confidence_score": _safe_float(
                                                    row.get("confidence_score")),
                            "confidence_level": row.get("confidence_level", "unknown"),
                            "completeness":     row.get("completeness", "unknown"),
                            "quantum_score":    None,
                            "final_score":      _safe_float(
                                                    row.get("confidence_score")),
                        })
        except Exception:
            pass

    return {
        "vqc_available":   False,
        "vqc_accuracy":    None,
        "vqc_roc_auc":     None,
        "vqc_precision":   None,
        "vqc_recall":      None,
        "pca_variance":    None,
        "train_samples":   0,
        "val_samples":     0,
        "architecture":    f"{N_QUBITS}q × {N_LAYERS}L StronglyEntanglingLayers",
        "epochs":          EPOCHS,
        "mibig_bgcs_used": 0,
        "training_time_s": 0.0,
        "weights_path":    None,
        "fallback_reason": reason,
        "candidates":      candidates,
        "train_losses":    [],
        "val_losses":      [],
    }
