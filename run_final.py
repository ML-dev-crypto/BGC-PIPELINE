"""
Complete pipeline runner:
1. Wait for WSL to be available
2. Check/fix Pfam index on native WSL filesystem
3. Run the BGC pipeline
"""
import subprocess, time, sys, os

PFAM_NATIVE = "/root/bgc_work/pfam_data/Pfam-A.hmm"
PFAM_H3I    = "/root/bgc_work/pfam_data/Pfam-A.hmm.h3i"

def wsl(cmd, timeout=30):
    """Run a single WSL command using wsl -- syntax (no bash -c)."""
    return subprocess.run(
        ['wsl', '--'] + cmd.split(),
        capture_output=True, text=True, timeout=timeout
    )

def wsl_check_file_size(path, timeout=15):
    """Return file size in bytes, 0 if missing."""
    r = subprocess.run(
        ['wsl', '--', 'wc', '-c', path],
        capture_output=True, text=True, timeout=timeout
    )
    try:
        return int(r.stdout.strip().split()[0])
    except (ValueError, IndexError):
        return 0

# ── Step 1: wait for WSL ──────────────────────────────────────────────
print("Waiting for WSL...", flush=True)
for i in range(20):
    try:
        r = subprocess.run(
            ['wsl', '--', 'echo', 'ok'],
            capture_output=True, text=True, timeout=10
        )
        if "ok" in r.stdout:
            print(f"WSL ready (attempt {i+1})")
            break
    except subprocess.TimeoutExpired:
        print(f"  [{i*5}s] WSL starting up...", flush=True)
        time.sleep(5)
else:
    print("ERROR: WSL not responding after 100s")
    sys.exit(1)

# ── Step 2: check h3i ────────────────────────────────────────────────
print("\nChecking Pfam index...", flush=True)
h3i_size = wsl_check_file_size(PFAM_H3I)
print(f"  h3i size: {h3i_size} bytes")

if h3i_size == 0:
    print("  h3i is empty — running hmmpress on native filesystem...")
    r = subprocess.run(
        ['wsl', '--', 'hmmpress', '-f', PFAM_NATIVE],
        capture_output=True, text=True, timeout=600
    )
    print(f"  hmmpress stdout: {r.stdout[-300:]}")
    h3i_size = wsl_check_file_size(PFAM_H3I)
    print(f"  h3i after press: {h3i_size} bytes")
else:
    print("  [OK] Pfam index is ready")

# ── Step 3: run pipeline ─────────────────────────────────────────────
print("\nRunning BGC-QDR pipeline...", flush=True)
result = subprocess.run(
    ['python', 'scripts/run_pipeline.py',
     '--input', 'validation/validation_test_BGC0000001.fasta',
     '--output', 'pipeline_run_output6'],
    timeout=3600
)
print(f"\nPipeline finished with exit code: {result.returncode}")
