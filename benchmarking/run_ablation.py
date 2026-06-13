"""
BGC-QDR Research Ablation & Benchmark Suite
============================================
Runs all experiments needed for publication:

  1. GPU detection and speedup benchmark
  2. Stratified 5-fold cross-validation (VQC + all classical baselines)
  3. Architecture ablation: qubits × layers grid search
  4. Classical baseline comparison with full metrics + confusion matrices
  5. Feature importance analysis
  6. Statistical significance testing (Wilcoxon)

Usage:
    python benchmarking/run_ablation.py --mibig-dir mibig_gbk_4.0 --output ablation_results
    python benchmarking/run_ablation.py --mibig-dir mibig_gbk_4.0 --output ablation_results --skip-vqc-ablation
    python benchmarking/run_ablation.py --mibig-dir mibig_gbk_4.0 --output ablation_results --cv-only

Outputs (in --output dir):
    gpu_benchmark.json
    cv_results.json               ← 5-fold CV for all models
    ablation_architecture.json    ← qubit/layer grid
    classical_comparison.json     ← full metrics + confusion matrices
    feature_importance.json
    statistical_tests.json
    ablation_report.txt           ← human-readable summary
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path
from collections import Counter

import numpy as np

warnings.filterwarnings("ignore")

# ── project root on path ──────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# ── optional deps ─────────────────────────────────────────────────────────────
try:
    import torch
    TORCH_OK = True
    CUDA_OK  = torch.cuda.is_available()
    DEVICE   = torch.device("cuda" if CUDA_OK else "cpu")
    GPU_NAME = torch.cuda.get_device_name(0) if CUDA_OK else "N/A"
except ImportError:
    TORCH_OK = CUDA_OK = False
    DEVICE   = None
    GPU_NAME = "N/A"

try:
    import pennylane as qml
    from pennylane import numpy as anp
    PENNYLANE_OK = True
except ImportError:
    PENNYLANE_OK = False

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score,
        roc_auc_score, f1_score, confusion_matrix,
        classification_report,
    )
    from sklearn.model_selection import StratifiedKFold, train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.inspection import permutation_importance
    SKLEARN_OK = True
except ImportError:
    SKLEARN_OK = False

try:
    from xgboost import XGBClassifier
    XGBOOST_OK = True
except ImportError:
    XGBOOST_OK = False

try:
    from Bio import SeqIO
    BIO_OK = True
except ImportError:
    BIO_OK = False

try:
    from scipy.stats import wilcoxon, mannwhitneyu
    SCIPY_OK = True
except ImportError:
    SCIPY_OK = False

# ── import the shared MiBIG parsing from vqc_ranking ─────────────────────────
from vqc_ranking import (
    _parse_mibig,
    _build_vqc,
    _train_vqc,
    _evaluate_vqc,
    _normalise,
    _scale_with_stats,
    N_QUBITS, N_LAYERS, EPOCHS, BATCH_SIZE, LR,
    FEATURE_DOMAINS, STRUCT_FEATURES, BIO_EXTRA_FEATURES,
    ALL_FEATURES, N_FEATURES,
)

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)


# ─────────────────────────────────────────────────────────────────────────────
# 1. GPU Benchmark
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_gpu(X_tr: np.ndarray, y_tr: np.ndarray,
                  X_val: np.ndarray, y_val: np.ndarray,
                  output_dir: Path) -> dict:
    """
    Compare CPU vs GPU training time for the VQC.
    RTX 2050 note: default.qubit is a CPU simulator — the GPU speedup comes
    from the PyTorch backprop graph, not quantum hardware acceleration.
    lightning.gpu requires NVIDIA CUDA Toolkit + pennylane-lightning-gpu.
    """
    results: dict = {
        "cuda_available": CUDA_OK,
        "gpu_name": GPU_NAME,
        "torch_version": torch.__version__ if TORCH_OK else "N/A",
        "pennylane_version": qml.__version__ if PENNYLANE_OK else "N/A",
        "benchmarks": [],
    }

    if not PENNYLANE_OK:
        print("  [GPU] PennyLane not available — skipping GPU benchmark")
        return results

    # Prep data (small subset for timing)
    X_t = X_tr[:50]
    y_t = y_tr[:50]
    X_v = X_val[:20]
    y_v = y_val[:20]

    backends = ["default.qubit"]

    # Try lightning.qubit (faster CPU simulator, no GPU needed)
    try:
        dev_test = qml.device("lightning.qubit", wires=N_QUBITS)
        backends.append("lightning.qubit")
        print("  [GPU] lightning.qubit available ✓")
    except Exception:
        print("  [GPU] lightning.qubit not available — install pennylane-lightning")

    # Try lightning.gpu (requires NVIDIA GPU + pennylane-lightning-gpu)
    if CUDA_OK:
        try:
            dev_test = qml.device("lightning.gpu", wires=N_QUBITS)
            backends.append("lightning.gpu")
            print(f"  [GPU] lightning.gpu available on {GPU_NAME} ✓")
        except Exception:
            print(f"  [GPU] lightning.gpu not available — install pennylane-lightning-gpu")
            print(f"        pip install pennylane-lightning-gpu")

    for backend in backends:
        print(f"  [GPU] Benchmarking {backend} ...")
        try:
            t0 = time.time()
            circuit, weights = _build_vqc_with_backend(backend)
            best_w, _, _ = _train_vqc(circuit, weights, X_t, y_t, X_v, y_v)
            elapsed = round(time.time() - t0, 2)
            metrics = _evaluate_vqc(circuit, best_w, X_v, y_v)
            results["benchmarks"].append({
                "backend": backend,
                "time_s":  elapsed,
                "acc":     round(metrics["accuracy"], 4),
                "auc":     round(metrics["roc_auc"], 4),
                "n_train": len(X_t),
            })
            print(f"  [GPU] {backend}: {elapsed}s  acc={metrics['accuracy']:.3f}")
        except Exception as exc:
            print(f"  [GPU] {backend} failed: {exc}")
            results["benchmarks"].append({
                "backend": backend,
                "error":   str(exc),
            })

    # Compute speedup
    times = {b["backend"]: b["time_s"]
             for b in results["benchmarks"] if "time_s" in b}
    if "default.qubit" in times and "lightning.qubit" in times:
        results["lightning_qubit_speedup"] = round(
            times["default.qubit"] / times["lightning.qubit"], 2)
    if "default.qubit" in times and "lightning.gpu" in times:
        results["lightning_gpu_speedup"] = round(
            times["default.qubit"] / times["lightning.gpu"], 2)

    out = output_dir / "gpu_benchmark.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"  [GPU] Results → {out}")
    return results


def _build_vqc_with_backend(backend: str):
    """Build a VQC circuit using a specific PennyLane backend."""
    dev = qml.device(backend, wires=N_QUBITS)

    if TORCH_OK:
        @qml.qnode(dev, interface="torch", diff_method="backprop")
        def circuit(weights, x):
            qml.templates.AngleEmbedding(
                x[:N_QUBITS], wires=range(N_QUBITS), rotation="Y")
            qml.templates.StronglyEntanglingLayers(
                weights, wires=range(N_QUBITS))
            return qml.expval(qml.PauliZ(0))

        shape  = qml.templates.StronglyEntanglingLayers.shape(
            n_layers=N_LAYERS, n_wires=N_QUBITS)
        rng    = np.random.default_rng(RANDOM_SEED)
        init   = torch.tensor(
            rng.uniform(-np.pi / 4, np.pi / 4, shape),
            dtype=torch.float64, device=DEVICE)
        weights = torch.nn.Parameter(init)
    else:
        @qml.qnode(dev, interface="autograd")
        def circuit(weights, x):
            qml.templates.AngleEmbedding(
                x[:N_QUBITS], wires=range(N_QUBITS), rotation="Y")
            qml.templates.StronglyEntanglingLayers(
                weights, wires=range(N_QUBITS))
            return qml.expval(qml.PauliZ(0))

        shape  = qml.templates.StronglyEntanglingLayers.shape(
            n_layers=N_LAYERS, n_wires=N_QUBITS)
        rng    = np.random.default_rng(RANDOM_SEED)
        weights = anp.array(
            rng.uniform(-np.pi / 4, np.pi / 4, shape),
            requires_grad=True)

    return circuit, weights


# ─────────────────────────────────────────────────────────────────────────────
# 2. Stratified 5-fold Cross-Validation
# ─────────────────────────────────────────────────────────────────────────────

def run_cv(X: np.ndarray, y: np.ndarray,
           output_dir: Path,
           n_folds: int = 5,
           run_vqc: bool = True,
           qml_train_limit: int = 250) -> dict:
    """
    Stratified k-fold CV for VQC and all classical baselines.
    Uses PCA preprocessing identical to vqc_ranking.py so comparison is fair.
    """
    from sklearn.model_selection import StratifiedKFold
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True,
                          random_state=RANDOM_SEED)

    print(f"\n  [CV] Stratified {n_folds}-fold CV on {len(X)} BGCs ...")
    print(f"  [CV] Class balance: active={y.sum()}/{len(y)} ({100*y.mean():.1f}%)")

    # Classical model factories — all trained on raw features with StandardScaler
    def _make_models(y_tr):
        models = {
            "LogisticRegression": LogisticRegression(
                max_iter=1000, class_weight="balanced",
                random_state=RANDOM_SEED, C=1.0),
            "RandomForest": RandomForestClassifier(
                n_estimators=200, max_depth=10,
                class_weight="balanced", n_jobs=-1,
                random_state=RANDOM_SEED),
            "MLP": MLPClassifier(
                hidden_layer_sizes=(128, 64, 32), max_iter=500,
                random_state=RANDOM_SEED, early_stopping=True,
                validation_fraction=0.1),
        }
        if XGBOOST_OK:
            pos = float(y_tr.sum())
            neg = float(len(y_tr) - pos)
            models["XGBoost"] = XGBClassifier(
                n_estimators=300, max_depth=6,
                learning_rate=0.05, subsample=0.9,
                colsample_bytree=0.9, objective="binary:logistic",
                scale_pos_weight=neg / pos if pos > 0 else 1.0,
                random_state=RANDOM_SEED, n_jobs=-1,
                tree_method="hist", verbosity=0)
        return models

    # Collect per-fold metrics for every model
    fold_metrics: dict[str, list[dict]] = {}

    for fold_idx, (tr_idx, va_idx) in enumerate(skf.split(X, y), 1):
        X_tr_f, X_va_f = X[tr_idx], X[va_idx]
        y_tr_f, y_va_f = y[tr_idx], y[va_idx]

        print(f"\n  [CV] Fold {fold_idx}/{n_folds}  "
              f"train={len(X_tr_f)}  val={len(X_va_f)}")

        # ── Classical models ─────────────────────────────────────────────────
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr_f)
        X_va_s = scaler.transform(X_va_f)

        for name, model in _make_models(y_tr_f).items():
            t0 = time.time()
            model.fit(X_tr_s, y_tr_f)
            probs = model.predict_proba(X_va_s)[:, 1]
            preds = (probs > 0.5).astype(int)
            elapsed = round(time.time() - t0, 3)

            m = _metrics(y_va_f, preds, probs, elapsed)
            fold_metrics.setdefault(name, []).append(m)
            print(f"    {name:<22}  "
                  f"acc={m['accuracy']:.3f}  auc={m['roc_auc']:.3f}  "
                  f"f1={m['f1']:.3f}  t={elapsed}s")

        # ── VQC ──────────────────────────────────────────────────────────────
        if run_vqc and PENNYLANE_OK:
            # Subsample for VQC (tractable)
            if len(X_tr_f) > qml_train_limit:
                idx_sub = np.random.default_rng(fold_idx).choice(
                    len(X_tr_f), qml_train_limit, replace=False)
                X_qml_tr = X_tr_f[idx_sub]
                y_qml_tr = y_tr_f[idx_sub]
            else:
                X_qml_tr, y_qml_tr = X_tr_f, y_tr_f

            val_limit = 80
            if len(X_va_f) > val_limit:
                idx_sub = np.random.default_rng(fold_idx + 100).choice(
                    len(X_va_f), val_limit, replace=False)
                X_qml_val = X_va_f[idx_sub]
                y_qml_val = y_va_f[idx_sub]
            else:
                X_qml_val, y_qml_val = X_va_f, y_va_f

            # PCA 17 → N_QUBITS
            scaler_pca = StandardScaler()
            scaler_pca.fit(X_tr_f)
            pca = PCA(n_components=N_QUBITS, random_state=RANDOM_SEED)
            pca.fit(scaler_pca.transform(X_tr_f))

            (X_tr_n, X_va_n), _, _ = _normalise(
                pca.transform(scaler_pca.transform(X_qml_tr)),
                pca.transform(scaler_pca.transform(X_qml_val)),
            )

            t0 = time.time()
            circuit, weights = _build_vqc()
            best_w, _, _ = _train_vqc(
                circuit, weights, X_tr_n, y_qml_tr, X_va_n, y_qml_val)
            vqc_m = _evaluate_vqc(circuit, best_w, X_va_n, y_qml_val)
            elapsed = round(time.time() - t0, 3)

            preds = (np.array(vqc_m["probs"]) > 0.5).astype(int)
            m = _metrics(y_qml_val, preds,
                         np.array(vqc_m["probs"]), elapsed)
            fold_metrics.setdefault("VQC_PennyLane", []).append(m)
            print(f"    {'VQC_PennyLane':<22}  "
                  f"acc={m['accuracy']:.3f}  auc={m['roc_auc']:.3f}  "
                  f"f1={m['f1']:.3f}  t={elapsed}s")

    # ── Aggregate across folds ────────────────────────────────────────────────
    cv_summary: dict = {}
    for model_name, fold_list in fold_metrics.items():
        keys = ["accuracy", "precision", "recall", "f1", "roc_auc"]
        agg = {}
        for k in keys:
            vals = [f[k] for f in fold_list if k in f]
            if vals:
                mean = float(np.mean(vals))
                std  = float(np.std(vals))
                ci   = 1.96 * std / np.sqrt(len(vals))
                agg[k] = {
                    "mean":  round(mean, 4),
                    "std":   round(std,  4),
                    "ci_lo": round(mean - ci, 4),
                    "ci_hi": round(mean + ci, 4),
                }
        cv_summary[model_name] = {
            "n_folds":     n_folds,
            "metrics":     agg,
            "fold_detail": fold_list,
        }

    # ── Statistical significance (Wilcoxon signed-rank) ─────────────────────
    sig_tests: dict = {}
    if SCIPY_OK and "VQC_PennyLane" in fold_metrics:
        vqc_aucs = [f["roc_auc"] for f in fold_metrics["VQC_PennyLane"]]
        for name, folds in fold_metrics.items():
            if name == "VQC_PennyLane":
                continue
            other_aucs = [f["roc_auc"] for f in folds]
            min_len    = min(len(vqc_aucs), len(other_aucs))
            if min_len < 2:
                continue
            try:
                stat, p = wilcoxon(
                    vqc_aucs[:min_len], other_aucs[:min_len])
                sig_tests[f"VQC_vs_{name}"] = {
                    "statistic": round(float(stat), 4),
                    "p_value":   round(float(p),    6),
                    "significant_p05": bool(p < 0.05),
                }
            except Exception:
                pass

    result = {
        "n_folds":       n_folds,
        "n_samples":     int(len(X)),
        "class_balance": {"active": int(y.sum()),
                          "inactive": int(len(y) - y.sum())},
        "cv_summary":    cv_summary,
        "significance":  sig_tests,
    }

    out = output_dir / "cv_results.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\n  [CV] Results → {out}")
    _print_cv_table(cv_summary)
    return result


def _metrics(y_true, y_pred, y_prob, elapsed: float) -> dict:
    return {
        "accuracy":  round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(
                           y_true, y_pred, zero_division=0)), 4),
        "recall":    round(float(recall_score(
                           y_true, y_pred, zero_division=0)), 4),
        "f1":        round(float(f1_score(
                           y_true, y_pred, zero_division=0)), 4),
        "roc_auc":   round(float(roc_auc_score(y_true, y_prob))
                           if len(np.unique(y_true)) > 1 else 0.0, 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "time_s":    elapsed,
    }


def _print_cv_table(cv_summary: dict) -> None:
    print(f"\n  {'Model':<26} {'Accuracy':>12} {'ROC-AUC':>12} "
          f"{'F1':>12} {'Precision':>12} {'Recall':>12}")
    print("  " + "─" * 88)
    for name, data in sorted(cv_summary.items()):
        m = data["metrics"]
        def _fmt(k):
            if k not in m:
                return "    N/A     "
            return f"{m[k]['mean']:.3f}±{m[k]['std']:.3f}"
        print(f"  {name:<26} {_fmt('accuracy'):>12} {_fmt('roc_auc'):>12} "
              f"{_fmt('f1'):>12} {_fmt('precision'):>12} {_fmt('recall'):>12}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Architecture Ablation: qubits × layers
# ─────────────────────────────────────────────────────────────────────────────

def run_architecture_ablation(
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    output_dir: Path,
) -> dict:
    """
    Grid search over (n_qubits, n_layers) to find the config that
    maximises ROC-AUC rather than accuracy.
    """
    if not PENNYLANE_OK:
        print("  [ABL] PennyLane not available — skipping ablation")
        return {}

    qubit_configs = [4, 6, 8]
    layer_configs = [2, 3, 4]
    results       = []

    print(f"\n  [ABL] Architecture ablation: "
          f"{len(qubit_configs)} × {len(layer_configs)} = "
          f"{len(qubit_configs)*len(layer_configs)} configs")

    for n_q in qubit_configs:
        for n_l in layer_configs:
            n_params = n_q * n_l * 3
            print(f"\n  [ABL] Config: {n_q}q × {n_l}L ({n_params} params) ...")

            # PCA to n_q dimensions
            scaler_pca = StandardScaler()
            scaler_pca.fit(X_tr)
            pca = PCA(n_components=n_q, random_state=RANDOM_SEED)
            pca.fit(scaler_pca.transform(X_tr))

            (X_tr_n, X_va_n), _, _ = _normalise(
                pca.transform(scaler_pca.transform(X_tr)),
                pca.transform(scaler_pca.transform(X_val)),
            )
            pca_var = float(pca.explained_variance_ratio_.sum())

            # Build circuit for this config
            try:
                circuit, weights = _build_vqc_config(n_q, n_l)
                t0 = time.time()
                best_w, tl, vl = _train_vqc_config(
                    circuit, weights, X_tr_n, y_tr, X_va_n, y_val,
                    n_q, n_l)
                elapsed = round(time.time() - t0, 2)
                metrics = _evaluate_vqc(circuit, best_w, X_va_n, y_val)

                entry = {
                    "n_qubits":    n_q,
                    "n_layers":    n_l,
                    "n_params":    n_params,
                    "pca_variance": round(pca_var, 4),
                    "accuracy":    round(metrics["accuracy"], 4),
                    "roc_auc":     round(metrics["roc_auc"], 4),
                    "precision":   round(metrics["precision"], 4),
                    "recall":      round(metrics["recall"], 4),
                    "time_s":      elapsed,
                    "final_train_loss": round(float(tl[-1]), 4) if tl else None,
                    "final_val_loss":   round(float(vl[-1]), 4) if vl else None,
                }
                results.append(entry)
                print(f"  [ABL] {n_q}q × {n_l}L  "
                      f"auc={metrics['roc_auc']:.3f}  "
                      f"acc={metrics['accuracy']:.3f}  "
                      f"t={elapsed}s")
            except Exception as exc:
                print(f"  [ABL] {n_q}q × {n_l}L FAILED: {exc}")
                results.append({
                    "n_qubits": n_q, "n_layers": n_l,
                    "error": str(exc)})

    # Sort by ROC-AUC descending
    valid   = [r for r in results if "roc_auc" in r]
    invalid = [r for r in results if "roc_auc" not in r]
    results = sorted(valid, key=lambda r: -r["roc_auc"]) + invalid

    ablation_result = {
        "best_config_by_roc_auc": results[0] if valid else None,
        "all_configs":            results,
    }

    out = output_dir / "ablation_architecture.json"
    out.write_text(json.dumps(ablation_result, indent=2))
    print(f"\n  [ABL] Results → {out}")

    if valid:
        best = results[0]
        print(f"  [ABL] Best: {best['n_qubits']}q × {best['n_layers']}L  "
              f"auc={best['roc_auc']:.3f}  acc={best['accuracy']:.3f}")

    return ablation_result


def _build_vqc_config(n_q: int, n_l: int):
    """Build a VQC circuit for a specific qubit/layer count.
    Delegates to _build_vqc so the ablation uses the same auto-detected
    backend (lightning.qubit / lightning.gpu) as the main training path.
    """
    return _build_vqc(n_qubits=n_q, n_layers=n_l)


def _train_vqc_config(circuit, weights,
                      X_tr, y_tr, X_val, y_val,
                      n_q: int, n_l: int):
    """Thin wrapper — reuses _train_vqc from vqc_ranking with local n_q/n_l."""
    import vqc_ranking as vr
    old_q, old_l = vr.N_QUBITS, vr.N_LAYERS
    vr.N_QUBITS  = n_q
    vr.N_LAYERS  = n_l
    try:
        result = _train_vqc(circuit, weights, X_tr, y_tr, X_val, y_val)
    finally:
        vr.N_QUBITS = old_q
        vr.N_LAYERS = old_l
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. Classical Baseline Full Comparison
# ─────────────────────────────────────────────────────────────────────────────

def run_classical_comparison(
    X: np.ndarray, y: np.ndarray,
    output_dir: Path,
    n_folds: int = 5,
) -> dict:
    """
    Full classical baseline comparison with confusion matrices,
    feature importance, and publication-ready table.
    Includes LogisticRegression which phase6 was missing.
    """
    from sklearn.model_selection import StratifiedKFold
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True,
                          random_state=RANDOM_SEED)

    print(f"\n  [CLS] Classical baseline {n_folds}-fold CV ...")

    feature_names = ALL_FEATURES  # 20 features: 15 domain + 2 structural + 3 bio

    def _make_classifiers(y_tr):
        pos = float(y_tr.sum())
        neg = float(len(y_tr) - pos)
        clf = {
            "LogisticRegression": LogisticRegression(
                max_iter=2000, class_weight="balanced",
                random_state=RANDOM_SEED, C=1.0, solver="lbfgs"),
            "RandomForest": RandomForestClassifier(
                n_estimators=300, max_depth=12,
                class_weight="balanced", n_jobs=-1,
                random_state=RANDOM_SEED),
            "MLP": MLPClassifier(
                hidden_layer_sizes=(128, 64, 32),
                max_iter=500, random_state=RANDOM_SEED,
                early_stopping=True, validation_fraction=0.1,
                learning_rate_init=0.001),
        }
        if XGBOOST_OK:
            clf["XGBoost"] = XGBClassifier(
                n_estimators=300, max_depth=6,
                learning_rate=0.05, subsample=0.9,
                colsample_bytree=0.9, objective="binary:logistic",
                scale_pos_weight=neg / pos if pos > 0 else 1.0,
                random_state=RANDOM_SEED, n_jobs=-1,
                tree_method="hist", verbosity=0)
        return clf

    fold_metrics: dict[str, list[dict]] = {}
    rf_importances: list[np.ndarray]    = []

    for fold_idx, (tr_idx, va_idx) in enumerate(skf.split(X, y), 1):
        X_tr_f, X_va_f = X[tr_idx], X[va_idx]
        y_tr_f, y_va_f = y[tr_idx], y[va_idx]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr_f)
        X_va_s = scaler.transform(X_va_f)

        for name, model in _make_classifiers(y_tr_f).items():
            t0 = time.time()
            model.fit(X_tr_s, y_tr_f)
            probs   = model.predict_proba(X_va_s)[:, 1]
            preds   = (probs > 0.5).astype(int)
            elapsed = round(time.time() - t0, 3)
            m       = _metrics(y_va_f, preds, probs, elapsed)
            fold_metrics.setdefault(name, []).append(m)

            # Collect RF feature importances
            if name == "RandomForest" and hasattr(model, "feature_importances_"):
                rf_importances.append(model.feature_importances_)

    # Aggregate
    comparison: dict = {}
    for name, folds in fold_metrics.items():
        keys = ["accuracy", "precision", "recall", "f1", "roc_auc"]
        agg  = {}
        for k in keys:
            vals = [f[k] for f in folds]
            mean = float(np.mean(vals))
            std  = float(np.std(vals))
            ci   = 1.96 * std / np.sqrt(len(vals))
            agg[k] = {"mean": round(mean,4), "std": round(std,4),
                      "ci_lo": round(mean-ci,4), "ci_hi": round(mean+ci,4)}
        # Average confusion matrix
        cms = [np.array(f["confusion_matrix"]) for f in folds]
        avg_cm = np.mean(cms, axis=0).round(1).tolist()
        comparison[name] = {"metrics": agg, "avg_confusion_matrix": avg_cm,
                            "n_folds": n_folds}

    # Feature importance from RF
    feat_importance: dict = {}
    if rf_importances:
        mean_imp = np.mean(rf_importances, axis=0)
        std_imp  = np.std(rf_importances,  axis=0)
        feat_importance = {
            feature_names[i]: {
                "mean": round(float(mean_imp[i]), 5),
                "std":  round(float(std_imp[i]),  5),
            }
            for i in np.argsort(mean_imp)[::-1]
        }

    result = {
        "n_folds":           n_folds,
        "models":            comparison,
        "feature_importance": feat_importance,
    }

    out = output_dir / "classical_comparison.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\n  [CLS] Results → {out}")
    _print_cv_table({k: v for k, v in comparison.items()})
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 5. Write publication-ready text report
# ─────────────────────────────────────────────────────────────────────────────

def write_ablation_report(
    output_dir: Path,
    gpu_result: dict,
    cv_result: dict,
    ablation_result: dict,
    classical_result: dict,
    n_mibig: int,
    elapsed_total: float,
) -> None:
    lines = [
        "=" * 72,
        "  BGC-QDR Research Ablation Report",
        f"  Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 72,
        "",
        "── 1. Hardware & Environment ──────────────────────────────────────",
        f"  CUDA available : {gpu_result.get('cuda_available')}",
        f"  GPU            : {gpu_result.get('gpu_name')}",
        f"  PyTorch        : {gpu_result.get('torch_version')}",
        f"  PennyLane      : {gpu_result.get('pennylane_version')}",
    ]

    if gpu_result.get("benchmarks"):
        lines += ["", "  Backend timing (50-sample subset):"]
        for b in gpu_result["benchmarks"]:
            if "error" in b:
                lines.append(f"    {b['backend']:<20} ERROR: {b['error']}")
            else:
                lines.append(f"    {b['backend']:<20} {b['time_s']:>8.1f}s  "
                             f"acc={b['acc']:.3f}  auc={b['auc']:.3f}")
        if "lightning_qubit_speedup" in gpu_result:
            lines.append(f"\n  lightning.qubit speedup vs default.qubit: "
                        f"{gpu_result['lightning_qubit_speedup']}×")
        if "lightning_gpu_speedup" in gpu_result:
            lines.append(f"  lightning.gpu speedup vs default.qubit: "
                        f"{gpu_result['lightning_gpu_speedup']}×")

    lines += [
        "",
        f"── 2. Stratified {cv_result.get('n_folds',5)}-Fold Cross-Validation ──────────────────────────",
        f"  Dataset: {n_mibig} MiBIG BGCs  "
        f"active={cv_result.get('class_balance',{}).get('active','?')}  "
        f"inactive={cv_result.get('class_balance',{}).get('inactive','?')}",
        "",
        f"  {'Model':<26} {'Accuracy':>14} {'ROC-AUC':>14} "
        f"{'F1':>10} {'Precision':>12} {'Recall':>10}",
        "  " + "─" * 88,
    ]

    cv_summary = cv_result.get("cv_summary", {})
    for name, data in sorted(cv_summary.items()):
        m = data.get("metrics", {})
        def _f(k):
            if k not in m: return "   N/A      "
            return f"{m[k]['mean']:.3f}±{m[k]['std']:.3f}"
        lines.append(f"  {name:<26} {_f('accuracy'):>14} {_f('roc_auc'):>14} "
                    f"{_f('f1'):>10} {_f('precision'):>12} {_f('recall'):>10}")

    sig = cv_result.get("significance", {})
    if sig:
        lines += ["", "  Statistical significance (Wilcoxon signed-rank on AUC):"]
        for test_name, res in sig.items():
            sig_str = "p<0.05 ✓" if res.get("significant_p05") else "n.s."
            lines.append(f"    {test_name:<40}  "
                        f"p={res['p_value']:.4f}  {sig_str}")

    if ablation_result.get("all_configs"):
        lines += [
            "",
            "── 3. Architecture Ablation (sorted by ROC-AUC) ─────────────────",
            f"  {'Config':<14} {'Params':>8} {'PCA var':>9} "
            f"{'Accuracy':>10} {'ROC-AUC':>10} {'Time(s)':>10}",
            "  " + "─" * 68,
        ]
        for c in ablation_result["all_configs"]:
            if "error" in c:
                lines.append(f"  {c['n_qubits']}q×{c['n_layers']}L  ERROR: {c['error']}")
            else:
                cfg = f"{c['n_qubits']}q × {c['n_layers']}L"
                lines.append(
                    f"  {cfg:<14} {c['n_params']:>8}  "
                    f"{c.get('pca_variance',0):.1%}  "
                    f"{c['accuracy']:>10.3f}  "
                    f"{c['roc_auc']:>10.3f}  "
                    f"{c.get('time_s',0):>10.1f}")

        if ablation_result.get("best_config_by_roc_auc"):
            b = ablation_result["best_config_by_roc_auc"]
            lines += [
                "",
                f"  → Best config: {b['n_qubits']} qubits × {b['n_layers']} layers  "
                f"({b['n_params']} params)  AUC={b['roc_auc']:.3f}",
                f"    Recommendation: use this config in paper Table 1",
            ]

    lines += [
        "",
        "── 4. Feature Importance (RandomForest, averaged over folds) ────",
    ]
    fi = classical_result.get("feature_importance", {})
    for feat, vals in list(fi.items())[:10]:
        lines.append(f"  {feat:<28}  {vals['mean']:.5f} ± {vals['std']:.5f}")

    lines += [
        "",
        "── 5. Recommendations for Paper ────────────────────────────────",
        "",
        "  CRITICAL (must fix before submission):",
        "  • Replace single-split results with 5-fold CV mean±std",
        "  • Report ROC-AUC as primary metric (not accuracy, due to 82% imbalance)",
        "  • Add statistical significance tests vs best classical baseline",
        "  • Add confusion matrices as supplementary figure",
        "",
        "  HIGH IMPACT:",
        "  • Use best qubit/layer config found in ablation (Section 3 above)",
        "  • Add LogisticRegression as baseline (reveals if problem is linearly separable)",
        "  • Report F1 score alongside AUC",
        "",
        "  MEDIUM IMPACT:",
        "  • Add domain entropy feature (captures BGC diversity)",
        "  • Add resistance gene count feature",
        "  • Add tailoring enzyme count (P450, glycosyltransferase, methyltransferase)",
        "",
        "  PIPELINE STRUCTURE FOR PAPER:",
        "  Recommended for IEEE TCBB / Bioinformatics:",
        "    QC → ORF Calling → Domain Annotation → Novelty Assessment → VQC Ranking",
        "  Graph reconstruction + GCF clustering → frame as future work",
        "  This is cleaner and more reviewable in 8–10 pages",
        "",
        f"  Total ablation runtime: {elapsed_total:.1f}s",
        "=" * 72,
    ]

    report_path = output_dir / "ablation_report.txt"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Report → {report_path}")
    print("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="BGC-QDR Ablation & Benchmark Suite")
    parser.add_argument("--mibig-dir",  required=True,
                        help="Path to mibig_gbk_4.0/")
    parser.add_argument("--output",     required=True,
                        help="Output directory for all results")
    parser.add_argument("--cv-folds",   type=int, default=5,
                        help="Number of CV folds (default: 5)")
    parser.add_argument("--skip-vqc-ablation", action="store_true",
                        help="Skip qubit/layer grid search (saves ~2h)")
    parser.add_argument("--skip-vqc-cv", action="store_true",
                        help="Skip VQC in CV (run classical only, much faster)")
    parser.add_argument("--cv-only",    action="store_true",
                        help="Run only 5-fold CV, skip ablation and GPU bench")
    parser.add_argument("--seed",       type=int, default=42)
    args = parser.parse_args()

    global RANDOM_SEED
    RANDOM_SEED = args.seed
    np.random.seed(RANDOM_SEED)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    mibig_dir  = Path(args.mibig_dir)

    t_total = time.time()

    # ── Load data once ────────────────────────────────────────────────────────
    if not BIO_OK:
        print("ERROR: biopython required — pip install biopython")
        return 1

    print(f"\n[1/5] Parsing MiBIG from {mibig_dir} ...")
    X, y, ids = _parse_mibig(mibig_dir)

    # Standard 85/15 split for ablation (same as vqc_ranking.py)
    from sklearn.model_selection import train_test_split
    X_tr, X_val, y_tr, y_val = train_test_split(
        X, y, test_size=0.15, random_state=RANDOM_SEED, stratify=y)

    # QML subset
    QML_TR = 250; QML_VA = 80
    if len(X_tr) > QML_TR:
        X_qml_tr, _, y_qml_tr, _ = train_test_split(
            X_tr, y_tr, train_size=QML_TR,
            random_state=RANDOM_SEED, stratify=y_tr)
    else:
        X_qml_tr, y_qml_tr = X_tr, y_tr

    if len(X_val) > QML_VA:
        X_qml_val, _, y_qml_val, _ = train_test_split(
            X_val, y_val, train_size=QML_VA,
            random_state=RANDOM_SEED, stratify=y_val)
    else:
        X_qml_val, y_qml_val = X_val, y_val

    from sklearn.preprocessing import StandardScaler
    sc  = StandardScaler()
    pca = PCA(n_components=N_QUBITS, random_state=RANDOM_SEED)
    pca.fit(sc.fit_transform(X_tr))
    (X_tr_n, X_va_n), _, _ = _normalise(
        pca.transform(sc.transform(X_qml_tr)),
        pca.transform(sc.transform(X_qml_val)),
    )

    gpu_result      = {}
    cv_result       = {}
    ablation_result = {}
    classical_result = {}

    # ── 1. GPU Benchmark ─────────────────────────────────────────────────────
    if not args.cv_only:
        print("\n[2/5] GPU / backend benchmark ...")
        gpu_result = benchmark_gpu(X_tr_n, y_qml_tr, X_va_n, y_qml_val,
                                   output_dir)

    # ── 2. CV ─────────────────────────────────────────────────────────────────
    print(f"\n[3/5] {args.cv_folds}-fold cross-validation ...")
    cv_result = run_cv(X, y, output_dir,
                       n_folds=args.cv_folds,
                       run_vqc=not args.skip_vqc_cv)

    # ── 3. Architecture ablation ─────────────────────────────────────────────
    if not args.cv_only and not args.skip_vqc_ablation:
        print("\n[4/5] Architecture ablation ...")
        ablation_result = run_architecture_ablation(
            X_qml_tr, y_qml_tr, X_qml_val, y_qml_val, output_dir)
    else:
        print("\n[4/5] Architecture ablation SKIPPED")

    # ── 4. Classical baselines ───────────────────────────────────────────────
    print("\n[5/5] Classical baseline comparison ...")
    classical_result = run_classical_comparison(X, y, output_dir,
                                                n_folds=args.cv_folds)

    # ── 5. Report ─────────────────────────────────────────────────────────────
    elapsed = round(time.time() - t_total, 1)
    write_ablation_report(
        output_dir, gpu_result, cv_result,
        ablation_result, classical_result,
        n_mibig=len(X), elapsed_total=elapsed)

    print(f"\n[DONE] Total runtime: {elapsed}s")
    print(f"       Results in: {output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
