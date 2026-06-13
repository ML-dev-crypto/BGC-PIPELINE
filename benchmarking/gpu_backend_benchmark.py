"""
GPU + Backend Benchmark
Measures: default.qubit CPU, lightning.qubit CPU, lightning.qubit GPU (via torch+cuda)
"""
import sys, time
sys.path.insert(0, 'scripts')

import numpy as np
import torch
import pennylane as qml
import json
from pathlib import Path

print("=" * 60)
print("  BGC-QDR Backend Benchmark")
print("=" * 60)
print(f"  PyTorch : {torch.__version__}")
print(f"  CUDA    : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"  GPU     : {torch.cuda.get_device_name(0)}")
print(f"  PL      : {qml.__version__}")
print()

np.random.seed(42)
N_SAMPLES  = 50
N_Q, N_L   = 6, 3
EPOCHS     = 8
BATCH      = 5
LR         = 0.02
N_FEATURES = N_Q

X   = np.random.randn(N_SAMPLES, N_FEATURES).astype(np.float64)
y   = np.random.randint(0, 2, N_SAMPLES)
X_v = np.random.randn(20, N_FEATURES).astype(np.float64)
y_v = np.random.randint(0, 2, 20)


def run_benchmark(backend: str, use_cuda: bool) -> dict:
    device = torch.device("cuda" if use_cuda and torch.cuda.is_available() else "cpu")
    label  = f"{backend} ({'GPU' if device.type == 'cuda' else 'CPU'})"
    print(f"  Testing {label} ...", end="", flush=True)

    try:
        dev = qml.device(backend, wires=N_Q)

        @qml.qnode(dev, interface="torch", diff_method="backprop")
        def circuit(weights, x):
            qml.templates.AngleEmbedding(x[:N_Q], wires=range(N_Q), rotation="Y")
            qml.templates.StronglyEntanglingLayers(weights, wires=range(N_Q))
            return qml.expval(qml.PauliZ(0))

        shape   = qml.templates.StronglyEntanglingLayers.shape(n_layers=N_L, n_wires=N_Q)
        rng_np  = np.random.default_rng(42)
        weights = torch.nn.Parameter(
            torch.tensor(rng_np.uniform(-np.pi / 4, np.pi / 4, shape),
                         dtype=torch.float64, device=device))
        opt = torch.optim.Adam([weights], lr=LR)

        t0 = time.time()
        for _ in range(EPOCHS):
            idx = np.random.permutation(N_SAMPLES)
            for start in range(0, N_SAMPLES, BATCH):
                bidx = idx[start: start + BATCH]
                X_b  = torch.tensor(X[bidx], dtype=torch.float64, device=device)
                y_b  = torch.tensor(y[bidx].astype(np.float64),
                                    dtype=torch.float64, device=device)
                opt.zero_grad()
                raw  = torch.stack([circuit(weights, x) for x in X_b])
                loss = torch.nn.functional.binary_cross_entropy_with_logits(raw, y_b)
                loss.backward()
                opt.step()
        elapsed = time.time() - t0

        # Quick accuracy check
        with torch.no_grad():
            X_vt  = torch.tensor(X_v, dtype=torch.float64, device=device)
            probs = torch.sigmoid(torch.stack([circuit(weights, x) for x in X_vt]))
            acc   = float((probs.cpu().numpy() > 0.5) == y_v).mean() if len(y_v) > 0 else 0.0
            acc   = float(np.mean((probs.cpu().numpy() > 0.5) == y_v))

        print(f"  {elapsed:.2f}s  acc≈{acc:.2f}")
        return {"backend": label, "time_s": round(elapsed, 3),
                "acc": round(acc, 3), "epochs": EPOCHS,
                "n_train": N_SAMPLES, "device": device.type, "ok": True}

    except Exception as exc:
        print(f"  FAILED: {exc}")
        return {"backend": label, "error": str(exc), "ok": False}


results = []

# 1. default.qubit on CPU (baseline)
results.append(run_benchmark("default.qubit", use_cuda=False))

# 2. lightning.qubit on CPU (C++ kernel speedup)
results.append(run_benchmark("lightning.qubit", use_cuda=False))

# 3. lightning.qubit with GPU tensors (best we can do without lightning.gpu)
#    Note: lightning.qubit itself is CPU-only simulator but torch tensors
#    will move to GPU for the backprop graph portions
if torch.cuda.is_available():
    results.append(run_benchmark("lightning.qubit", use_cuda=True))

# 4. Try lightning.gpu if available
if torch.cuda.is_available():
    try:
        import pennylane_lightning
        results.append(run_benchmark("lightning.gpu", use_cuda=True))
    except Exception:
        print("  lightning.gpu: not installed (pip install pennylane-lightning-gpu)")

print()
print("  Results summary:")
print(f"  {'Backend':<35} {'Time(s)':>8}  {'Device':>6}")
print("  " + "-" * 55)
for r in results:
    if r.get("ok"):
        print(f"  {r['backend']:<35} {r['time_s']:>8.2f}  {r['device']:>6}")
    else:
        print(f"  {r['backend']:<35} {'ERROR':>8}")

# Speedup vs baseline
base = next((r["time_s"] for r in results if "default.qubit" in r["backend"] and r.get("ok")), None)
if base:
    print()
    print("  Speedups vs default.qubit CPU:")
    for r in results[1:]:
        if r.get("ok"):
            sp = base / r["time_s"]
            print(f"    {r['backend']:<35} {sp:.2f}x")

out = Path("ablation_results")
out.mkdir(exist_ok=True)
(out / "gpu_benchmark.json").write_text(json.dumps({"results": results, "baseline_s": base}, indent=2))
print()
print(f"  Saved → ablation_results/gpu_benchmark.json")
