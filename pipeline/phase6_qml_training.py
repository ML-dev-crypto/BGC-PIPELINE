"""
Phase 6 — Trained Quantum Machine Learning Drug-Potential Predictor
====================================================================
Trains a Variational Quantum Classifier (VQC) on 2636 MiBIG BGCs and
applies the trained model to rank the 14 discovered virtual BGCs.

Steps
-----
1. Parse all MiBIG GBKs → feature vectors + activity labels
2. Train/val split, normalise features
3. VQC (PennyLane, 6 qubits, 4 StronglyEntanglingLayers, 200 epochs)
4. Classical baselines: RandomForest, XGBoost, MLP
5. Apply trained VQC to virtual BGCs from Phase 3
6. Final ranking: 0.6 × novelty + 0.4 × qml_probability
7. Save all outputs to phase6_results/

Outputs
-------
phase6_results/
  training_features.npy
  qml_model_weights.npy
  model_comparison.json
  final_drug_candidates.json
  qml_experiment_report.txt
  training_loss_curve.png        (skips gracefully if matplotlib unavailable)
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

# ── optional imports ──────────────────────────────────────────────────────────
try:
    import pennylane as qml
    from pennylane import numpy as anp   # autograd-aware numpy (fallback)
    PENNYLANE_OK = True
except ImportError:
    PENNYLANE_OK = False
    print("⚠  PennyLane not found — QML step will be skipped")

try:
    import torch
    TORCH_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    TORCH_OK = True
    print(f"  PyTorch device: {TORCH_DEVICE}" +
          (f"  ({torch.cuda.get_device_name(0)})" if TORCH_DEVICE.type == "cuda" else ""))
except ImportError:
    TORCH_OK = False
    TORCH_DEVICE = None
    print("⚠  PyTorch not found — falling back to autograd VQC")

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.neural_network import MLPClassifier
    from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False
    print("⚠  scikit-learn not found — classical baselines will be skipped")

try:
    from xgboost import XGBClassifier
    XGBOOST_OK = True
except ImportError:
    XGBOOST_OK = False
    print("⚠  xgboost not found — XGBoost baseline will be skipped")

try:
    from Bio import SeqIO
    BIO_OK = True
except ImportError:
    BIO_OK = False
    sys.exit("Biopython is required: pip install biopython")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MPL_OK = True
except ImportError:
    MPL_OK = False

# ─────────────────────────────────────────────────────────────────────────────
MIBIG_DIR   = Path("mibig_gbk_4.0")
OUTPUT_DIR  = Path("phase6_results")
VBGC_FILE   = Path("phase3_results/virtual_bgcs.json")
RANKING_FILE = Path("phase4_results/bgc_final_ranking.json")
GCF_FILE    = Path("phase5_results/gcf_clusters.json")

N_QUBITS    = 6   # 6 qubits × 3 layers × 3 = 54 params — more expressive, still CPU-tractable
N_LAYERS    = 3
EPOCHS      = 60
BATCH_SIZE  = 5
LR          = 0.02
EDGE_CUTOFF = 0.30   # similarity threshold used in Phase 5
PCA_COMPONENTS = N_QUBITS  # compress 17 features → 6 PCA components (one per qubit)

# ─────────────────────────────────────────────────────────────────────────────
# Feature definition — sec_met_domain names as used by antiSMASH/MiBIG
# ─────────────────────────────────────────────────────────────────────────────
FEATURE_DOMAINS = [
    "PKS_KS", "PKS_AT", "PP-binding",      # PKS core
    "mod_KS", "hyb_KS", "itr_KS",          # KS types
    "AMP-binding", "Condensation",          # NRPS core
    "p450",                                 # P450 tailoring
    "Glycos_transf_1", "MGT",              # glycosyltransferases
    "adh_short", "ADH_zinc_N",             # dehydrogenases
    "Abhydrolase_6",                        # hydrolases/β-lactam
    "RmlD_sub_bind",                        # sugar biosynthesis (ribosomal)
]   # → 15 domain features + 2 structural = 17 total → use first 6 for embedding

STRUCT_FEATURES = [
    "cluster_length_kb",   # cluster length in kb
    "module_count",        # number of PKS/NRPS modules
]

ALL_FEATURES = FEATURE_DOMAINS + STRUCT_FEATURES   # 17 features total
N_FEATURES   = len(ALL_FEATURES)


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Build training dataset from MiBIG GBKs
# ─────────────────────────────────────────────────────────────────────────────

# Activity mapping: BGC class → binary label
# Rationale: clusters producing antibiotics, antifungals, anticancer compounds
# are labelled 1.  Saccharides, unknowns, and "other" are 0.
ACTIVE_CLASSES = {"PKS", "NRPS", "ribosomal", "terpene"}
INACTIVE_CLASSES = {"saccharide", "other"}

# Known compound → override label (manual curation for common examples)
KNOWN_ACTIVE_STEMS = {
    "antibiotic", "antimicrobial", "antifungal", "anticancer",
    "antitumor", "cytotoxic", "antiviral", "herbicidal",
}


def _label_from_mibig(label_str: str, comment: str) -> int:
    """
    Convert MiBIG subregion /label= and GBK comment to binary activity.
    1 = likely bioactive (antibiotic / antifungal / anticancer)
    0 = inactive / unknown / saccharide
    """
    parts = {p.strip().lower() for p in label_str.split(",")}
    # Any active class in the multi-label set → positive
    if parts & {a.lower() for a in ACTIVE_CLASSES}:
        return 1
    if parts & {i.lower() for i in INACTIVE_CLASSES}:
        return 0
    # Fallback: scan comment text
    comment_lower = comment.lower()
    if any(kw in comment_lower for kw in KNOWN_ACTIVE_STEMS):
        return 1
    return 0   # conservative default


def _count_modules(sec_domains: list[str]) -> int:
    """Count KS + A-domain occurrences as a proxy for module count."""
    ks_types = {"PKS_KS", "mod_KS", "hyb_KS", "itr_KS", "tra_KS"}
    a_types  = {"AMP-binding"}
    ks = sum(1 for d in sec_domains if d in ks_types)
    a  = sum(1 for d in sec_domains if d in a_types)
    return ks + a


def parse_mibig(gbk_dir: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Parse all MiBIG GBKs and return feature matrix X, labels y, ids."""
    gbks = sorted(gbk_dir.glob("*.gbk"))
    print(f"  Parsing {len(gbks)} MiBIG GBKs...")

    X_rows, y, ids = [], [], []
    skipped = 0

    for gbk in gbks:
        try:
            rec = next(SeqIO.parse(gbk, "genbank"))
        except Exception:
            skipped += 1
            continue

        # Extract label from subregion feature
        label_str = "other"
        for feat in rec.features:
            if feat.type == "subregion":
                label_str = feat.qualifiers.get("label", ["other"])[0]
                break

        comment = rec.annotations.get("comment", "")
        activity = _label_from_mibig(label_str, comment)

        # Collect all sec_met_domain strings
        sec_domains: list[str] = []
        for feat in rec.features:
            if feat.type != "CDS":
                continue
            for smd in feat.qualifiers.get("sec_met_domain", []):
                sec_domains.append(smd.split(" ")[0])

        domain_counter = Counter(sec_domains)

        # Build feature vector
        row = [float(domain_counter.get(d, 0)) for d in FEATURE_DOMAINS]
        row.append(len(rec) / 1000.0)   # cluster_length_kb
        row.append(float(_count_modules(sec_domains)))  # module_count

        X_rows.append(row)
        y.append(activity)
        ids.append(gbk.stem)

    if skipped:
        print(f"  ⚠  {skipped} GBKs skipped (parse error)")

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y, dtype=np.int32)
    print(f"  Dataset: {len(ids)} BGCs  "
          f"active={y.sum()}  inactive={len(y)-y.sum()}")
    return X, y, ids


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Normalise features
# ─────────────────────────────────────────────────────────────────────────────

def normalise(X_train: np.ndarray,
              X_val: np.ndarray,
              X_test: np.ndarray | None = None):
    """Min-max normalise to [-1, 1] using training stats."""
    mn  = X_train.min(axis=0)
    rng = X_train.max(axis=0) - mn
    rng[rng == 0] = 1.0   # avoid division by zero for constant columns

    def _scale(X):
        return 2.0 * ((X - mn) / rng) - 1.0

    out = [_scale(X_train), _scale(X_val)]
    if X_test is not None:
        out.append(_scale(X_test))
    return tuple(out), mn, rng


# ─────────────────────────────────────────────────────────────────────────────
# Step 2b — PCA compression (17 → N_QUBITS features for quantum embedding)
# ─────────────────────────────────────────────────────────────────────────────

def fit_pca(X_train: np.ndarray, n_components: int = 6):
    """Fit PCA on training set, return (pca, X_train_reduced)."""
    pca = PCA(n_components=n_components, random_state=42)
    X_r = pca.fit_transform(X_train)
    explained = pca.explained_variance_ratio_.sum()
    print(f"  PCA {X_train.shape[1]}→{n_components} dims  "
          f"variance explained: {explained:.1%}")
    return pca, X_r


# ─────────────────────────────────────────────────────────────────────────────
# Step 3+4 — VQC with PennyLane
# ─────────────────────────────────────────────────────────────────────────────

def build_vqc():
    """Return the QNode and initial weights (torch CUDA if available)."""
    use_torch = TORCH_OK and PENNYLANE_OK

    if use_torch:
        # backprop diff reuses the forward-pass graph — much faster than
        # parameter-shift, and runs on GPU when weights are CUDA tensors.
        dev = qml.device("default.qubit", wires=N_QUBITS)

        @qml.qnode(dev, interface="torch", diff_method="backprop")
        def circuit(weights, x):
            qml.templates.AngleEmbedding(x[:N_QUBITS], wires=range(N_QUBITS),
                                         rotation="Y")
            qml.templates.StronglyEntanglingLayers(weights,
                                                   wires=range(N_QUBITS))
            return qml.expval(qml.PauliZ(0))

        weight_shape = qml.templates.StronglyEntanglingLayers.shape(
            n_layers=N_LAYERS, n_wires=N_QUBITS)
        rng = np.random.default_rng(42)
        init = torch.tensor(
            rng.uniform(-np.pi / 4, np.pi / 4, weight_shape),
            dtype=torch.float64,
            device=TORCH_DEVICE,
        )
        weights = torch.nn.Parameter(init)   # tracked by torch.optim
        print(f"  VQC backend: PyTorch ({TORCH_DEVICE})  diff=backprop")
    else:
        # Autograd fallback (CPU only)
        dev = qml.device("default.qubit", wires=N_QUBITS)

        @qml.qnode(dev, interface="autograd")
        def circuit(weights, x):
            qml.templates.AngleEmbedding(x[:N_QUBITS], wires=range(N_QUBITS),
                                         rotation="Y")
            qml.templates.StronglyEntanglingLayers(weights,
                                                   wires=range(N_QUBITS))
            return qml.expval(qml.PauliZ(0))

        weight_shape = qml.templates.StronglyEntanglingLayers.shape(
            n_layers=N_LAYERS, n_wires=N_QUBITS)
        rng = np.random.default_rng(42)
        weights = anp.array(
            rng.uniform(-np.pi / 4, np.pi / 4, weight_shape),
            requires_grad=True,
        )
        print("  VQC backend: PennyLane autograd (CPU)  diff=parameter-shift")

    return circuit, weights


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def binary_cross_entropy(probs: np.ndarray, labels: np.ndarray) -> float:
    eps = 1e-7
    p = np.clip(probs, eps, 1 - eps)
    return -np.mean(labels * np.log(p) + (1 - labels) * np.log(1 - p))


def _vqc_probs_torch(circuit, weights, X: np.ndarray) -> np.ndarray:
    """Run circuit on a numpy array of inputs, return numpy probs (torch path)."""
    with torch.no_grad():
        X_t = torch.tensor(X, dtype=torch.float64, device=TORCH_DEVICE)
        raw = torch.stack([circuit(weights, x) for x in X_t])
        return torch.sigmoid(raw).cpu().numpy()


def train_vqc(circuit, weights, X_tr: np.ndarray,
              y_tr: np.ndarray, X_val: np.ndarray,
              y_val: np.ndarray) -> tuple:
    """Adam training loop (torch/GPU or autograd/CPU). Returns (best_weights, train_losses, val_losses)."""
    use_torch = TORCH_OK and isinstance(weights, torch.nn.Parameter)
    n   = len(X_tr)
    rng = np.random.default_rng(0)

    train_losses, val_losses = [], []
    best_val_loss = float("inf")

    # Balanced class weights capped at 3× to prevent minority-class collapse
    # (uncapped inverse-frequency weights cause model to predict all-inactive
    #  after epoch 1, then best_weights freezes at epoch-1 = trivial majority)
    n_pos = float(y_tr.sum())
    n_neg = float(n - n_pos)
    MAX_W = 3.0
    pos_w = min(n / (2.0 * n_pos), MAX_W) if n_pos > 0 else 1.0
    neg_w = min(n / (2.0 * n_neg), MAX_W) if n_neg > 0 else 1.0
    sample_weights = np.where(y_tr == 1, pos_w, neg_w).astype(np.float64)
    print(f"  Class weights — active: {pos_w:.3f}, inactive: {neg_w:.3f} (capped at {MAX_W}×)")

    n_params = N_QUBITS * N_LAYERS * 3
    print(f"  Training VQC: {N_QUBITS} qubits × {N_LAYERS} layers "
          f"({n_params} params), {EPOCHS} epochs, batch={BATCH_SIZE}, lr={LR}")

    if use_torch:
        # ── PyTorch path (GPU if TORCH_DEVICE=cuda) ──────────────────────────
        opt = torch.optim.Adam([weights], lr=LR)

        best_weights = weights.data.clone()

        for epoch in range(1, EPOCHS + 1):
            idx = rng.permutation(n)
            epoch_loss = 0.0
            n_batches  = 0

            weights.requires_grad_(True)
            for start in range(0, n, BATCH_SIZE):
                batch_idx = idx[start: start + BATCH_SIZE]
                X_b = torch.tensor(X_tr[batch_idx],
                                   dtype=torch.float64, device=TORCH_DEVICE)
                y_b = torch.tensor(y_tr[batch_idx].astype(np.float64),
                                   dtype=torch.float64, device=TORCH_DEVICE)
                sw  = torch.tensor(sample_weights[batch_idx],
                                   dtype=torch.float64, device=TORCH_DEVICE)

                opt.zero_grad()
                raw  = torch.stack([circuit(weights, x) for x in X_b])
                prob = torch.sigmoid(raw)
                eps  = 1e-7
                p    = torch.clamp(prob, eps, 1.0 - eps)
                bce  = -(y_b * torch.log(p) + (1.0 - y_b) * torch.log(1.0 - p))
                loss = (sw * bce).mean()
                loss.backward()
                opt.step()

                epoch_loss += float(loss.item())
                n_batches  += 1

            train_loss = epoch_loss / max(n_batches, 1)

            # Validation
            val_probs_arr = _vqc_probs_torch(circuit, weights, X_val)
            val_loss = binary_cross_entropy(val_probs_arr, y_val.astype(np.float64))

            train_losses.append(train_loss)
            val_losses.append(val_loss)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_weights  = weights.data.clone()

            if epoch % 20 == 0 or epoch == 1:
                tr_probs = _vqc_probs_torch(circuit, weights, X_tr)
                tr_acc   = float(np.mean((tr_probs > 0.5) == y_tr))
                vl_acc   = float(np.mean((val_probs_arr > 0.5) == y_val))
                print(f"  Epoch {epoch:3d}/{EPOCHS}  "
                      f"train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  "
                      f"train_acc={tr_acc:.3f}  val_acc={vl_acc:.3f}")

        # Return as numpy for downstream compatibility
        weights.data.copy_(best_weights)
        return weights, train_losses, val_losses

    else:
        # ── Autograd fallback (CPU) ───────────────────────────────────────────
        opt = qml.AdamOptimizer(stepsize=LR)
        best_weights = weights.copy()

        for epoch in range(1, EPOCHS + 1):
            idx = rng.permutation(n)
            epoch_loss = 0.0
            n_batches  = 0

            for start in range(0, n, BATCH_SIZE):
                batch_idx = idx[start: start + BATCH_SIZE]
                X_b = X_tr[batch_idx]
                y_b = y_tr[batch_idx].astype(np.float64)
                sw  = sample_weights[batch_idx]

                def cost(w, _X_b=X_b, _y_b=y_b, _sw=sw):
                    raw  = anp.stack([circuit(w, x) for x in _X_b])
                    prob = 1.0 / (1.0 + anp.exp(-raw))
                    eps  = 1e-7
                    p    = anp.clip(prob, eps, 1.0 - eps)
                    bce  = -(_y_b * anp.log(p) + (1.0 - _y_b) * anp.log(1.0 - p))
                    return anp.mean(_sw * bce)

                weights, loss_val = opt.step_and_cost(cost, weights)
                epoch_loss += float(loss_val)
                n_batches  += 1

            train_loss = epoch_loss / max(n_batches, 1)

            val_probs_arr = np.array(
                [sigmoid(float(circuit(weights, x))) for x in X_val])
            val_loss = binary_cross_entropy(val_probs_arr, y_val.astype(np.float64))

            train_losses.append(train_loss)
            val_losses.append(val_loss)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_weights  = weights.copy()

            if epoch % 20 == 0 or epoch == 1:
                tr_pred = np.array(
                    [sigmoid(float(circuit(weights, x))) for x in X_tr]) > 0.5
                tr_acc  = np.mean(tr_pred == y_tr)
                vl_acc  = np.mean((val_probs_arr > 0.5) == y_val)
                print(f"  Epoch {epoch:3d}/{EPOCHS}  "
                      f"train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  "
                      f"train_acc={tr_acc:.3f}  val_acc={vl_acc:.3f}")

        return best_weights, train_losses, val_losses


def evaluate_vqc(circuit, weights, X: np.ndarray,
                 y: np.ndarray) -> dict:
    if TORCH_OK and isinstance(weights, torch.nn.Parameter):
        probs = _vqc_probs_torch(circuit, weights, X)
    else:
        probs = np.array([sigmoid(float(circuit(weights, x))) for x in X])
    preds = (probs > 0.5).astype(int)
    return {
        "accuracy":  float(np.mean(preds == y)),
        "precision": float(precision_score(y, preds, zero_division=0)),
        "recall":    float(recall_score(y, preds, zero_division=0)),
        "roc_auc":   float(roc_auc_score(y, probs))
            if len(np.unique(y)) > 1 else 0.0,
        "probs":     probs.tolist(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Classical baselines
# ─────────────────────────────────────────────────────────────────────────────

def _scale_pos_weight(y: np.ndarray) -> float:
    """Compute neg/pos class ratio for imbalanced binary classification."""
    pos = float(np.sum(y == 1))
    neg = float(np.sum(y == 0))
    return (neg / pos) if pos > 0 else 1.0

def train_classical(X_tr, y_tr, X_val, y_val) -> dict:
    """Train RF, XGBoost, MLP and return performance comparison dict."""
    results = {}

    models = {
        "RandomForest":       RandomForestClassifier(
            n_estimators=200, max_depth=10, random_state=42, n_jobs=-1,
            class_weight="balanced"),
        "MLP":                MLPClassifier(
            hidden_layer_sizes=(64, 32), max_iter=300,
            random_state=42, early_stopping=True),
    }

    if XGBOOST_OK:
        models["XGBoost"] = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
            scale_pos_weight=_scale_pos_weight(y_tr),
            verbosity=0,
        )
    else:
        print("  ⚠  Skipping XGBoost baseline (xgboost not installed)")

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_val_s = scaler.transform(X_val)

    for name, model in models.items():
        t0 = time.time()
        model.fit(X_tr_s, y_tr)
        elapsed = time.time() - t0

        probs = model.predict_proba(X_val_s)[:, 1]
        preds = (probs > 0.5).astype(int)

        results[name] = {
            "accuracy":  float(accuracy_score(y_val, preds)),
            "precision": float(precision_score(y_val, preds, zero_division=0)),
            "recall":    float(recall_score(y_val, preds, zero_division=0)),
            "roc_auc":   float(roc_auc_score(y_val, probs))
                if len(np.unique(y_val)) > 1 else 0.0,
            "train_time_s": round(elapsed, 2),
        }
        print(f"  {name:<22}  acc={results[name]['accuracy']:.3f}  "
              f"auc={results[name]['roc_auc']:.3f}  "
              f"t={elapsed:.1f}s")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Step 5b — k-fold Cross-Validation
# ─────────────────────────────────────────────────────────────────────────────

def run_cross_validation(X: np.ndarray, y: np.ndarray,
                        n_folds: int = 5) -> dict:
    """
    Stratified k-fold CV for all classical classifiers.
    Returns dict: model_name → {acc_mean, acc_std, auc_mean, auc_std}.
    """
    from sklearn.model_selection import StratifiedKFold
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    model_factories = {
        "RandomForest":       lambda y_train: RandomForestClassifier(
            n_estimators=200, max_depth=10, random_state=42,
            n_jobs=-1, class_weight="balanced"),
        "MLP":                lambda y_train: MLPClassifier(
            hidden_layer_sizes=(64, 32), max_iter=300,
            random_state=42, early_stopping=True),
    }

    if XGBOOST_OK:
        model_factories["XGBoost"] = lambda y_train: XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
            scale_pos_weight=_scale_pos_weight(y_train),
            verbosity=0,
        )
    else:
        print("  ⚠  Skipping XGBoost in CV (xgboost not installed)")

    cv_results = {}
    for name, factory in model_factories.items():
        acc_scores, auc_scores = [], []
        for fold, (tr_idx, va_idx) in enumerate(
                skf.split(X, y), 1):
            X_tr, X_va = X[tr_idx], X[va_idx]
            y_tr, y_va = y[tr_idx], y[va_idx]

            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr)
            X_va_s = scaler.transform(X_va)

            model = factory(y_tr)
            model.fit(X_tr_s, y_tr)
            probs = model.predict_proba(X_va_s)[:, 1]
            preds = (probs > 0.5).astype(int)

            acc_scores.append(accuracy_score(y_va, preds))
            auc_scores.append(
                roc_auc_score(y_va, probs)
                if len(np.unique(y_va)) > 1 else 0.0
            )

        auc_mean = float(np.mean(auc_scores))
        auc_std  = float(np.std(auc_scores))
        auc_lo   = round(auc_mean - 1.96 * auc_std, 4)
        auc_hi   = round(auc_mean + 1.96 * auc_std, 4)
        cv_results[name] = {
            "acc_mean":   round(float(np.mean(acc_scores)), 4),
            "acc_std":    round(float(np.std(acc_scores)),  4),
            "auc_mean":   round(auc_mean, 4),
            "auc_std":    round(auc_std,  4),
            "auc_ci_lo":  auc_lo,
            "auc_ci_hi":  auc_hi,
            "n_folds":    n_folds,
        }
        print(f"  {name:<22}  "
              f"acc={cv_results[name]['acc_mean']:.3f}±{cv_results[name]['acc_std']:.3f}  "
              f"auc={cv_results[name]['auc_mean']:.3f}±{cv_results[name]['auc_std']:.3f}  "
              f"(95% CI: {auc_lo:.3f}–{auc_hi:.3f})")
    return cv_results


def vqc_cross_validation(X: np.ndarray, y: np.ndarray,
                         n_folds: int = 3) -> dict:
    """
    Stratified 3-fold CV for the VQC on the QML-sized dataset.
    Slower than classical CV — use 3 folds to keep it tractable.
    Returns {acc_mean, acc_std, auc_mean, auc_std}.
    """
    if not (PENNYLANE_OK and SKLEARN_OK):
        return {}
    from sklearn.model_selection import StratifiedKFold
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    acc_scores, auc_scores = [], []
    for fold, (tr_idx, va_idx) in enumerate(skf.split(X, y), 1):
        X_tr_f, X_va_f = X[tr_idx], X[va_idx]
        y_tr_f, y_va_f = y[tr_idx], y[va_idx]

        (X_tr_n, X_va_n), _, _ = normalise(X_tr_f, X_va_f)

        circuit, weights = build_vqc()
        best_w, _, _ = train_vqc(
            circuit, weights, X_tr_n, y_tr_f, X_va_n, y_va_f)

        metrics = evaluate_vqc(circuit, best_w, X_va_n, y_va_f)
        acc_scores.append(metrics["accuracy"])
        auc_scores.append(metrics["roc_auc"])
        print(f"  VQC fold {fold}/{n_folds}  "
              f"acc={metrics['accuracy']:.3f}  auc={metrics['roc_auc']:.3f}")

    auc_mean = float(np.mean(auc_scores))
    auc_std  = float(np.std(auc_scores))
    auc_lo   = round(auc_mean - 1.96 * auc_std, 4)
    auc_hi   = round(auc_mean + 1.96 * auc_std, 4)
    return {
        "acc_mean":   round(float(np.mean(acc_scores)), 4),
        "acc_std":    round(float(np.std(acc_scores)),  4),
        "auc_mean":   round(auc_mean, 4),
        "auc_std":    round(auc_std,  4),
        "auc_ci_lo":  auc_lo,
        "auc_ci_hi":  auc_hi,
        "n_folds":    n_folds,
    }
# ─────────────────────────────────────────────────────────────────────────────

def vbgc_features(vbgcs: list[dict],
                  bgcres: list[dict]) -> np.ndarray:
    """
    Build the same 17-feature vector for each virtual BGC.
    Domain counts come from the genes stored in bgc_results.json;
    cluster_length and module_count from the virtual_bgcs.json record.
    """
    # region_id → list of sec_met_domain strings (approximated from domain dicts)
    region_domains: dict[str, list[str]] = {}
    for region in bgcres:
        doms: list[str] = []
        for gene in region.get("genes", []):
            for d in gene.get("domains", []):
                # Map our Pfam-name back to sec_met_domain naming where possible
                doms.append(d.get("pfam_name", d.get("bgc_type", "")))
        region_domains[region["region_id"]] = doms

    rows = []
    for v in vbgcs:
        all_doms: list[str] = []
        for mr in v.get("member_regions", []):
            all_doms.extend(region_domains.get(mr, []))

        dc = Counter(all_doms)

        # Feature vector (same order as FEATURE_DOMAINS + STRUCT)
        # Note: our Pfam names differ slightly from sec_met_domain names;
        # we use a best-effort crosswalk here.
        crosswalk = {
            "PKS_KS":           ["PKS_KS"],
            "PKS_AT":           ["PKS_AT"],
            "PP-binding":       ["PKS_ACP", "NRPS_T"],
            "mod_KS":           ["PKS_KS"],
            "hyb_KS":           ["PKS_KS"],
            "itr_KS":           ["PKS_KS"],
            "AMP-binding":      ["NRPS_A"],
            "Condensation":     ["NRPS_C"],
            "p450":             ["P450"],
            "Glycos_transf_1":  ["Glycosyltransf"],
            "MGT":              ["Methyltransf"],
            "adh_short":        ["Dehydrogenase"],
            "ADH_zinc_N":       ["Dehydrogenase"],
            "Abhydrolase_6":    ["BetaLactam_synthase"],
            "RmlD_sub_bind":    ["Glycosyltransf"],
        }

        row = []
        for feat in FEATURE_DOMAINS:
            aliases = crosswalk.get(feat, [feat])
            count   = sum(dc.get(a, 0) for a in aliases)
            row.append(float(count))

        # Structural features – estimate from virtual BGC metadata
        n_regions = len(v.get("member_regions", []))
        row.append(float(n_regions * 10.0))   # rough kb estimate
        row.append(float(v.get("total_domains", 1)))

        rows.append(row)

    return np.array(rows, dtype=np.float32)


# ─────────────────────────────────────────────────────────────────────────────
# Step 8 — Report
# ─────────────────────────────────────────────────────────────────────────────

def write_report(path: Path,
                 n_train: int, n_val: int,
                 qml_metrics: dict | None,
                 classical_metrics: dict,
                 classical_metrics_small: dict,
                 cv_results: dict,
                 vqc_cv: dict,
                 candidates: list[dict],
                 train_losses: list | None,
                 val_losses: list | None) -> None:

    lines = [
        "=" * 72,
        "  Phase 6 — Quantum ML Drug-Potential Prediction",
        "  Trained on MiBIG 4.0  ·  Applied to Discovered Virtual BGCs",
        "=" * 72,
        "",
        "  Training Configuration",
        "  ─────────────────────────────────────────────",
        f"  Training samples   : {n_train}",
        f"  Validation samples : {n_val}",
        f"  Feature dimensions : {N_FEATURES}",
        "",
        "  VQC Architecture",
        "  ─────────────────────────────────────────────",
        f"  Device      : PennyLane default.qubit",
        f"  Qubits      : {N_QUBITS}",
        f"  Layers      : {N_LAYERS} (StronglyEntanglingLayers)",
        f"  Embedding   : AngleEmbedding (Y-rotation, {N_QUBITS} features of {N_FEATURES})",
        f"  Output      : expval(PauliZ(0)) → sigmoid → binary activity probability",
        f"  Epochs      : {EPOCHS}  (Adam, lr={LR}, batch={BATCH_SIZE})",
        "",
    ]

    if qml_metrics:
        lines += [
            "  VQC Performance (validation set)",
            "  ─────────────────────────────────────────────",
            f"  Accuracy   : {qml_metrics['accuracy']:.3f}",
            f"  Precision  : {qml_metrics['precision']:.3f}",
            f"  Recall     : {qml_metrics['recall']:.3f}",
            f"  ROC-AUC    : {qml_metrics['roc_auc']:.3f}",
            "",
        ]
    else:
        lines += ["  VQC: skipped (PennyLane not available)", ""]

    lines += [
        "  Classical Baseline Comparison — FULL DATA (validation set)",
        "  ─────────────────────────────────────────────",
        f"  {'Model':<22} {'N_train':>8} {'Accuracy':>9} {'Precision':>10} "
        f"{'Recall':>8} {'ROC-AUC':>9}",
        "  " + "─" * 70,
    ]
    for m, s in classical_metrics.items():
        n_tr = s.get('train_samples', '?')
        lines.append(
            f"  {m:<22} {str(n_tr):>8} {s['accuracy']:>9.3f} {s['precision']:>10.3f} "
            f"{s['recall']:>8.3f} {s['roc_auc']:>9.3f}"
        )
    lines.append("")

    if classical_metrics_small:
        lines += [
            f"  Fair Comparison — SAME {n_train}-SAMPLE SUBSET (validation set)",
            "  ─────────────────────────────────────────────",
            f"  {'Model':<30} {'Accuracy':>9} {'Precision':>10} "
            f"{'Recall':>8} {'ROC-AUC':>9}",
            "  " + "─" * 70,
        ]
        if qml_metrics:
            lines.append(
                f"  {'VQC_PennyLane':<30} {qml_metrics['accuracy']:>9.3f} "
                f"{qml_metrics['precision']:>10.3f} "
                f"{qml_metrics['recall']:>8.3f} {qml_metrics['roc_auc']:>9.3f}"
            )
        for m, s in classical_metrics_small.items():
            lines.append(
                f"  {m:<30} {s['accuracy']:>9.3f} {s['precision']:>10.3f} "
                f"{s['recall']:>8.3f} {s['roc_auc']:>9.3f}"
            )
        lines.append("")

    if cv_results or vqc_cv:
        n_folds_cl = next(iter(cv_results.values()), {}).get("n_folds", 5) if cv_results else 5
        n_folds_vq = vqc_cv.get("n_folds", 3)
        lines += [
            f"  Cross-Validation Results — {n_folds_cl}-fold classical / "
            f"{n_folds_vq}-fold VQC (mean ± std, 95% CI)",
            "  ─────────────────────────────────────────────────────────────────────────",
            f"  {'Model':<24} {'Accuracy':>17} {'ROC-AUC (mean±std)':>22} {'95% CI':>18}",
            "  " + "─" * 84,
        ]
        if vqc_cv:
            ci = (f"{vqc_cv['auc_ci_lo']:.3f}–{vqc_cv['auc_ci_hi']:.3f}"
                  if "auc_ci_lo" in vqc_cv else "n/a")
            lines.append(
                f"  {'VQC_PennyLane':<24} "
                f"{vqc_cv['acc_mean']:.3f} ± {vqc_cv['acc_std']:.3f}   "
                f"{vqc_cv['auc_mean']:.3f} ± {vqc_cv['auc_std']:.3f}   "
                f"{ci:>18}"
            )
        for m, s in cv_results.items():
            ci = (f"{s['auc_ci_lo']:.3f}–{s['auc_ci_hi']:.3f}"
                  if "auc_ci_lo" in s else "n/a")
            lines.append(
                f"  {m:<24} "
                f"{s['acc_mean']:.3f} ± {s['acc_std']:.3f}   "
                f"{s['auc_mean']:.3f} ± {s['auc_std']:.3f}   "
                f"{ci:>18}"
            )
        lines.append("")
    lines.append("")

    if train_losses:
        lines += [
            "  VQC Training Dynamics",
            "  ─────────────────────────────────────────────",
            f"  Initial train loss : {train_losses[0]:.4f}",
            f"  Final   train loss : {train_losses[-1]:.4f}",
            f"  Best    val   loss : {min(val_losses):.4f}  "
            f"(epoch {val_losses.index(min(val_losses))+1})",
            "",
        ]

    lines += [
        "=" * 72,
        "  Top Drug Candidates (Virtual BGCs ranked by final score)",
        "=" * 72,
        "",
        f"  Final Score = 0.6 × novelty_score + 0.4 × qml_probability",
        "",
        f"  {'Rank':<5} {'VBGC':<12} {'Class':<28} {'Novelty':>8} "
        f"{'QML_P':>7} {'Score':>7} {'GCF':>8}  Metabolite",
        "  " + "─" * 96,
    ]
    for c in candidates[:14]:
        lines.append(
            f"  {c['rank']:<5} {c['vbgc_id']:<12} {c['bgc_class']:<28} "
            f"{c['novelty_score']:>8.2f} {c['qml_probability']:>7.4f} "
            f"{c['final_score']:>7.3f} {c['gcf_family']:>8}  "
            f"{c['predicted_metabolite']}"
        )

    lines += ["", "=" * 72]
    path.write_text("\n".join(lines), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 72)
    print("  Phase 6 — Trained QML Drug-Potential Predictor")
    print("=" * 72)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Parse MiBIG ──────────────────────────────────────────────────
    print("\n[1/8] Building training dataset from MiBIG 4.0...")
    X, y, ids = parse_mibig(MIBIG_DIR)

    # Save feature matrix
    feat_path = OUTPUT_DIR / "training_features.npy"
    np.save(feat_path, X)
    print(f"  Saved -> {feat_path}  shape={X.shape}")

    # ── Step 2: Train/val split + normalise ──────────────────────────────────
    print("\n[2/8] Splitting and normalising features...")
    # Use a small subset for QML (expensive) but full set for classical models
    X_tr_full, X_val, y_tr_full, y_val = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y)

    # QML subset: stratified to guarantee class balance (fix: was random
    # which could give <10 minority samples → extreme weights → collapse)
    QML_TRAIN_LIMIT = 250
    QML_VAL_LIMIT   = 80

    # Stratified split so QML subset mirrors 82%/18% distribution
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

    # Raw normalise (stats kept for VBGC raw inference fallback only)
    (X_qml_tr_n, X_qml_val_n), mn, rng_scale = normalise(
        X_qml_tr, X_qml_val)

    # PCA 17→6: all features contribute to quantum embedding
    scaler_pca = StandardScaler()
    X_pca_base = scaler_pca.fit_transform(X_tr_full)
    pca, _     = fit_pca(X_pca_base, n_components=PCA_COMPONENTS)
    pca_variance = float(pca.explained_variance_ratio_.sum())

    # Normalise PCA-projected QML subsets and SAVE the training stats
    (X_qml_tr_n, X_qml_val_n), mn_pca, rng_pca = normalise(
        pca.transform(scaler_pca.transform(X_qml_tr)),
        pca.transform(scaler_pca.transform(X_qml_val)),
    )

    n_active_qml  = int(y_qml_tr.sum())
    n_inactive_qml = int(len(y_qml_tr) - n_active_qml)
    print(f"  QML train: {len(X_qml_tr)}  "
          f"(active={n_active_qml}, inactive={n_inactive_qml})")
    print(f"  QML val  : {len(X_qml_val)}")
    print(f"  Classical train: {len(X_tr_full)}  val: {len(X_val)}")
    print(f"  Class balance — active: {y.sum()}/{len(y)} "
          f"({100*y.mean():.1f}%)")
    print(f"  PCA variance explained: {pca_variance:.1%}")

    # ── Step 3+4: Train VQC ──────────────────────────────────────────────────
    best_weights = None
    train_losses = val_losses = None
    qml_val_metrics: dict | None = None

    if PENNYLANE_OK:
        print(f"\n[3/8] Training Variational Quantum Classifier...")
        circuit, weights = build_vqc()
        best_weights, train_losses, val_losses = train_vqc(
            circuit, weights,
            X_qml_tr_n, y_qml_tr,
            X_qml_val_n, y_qml_val)

        # Evaluate
        print("  Evaluating VQC on validation set...")
        qml_val_metrics = evaluate_vqc(
            circuit, best_weights, X_qml_val_n, y_qml_val)
        print(f"  VQC val acc={qml_val_metrics['accuracy']:.3f}  "
              f"auc={qml_val_metrics['roc_auc']:.3f}")

        # Save weights (convert torch tensor → numpy if needed)
        wt_path = OUTPUT_DIR / "qml_model_weights.npy"
        wt_arr = best_weights.data.cpu().numpy() \
            if (TORCH_OK and isinstance(best_weights, torch.nn.Parameter)) \
            else np.array(best_weights)
        np.save(wt_path, wt_arr)
        print(f"  Saved -> {wt_path}")

        # Loss curve
        if MPL_OK and train_losses:
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.plot(train_losses, label="Train loss", color="#2196F3")
            ax.plot(val_losses,   label="Val   loss", color="#FF5722")
            ax.set_xlabel("Epoch")
            ax.set_ylabel("Binary Cross-Entropy")
            ax.set_title(f"VQC Training  ({N_QUBITS} qubits × {N_LAYERS} layers)")
            ax.legend()
            ax.grid(alpha=0.3)
            fig.tight_layout()
            lc_path = OUTPUT_DIR / "training_loss_curve.png"
            fig.savefig(lc_path, dpi=120)
            plt.close(fig)
            print(f"  Saved -> {lc_path}")
    else:
        print("\n[3/8] Skipping VQC (PennyLane not available)")

    # ── Step 5: Classical baselines ──────────────────────────────────────────
    classical_metrics: dict = {}
    classical_metrics_small: dict = {}   # fair comparison: same 250 samples as VQC
    cv_results: dict = {}               # 5-fold CV for classical models
    vqc_cv: dict = {}                   # 3-fold CV for VQC
    if SKLEARN_OK:
        print(f"\n[4/8] Training classical baselines on {len(X_tr_full)} samples...")
        classical_metrics = train_classical(
            X_tr_full, y_tr_full, X_val, y_val)

        # Fair comparison: retrain on the same subset used by VQC
        print(f"\n[4b/8] Fair comparison — classical on same "
              f"{len(X_qml_tr)}-sample subset as VQC...")
        classical_metrics_small = train_classical(
            X_qml_tr, y_qml_tr, X_qml_val, y_qml_val)
        # Tag entries so the report can distinguish them
        classical_metrics_small = {
            f"{k}_n{len(X_qml_tr)}": v
            for k, v in classical_metrics_small.items()
        }
    else:
        print("\n[4/8] Skipping classical baselines (scikit-learn not available)")

    # Assemble model comparison
    comparison: dict = {}
    if qml_val_metrics:
        comparison["VQC_PennyLane"] = {
            "accuracy":    qml_val_metrics["accuracy"],
            "precision":   qml_val_metrics["precision"],
            "recall":      qml_val_metrics["recall"],
            "roc_auc":     qml_val_metrics["roc_auc"],
            "train_samples": int(len(X_qml_tr)),
            "architecture": f"{N_QUBITS}q × {N_LAYERS}L StronglyEntangling",
        }
    comparison.update(classical_metrics)          # full-data baselines
    comparison.update(classical_metrics_small)    # fair same-size baselines

    comp_path = OUTPUT_DIR / "model_comparison.json"
    comp_path.write_text(json.dumps(comparison, indent=2))
    print(f"\n  Model comparison saved -> {comp_path}")
    # Print fair-comparison summary to console
    if qml_val_metrics and classical_metrics_small:
        print("\n  Fair comparison (all trained on same "
              f"{len(X_qml_tr)} samples):")
        print(f"  {'Model':<30} {'Accuracy':>9} {'ROC-AUC':>9}")
        print("  " + "─" * 52)
        print(f"  {'VQC_PennyLane':<30} "
              f"{qml_val_metrics['accuracy']:>9.3f} "
              f"{qml_val_metrics['roc_auc']:>9.3f}")
        for name, m in classical_metrics_small.items():
            print(f"  {name:<30} {m['accuracy']:>9.3f} {m['roc_auc']:>9.3f}")

    # ── Step 5c: k-fold cross-validation ────────────────────────────────────
    if SKLEARN_OK:
        # Combine train + val for proper k-fold over the full available pool
        X_cv_pool = np.vstack([X_tr_full, X_val])
        y_cv_pool = np.concatenate([y_tr_full, y_val])
        print(f"\n[4c/8] 5-fold stratified CV on {len(X_cv_pool)} samples "
              "(classical models)...")
        cv_results = run_cross_validation(X_cv_pool, y_cv_pool, n_folds=5)

    if PENNYLANE_OK and SKLEARN_OK:
        # Use the same 250+80 = 330-sample QML pool for VQC CV (3 folds, tractable)
        X_vqc_cv_pool = np.vstack([X_qml_tr, X_qml_val])
        y_vqc_cv_pool = np.concatenate([y_qml_tr, y_qml_val])
        print(f"\n[4d/8] 3-fold VQC CV on {len(X_vqc_cv_pool)} samples "
              "(GPU, may take ~2-3 min)...")
        vqc_cv = vqc_cross_validation(X_vqc_cv_pool, y_vqc_cv_pool, n_folds=3)
        if vqc_cv:
            print(f"  VQC CV  acc={vqc_cv['acc_mean']:.3f}±{vqc_cv['acc_std']:.3f}  "
                  f"auc={vqc_cv['auc_mean']:.3f}±{vqc_cv['auc_std']:.3f}")

    # Attach CV results to comparison and re-save JSON
    if cv_results or vqc_cv:
        comparison["cross_validation"] = {
            "classical_5fold": cv_results,
            "vqc_3fold":       vqc_cv,
        }
        comp_path.write_text(json.dumps(comparison, indent=2))
        print(f"  model_comparison.json updated with cross_validation key")

    # ── Step 6: Apply VQC (or best classical) to virtual BGCs ────────────────
    print("\n[5/8] Loading virtual BGCs and Phase 4 ranking...")
    vbgcs    = json.loads(VBGC_FILE.read_text())
    ranking  = json.loads(RANKING_FILE.read_text())
    gcf_data = json.loads(GCF_FILE.read_text()) if GCF_FILE.exists() else []
    bgcres   = json.loads(
        Path("stage2_production_results/bgc_results.json").read_text())

    rank_idx = {r["vbgc_id"]: r for r in ranking}

    # Build GCF lookup
    vbgc_gcf: dict[str, str] = {}
    for g in gcf_data:
        for m in g.get("members", []):
            vbgc_gcf[m] = g["gcf_id"]

    print("[6/8] Extracting features for virtual BGCs...")
    X_vbgc = vbgc_features(vbgcs, bgcres)

    # Diagnostic: check feature diversity across VBGCs
    feat_std = X_vbgc.std(axis=0)
    n_varying = int((feat_std > 0.01).sum())
    print(f"  VBGC feature matrix: shape={X_vbgc.shape}  "
          f"varying features={n_varying}/{X_vbgc.shape[1]}")
    print(f"  Per-VBGC feature norms: "
          + " ".join(f"{np.linalg.norm(r):.2f}" for r in X_vbgc))

    print("[7/8] Computing QML drug-potential probabilities...")
    qml_probs: list[float] = []

    if PENNYLANE_OK and best_weights is not None:
        # Apply SAME PCA + normalization used during VQC training so that
        # inference inputs live in the same space as training inputs.
        # (Fix: was using raw normalization → mismatch → identical outputs)
        X_vbgc_pca   = pca.transform(scaler_pca.transform(X_vbgc))
        X_vbgc_pca_n = 2.0 * ((X_vbgc_pca - mn_pca) /
                               np.where(rng_pca == 0, 1.0, rng_pca)) - 1.0
        print(f"  VBGC PCA norms (should vary): "
              + " ".join(f"{np.linalg.norm(r):.2f}" for r in X_vbgc_pca_n))
        circuit_inf, _ = build_vqc()
        if TORCH_OK and isinstance(best_weights, torch.nn.Parameter):
            probs_arr = _vqc_probs_torch(circuit_inf, best_weights, X_vbgc_pca_n)
            qml_probs = [round(float(p), 4) for p in probs_arr]
        else:
            for x in X_vbgc_pca_n:
                p = sigmoid(float(circuit_inf(best_weights, x)))
                qml_probs.append(round(p, 4))
    elif SKLEARN_OK and "RandomForest" in classical_metrics:
        # Fallback: use RandomForest trained on full dataset
        print("  (Using RandomForest as QML fallback)")
        scaler_fb = StandardScaler()
        X_fb_tr   = scaler_fb.fit_transform(X_tr_full)
        X_vbgc_fb = scaler_fb.transform(X_vbgc)
        rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
        rf.fit(X_fb_tr, y_tr_full)
        qml_probs = rf.predict_proba(X_vbgc_fb)[:, 1].tolist()
    else:
        # No model available — use a heuristic based on feature sum
        qml_probs = [
            float(np.clip(np.sum(np.abs(x)) / N_QUBITS, 0, 1))
            for x in X_vbgc
        ]

    # ── Step 7: Final ranking ─────────────────────────────────────────────────
    candidates = []
    for i, v in enumerate(vbgcs):
        vid  = v["virtual_bgc_id"]
        r    = rank_idx.get(vid, {})
        nov  = r.get("novelty_score", 0.0)
        qp   = qml_probs[i] if i < len(qml_probs) else 0.5
        fscore = round(0.6 * nov + 0.4 * qp * 100, 4)  # scale qp to ~0-100 range

        candidates.append({
            "rank":               0,           # filled below
            "vbgc_id":            vid,
            "bgc_class":          v.get("bgc_class", "Unknown"),
            "novelty_score":      round(nov, 4),
            "qml_probability":    round(qp, 4),
            "final_score":        fscore,
            "gcf_family":         vbgc_gcf.get(vid, "singleton"),
            "predicted_metabolite": r.get("predicted_metabolite", "unknown"),
            "est_mol_weight_Da":  r.get("est_mol_weight_Da", 0),
            "est_logP":           r.get("est_logP", 0),
            "drug_potential_score": r.get("drug_potential_score", 0),
        })

    candidates.sort(key=lambda c: -c["final_score"])
    for rank, c in enumerate(candidates, 1):
        c["rank"] = rank

    cand_path = OUTPUT_DIR / "final_drug_candidates.json"
    cand_path.write_text(json.dumps(candidates, indent=2))
    print(f"  Saved -> {cand_path}")

    # ── Step 8: Report ────────────────────────────────────────────────────────
    print("\n[8/8] Writing experiment report...")
    rep_path = OUTPUT_DIR / "qml_experiment_report.txt"
    write_report(rep_path,
                 n_train=len(X_qml_tr),
                 n_val=len(X_qml_val),
                 qml_metrics=qml_val_metrics,
                 classical_metrics=classical_metrics,
                 classical_metrics_small=classical_metrics_small,
                 cv_results=cv_results,
                 vqc_cv=vqc_cv,
                 candidates=candidates,
                 train_losses=train_losses,
                 val_losses=val_losses)
    print(f"  Saved -> {rep_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("  Phase 6 Summary")
    print("=" * 72)
    print(f"\n  MiBIG training BGCs : {len(ids)}")
    if qml_val_metrics:
        print(f"  VQC accuracy        : {qml_val_metrics['accuracy']:.3f}")
        print(f"  VQC ROC-AUC         : {qml_val_metrics['roc_auc']:.3f}")
    for m, s in classical_metrics.items():
        print(f"  {m:<22}  acc={s['accuracy']:.3f}  auc={s['roc_auc']:.3f}")

    print(f"\n  Top 5 Drug Candidates:")
    print(f"  {'VBGC':<12} {'Class':<30} {'Novelty':>8} "
          f"{'QML_P':>7} {'Score':>8}  GCF")
    print("  " + "─" * 78)
    for c in candidates[:5]:
        print(f"  {c['vbgc_id']:<12} {c['bgc_class']:<30} "
              f"{c['novelty_score']:>8.2f} {c['qml_probability']:>7.4f} "
              f"{c['final_score']:>8.3f}  {c['gcf_family']}")

    print("\n  Output files:")
    for p in sorted(OUTPUT_DIR.glob("*")):
        print(f"    {p.name:45s} {p.stat().st_size:>8,} bytes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
