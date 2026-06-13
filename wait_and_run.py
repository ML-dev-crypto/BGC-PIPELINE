"""
Wait for hmmpress to finish (WSL frees up), then run the pipeline.
Polls every 30s. Writes result to pipeline_result.txt.
"""
import subprocess, time, sys

print("Waiting for WSL to be free (hmmpress finishing)...")

# Wait for WSL to respond
for i in range(60):  # up to 30 minutes
    try:
        r = subprocess.run(
            ['wsl', 'ls', '/root/bgc_work/pfam_data/'],
            capture_output=True, text=True, timeout=20
        )
        if r.returncode == 0:
            print(f"WSL free after {i*30}s. Files: {r.stdout.strip()}")
            break
    except subprocess.TimeoutExpired:
        print(f"  [{i*30}s] WSL still busy...")
        time.sleep(30)
        continue
    time.sleep(30)
else:
    print("Timed out waiting for WSL")
    sys.exit(1)

# Check h3i
r2 = subprocess.run(
    ['wsl', 'bash', '-c', 'wc -c < /root/bgc_work/pfam_data/Pfam-A.hmm.h3i'],
    capture_output=True, text=True, timeout=20
)
h3i_size = r2.stdout.strip()
print(f"h3i size: {h3i_size} bytes")

if h3i_size == '0':
    print("h3i still 0 — re-pressing...")
    subprocess.run(
        ['wsl', 'bash', '-c', 'hmmpress -f /root/bgc_work/pfam_data/Pfam-A.hmm'],
        timeout=600
    )
    print("hmmpress done")

# Run pipeline
print("\nRunning pipeline with native Pfam...")
result = subprocess.run(
    ['python', 'scripts/run_pipeline.py',
     '--input', 'validation/validation_test_BGC0000001.fasta',
     '--output', 'pipeline_run_output6'],
    capture_output=False, timeout=3600
)
print(f"\nPipeline exit code: {result.returncode}")
