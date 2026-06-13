import subprocess

r = subprocess.run(
    ['wsl', '--', 'bash', '-c',
     'hmmscan -h 2>&1 | head -4; echo SEP; hmmpress -h 2>&1 | head -3; echo SEP; which hmmscan; which hmmpress'],
    capture_output=True, text=True, timeout=30
)

with open('hmmer_info.txt', 'w') as f:
    f.write("=== STDOUT ===\n")
    f.write(r.stdout or '(empty)\n')
    f.write("=== STDERR ===\n")
    f.write(r.stderr or '(empty)\n')
    f.write(f"RC: {r.returncode}\n")
