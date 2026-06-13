import subprocess, time, sys

for attempt in range(24):  # wait up to 2 min
    r = subprocess.run(
        ['wsl', 'ls', '-la', '/root/bgc_work/pfam_data/'],
        capture_output=True, text=True, timeout=15
    )
    output = r.stdout + r.stderr
    with open('pfam_status.txt', 'w') as f:
        f.write(f"Attempt {attempt+1}:\n{output}\nRC:{r.returncode}\n")
    
    # Check if h3i is non-zero
    if 'h3i' in output:
        lines = [l for l in output.splitlines() if 'h3i' in l]
        for line in lines:
            parts = line.split()
            # size is 5th field in ls -la
            if len(parts) >= 5:
                try:
                    size = int(parts[4])
                    if size > 0:
                        with open('pfam_status.txt', 'a') as f:
                            f.write(f"\nPFAM READY! h3i size={size}\n")
                        sys.exit(0)
                except ValueError:
                    pass
    
    time.sleep(5)

with open('pfam_status.txt', 'a') as f:
    f.write("\nTIMEOUT waiting for h3i\n")
