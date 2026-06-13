"""
BGC Detection Module
=====================
Orchestrates the full BGC detection pipeline:
  1. ORF calling (Prodigal via call_orfs.py)
  2. Domain annotation (HMMER via parse_domains.py)
  3. BGC classification (rule engine via classify_bgcs.py)

Exports:
  - count_fasta_sequences(fasta_path) -> int
  - run_bgc_detection(input_fasta, work_dir, **kwargs) -> dict
  - read_bgc_count(bgc_log, bgc_csv, min_score=0.0) -> int
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Union

import pandas as pd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def count_fasta_sequences(fasta_path: Union[str, Path]) -> int:
    """Return the number of sequences in a FASTA file."""
    count = 0
    fasta_path = Path(fasta_path)
    if not fasta_path.exists():
        return 0
    with open(fasta_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith(">"):
                count += 1
    return count


def read_bgc_count(
    bgc_log: Union[str, Path],
    bgc_csv: Union[str, Path],
    min_score: float = 0.0,
) -> int:
    """
    Read the BGC count produced by the classifier.

    Prefers the total_bgcs_detected field in the JSON log.
    Falls back to counting rows in the CSV that pass min_score.
    """
    bgc_log = Path(bgc_log)
    bgc_csv = Path(bgc_csv)

    # Primary: structured log written by classify_bgcs.py
    if bgc_log.exists():
        try:
            with open(bgc_log, encoding="utf-8") as fh:
                data = json.load(fh)
            if "total_bgcs_detected" in data:
                return int(data["total_bgcs_detected"])
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    # Fallback: count CSV rows above min_score
    if bgc_csv.exists():
        count = 0
        try:
            with open(bgc_csv, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    try:
                        score = float(row.get("confidence_score") or 0.0)
                    except ValueError:
                        score = 0.0
                    if score >= min_score:
                        count += 1
        except Exception:
            pass
        return count

    return 0


# ---------------------------------------------------------------------------
# WSL path helper
# ---------------------------------------------------------------------------

def _win_to_wsl_path(windows_path: Path) -> str:
    """
    Convert a Windows absolute path to its WSL /mnt/<drive>/... equivalent.

    Examples:
        D:\\web.dv\\results  ->  /mnt/d/web.dv/results
        C:\\Users\\foo       ->  /mnt/c/Users/foo
    """
    p = windows_path.resolve()
    drive = p.drive          # e.g. 'D:'
    rest = p.as_posix()[len(drive):]   # everything after drive letter
    drive_letter = drive.rstrip(':').lower()
    return f"/mnt/{drive_letter}{rest}"


# ---------------------------------------------------------------------------
# Prodigal wrapper — runs inside WSL so it shares Linux env with HMMER
# ---------------------------------------------------------------------------

def _run_prodigal(input_fasta: Path, output_dir: Path) -> dict:
    """
    Run Prodigal for ORF prediction via WSL on native WSL filesystem.

    Copies input FASTA to native WSL workspace, runs Prodigal there,
    then copies outputs back to Windows output_dir.
    Returns dict with Windows paths to proteins_faa, gene_count, log.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    proteins_faa    = output_dir / "regions_proteins.faa"
    nucleotides_fna = output_dir / "regions_nucleotides.fna"
    genes_gbk       = output_dir / "regions_genes.gbk"
    orf_log_path    = output_dir / "orf_calling.log.json"

    # Native WSL work paths (fast — no /mnt/ bridge)
    wsl_work     = _WSL_WORK_PRODIGAL
    wsl_input    = f"{wsl_work}/input.fasta"
    wsl_proteins = f"{wsl_work}/regions_proteins.faa"
    wsl_nucl     = f"{wsl_work}/regions_nucleotides.fna"
    wsl_gbk      = f"{wsl_work}/regions_genes.gbk"

    # Windows → WSL /mnt/ paths for copy operations only
    mnt_input    = _win_to_wsl_path(input_fasta)
    mnt_proteins = _win_to_wsl_path(proteins_faa)
    mnt_nucl     = _win_to_wsl_path(nucleotides_fna)
    mnt_gbk      = _win_to_wsl_path(genes_gbk)

    # Build one compound bash command:
    # 1. Set up native work dir and copy input in
    # 2. Run prodigal on native paths
    # 3. Copy outputs back to /mnt/ Windows paths
    bash_cmd = (
        f"mkdir -p {wsl_work} && "
        f"cp {mnt_input} {wsl_input} && "
        f"prodigal -i {wsl_input} -a {wsl_proteins} "
        f"-d {wsl_nucl} -o {wsl_gbk} -p meta -q && "
        f"cp {wsl_proteins} {mnt_proteins} && "
        f"cp {wsl_nucl} {mnt_nucl} && "
        f"cp {wsl_gbk} {mnt_gbk}"
    )

    cmd = ["wsl", "--", "bash", "-c", bash_cmd]

    status = "success"
    error_msg = None
    gene_count = 0

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)
        if proteins_faa.exists():
            with open(proteins_faa) as fh:
                gene_count = sum(1 for ln in fh if ln.startswith(">"))
        print(f"  ORF calling (WSL native): {gene_count} ORFs predicted")
    except FileNotFoundError:
        status = "prodigal_not_found"
        error_msg = "WSL or prodigal not found"
        print(f"  [WARN] {error_msg}")
    except subprocess.CalledProcessError as exc:
        status = "prodigal_failed"
        error_msg = exc.stderr[:200] if exc.stderr else str(exc)
        print(f"  [WARN] Prodigal (WSL) failed: {error_msg}")
    except subprocess.TimeoutExpired:
        status = "prodigal_timeout"
        error_msg = "Prodigal timed out after 600 s"
        print(f"  [WARN] {error_msg}")

    # Calculate input hash
    hasher = hashlib.md5()
    with open(input_fasta, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hasher.update(chunk)
    input_hash = hasher.hexdigest()[:16]

    log_data = {
        "status": status,
        "total_orfs_predicted": gene_count,
        "input_hash": input_hash,
        "proteins_faa": str(proteins_faa) if proteins_faa.exists() else None,
        "error": error_msg,
    }
    with open(orf_log_path, "w", encoding="utf-8") as fh:
        json.dump(log_data, fh, indent=2)

    return {
        "status": status,
        "proteins_faa": proteins_faa if proteins_faa.exists() else None,
        "gene_count": gene_count,
        "orf_log": orf_log_path,
        "error": error_msg,
    }


# ---------------------------------------------------------------------------
# HMMER / Pfam constants
# ---------------------------------------------------------------------------

# Native WSL home path for Pfam (fast — no /mnt/ bridge overhead)
_PFAM_WSL_NATIVE = "/root/bgc_work/pfam_data/Pfam-A.hmm"

# Native WSL work directories
_WSL_WORK_PRODIGAL = "/root/bgc_work/prodigal_work"
_WSL_WORK_HMMSCAN  = "/root/bgc_work/hmmscan_work"

# Fallback: Windows-mounted path (slow, only used if native copy absent)
_PFAM_WIN = Path(__file__).resolve().parents[1] / "pfam_data" / "Pfam-A.hmm"


def _pfam_wsl_path() -> str:
    """
    Return the best available WSL path for Pfam-A.hmm.
    Prefers the native WSL copy (/root/bgc_work); falls back to /mnt/ bridge.
    """
    try:
        r = subprocess.run(
            ['wsl', '--', 'wc', '-c', f"{_PFAM_WSL_NATIVE}.h3i"],
            capture_output=True, text=True, timeout=15,
        )
        size = int(r.stdout.strip().split()[0]) if r.returncode == 0 else 0
        if size > 0:
            return _PFAM_WSL_NATIVE
    except Exception:
        pass
    return _win_to_wsl_path(_PFAM_WIN)


def _ensure_pfam_pressed() -> bool:
    """
    Ensure Pfam is pressed and available.
    Checks native WSL copy first (/root/bgc_work), then /mnt/ fallback.
    Returns True if a usable pressed database exists.
    """
    try:
        r = subprocess.run(
            ['wsl', '--', 'wc', '-c',
             f"{_PFAM_WSL_NATIVE}.h3i"],
            capture_output=True, text=True, timeout=15,
        )
        size = int(r.stdout.strip().split()[0]) if r.returncode == 0 else 0
        if size > 0:
            print(f"  [OK] Pfam index ready at native WSL path {_PFAM_WSL_NATIVE}")
            return True
    except Exception:
        pass

    # Check /mnt/ fallback
    index_files = [
        _PFAM_WIN.parent / f"Pfam-A.hmm.{ext}"
        for ext in ("h3f", "h3i", "h3m", "h3p")
    ]
    if all(f.exists() and f.stat().st_size > 0 for f in index_files):
        print(f"  [WARN] Using slow /mnt/ Pfam path — native copy not ready yet")
        return True

    if not _PFAM_WIN.exists():
        print(f"  [WARN] Pfam-A.hmm not found — place it at {_PFAM_WIN}")
        return False

    # Try to press the /mnt/ copy as last resort
    print(f"  [INFO] Pfam index missing — running hmmpress...")
    for f in index_files:
        if f.exists():
            f.unlink()
    try:
        subprocess.run(
            ["wsl", "--", "hmmpress", _win_to_wsl_path(_PFAM_WIN)],
            check=True, timeout=900,
        )
        return all(f.exists() and f.stat().st_size > 0 for f in index_files)
    except Exception as exc:
        print(f"  [WARN] hmmpress failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Domain annotation — real hmmscan via WSL
# ---------------------------------------------------------------------------

def _run_hmmscan(proteins_faa: Path, input_fasta: Path, output_dir: Path) -> Path:
    """
    Run hmmscan against Pfam-A inside WSL, then build a domain table.

    Falls back to a placeholder table if hmmscan fails (so the rest of the
    pipeline still runs rather than crashing).

    Returns the Windows path to domain_table.csv.
    """
    from parse_domains import (
        parse_domtblout,
        extract_gene_metadata,
        load_region_metadata,
        build_domain_table,
    )

    domains_dir = output_dir / "domains"
    domains_dir.mkdir(parents=True, exist_ok=True)
    domain_table_path = domains_dir / "domain_table.csv"
    domtblout_path    = domains_dir / "pfam_hits.domtblout"

    # ------------------------------------------------------------------ #
    # Step 1 – extract gene metadata (always needed)                       #
    # ------------------------------------------------------------------ #
    genes_df   = extract_gene_metadata(str(proteins_faa)) if proteins_faa and proteins_faa.exists() else pd.DataFrame()
    regions_df = load_region_metadata(str(input_fasta))   if input_fasta.exists()                    else pd.DataFrame()

    if genes_df.empty:
        print("  [WARN] No ORFs found — writing empty domain table")
        pd.DataFrame(columns=[
            "target_name", "query_name", "domain_type", "evalue", "score",
            "seq_from", "seq_to", "gene_id", "region_id", "start", "end",
            "strand", "length", "partial", "has_start_codon", "has_stop_codon",
            "n_content_pct",
        ]).to_csv(domain_table_path, index=False)
        return domain_table_path

    # ------------------------------------------------------------------ #
    # Step 2 – run hmmscan via WSL                                         #
    # ------------------------------------------------------------------ #
    # Ensure Pfam index is ready
    if not _ensure_pfam_pressed():
        print("  [WARN] Pfam database not available — falling back to placeholder domains")
        domains_df   = _placeholder_domains_df(genes_df)
        domain_table = build_domain_table(domains_df, genes_df, regions_df)
        domain_table.to_csv(domain_table_path, index=False)
        return domain_table_path

    pfam_wsl = _pfam_wsl_path()

    # ------------------------------------------------------------------ #
    # Run hmmscan entirely on native WSL filesystem for speed              #
    # Copy proteins.faa in, run hmmscan, copy domtblout back               #
    # ------------------------------------------------------------------ #
    wsl_work      = _WSL_WORK_HMMSCAN
    wsl_proteins  = f"{wsl_work}/query_proteins.faa"
    wsl_domtblout = f"{wsl_work}/pfam_hits.domtblout"
    wsl_src_proteins = _win_to_wsl_path(proteins_faa)

    setup_cmd = (
        f"mkdir -p {wsl_work} && "
        f"cp {wsl_src_proteins} {wsl_proteins}"
    )
    subprocess.run(["wsl", "--", "bash", "-c", setup_cmd],
                   check=True, timeout=30)

    cmd = [
        "wsl", "--", "bash", "-c",
        f"hmmscan --domtblout {wsl_domtblout} --cpu 4 "
        f"-E 1e-5 --domE 1e-5 --noali "
        f"{pfam_wsl} {wsl_proteins} > /dev/null"
    ]

    print(f"  Running hmmscan (WSL native filesystem) against Pfam-A...")
    hmmscan_ok = False
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1800)
        # Copy domtblout back from WSL native to Windows output dir
        wsl_domtblout_win = _win_to_wsl_path(domtblout_path)
        subprocess.run(
            ["wsl", "--", "bash", "-c", f"cp {wsl_domtblout} {wsl_domtblout_win}"],
            check=True, timeout=30,
        )
        hmmscan_ok = domtblout_path.exists() and domtblout_path.stat().st_size > 0
        if hmmscan_ok:
            print(f"  hmmscan complete — {domtblout_path.stat().st_size:,} bytes")
        else:
            print("  [WARN] hmmscan produced no output")
    except FileNotFoundError:
        print("  [WARN] wsl/hmmscan not found")
    except subprocess.CalledProcessError as exc:
        print(f"  [WARN] hmmscan failed (rc={exc.returncode}): {exc.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print("  [WARN] hmmscan timed out after 1800 s")

    # ------------------------------------------------------------------ #
    # Step 3 – parse results or fall back to placeholder                   #
    # ------------------------------------------------------------------ #
    if hmmscan_ok:
        try:
            domains_df = parse_domtblout(str(domtblout_path), evalue_cutoff=1e-5)
            if domains_df.empty:
                print("  [WARN] No significant Pfam hits found")
                domains_df = _placeholder_domains_df(genes_df)
            domain_table = build_domain_table(domains_df, genes_df, regions_df)
            domain_table.to_csv(domain_table_path, index=False)
            real = domain_table[domain_table["domain_type"] != "OTHER"]
            print(f"  Domain table: {len(domain_table)} entries ({len(real)} BGC-relevant)")
            return domain_table_path
        except Exception as exc:
            print(f"  [WARN] Domain table build failed: {exc} — using placeholder")

    # Placeholder fallback
    domains_df  = _placeholder_domains_df(genes_df)
    domain_table = build_domain_table(domains_df, genes_df, regions_df)
    domain_table.to_csv(domain_table_path, index=False)
    print(f"  Domain table (placeholder fallback): {len(domain_table)} entries")
    return domain_table_path


def _placeholder_domains_df(genes_df: pd.DataFrame) -> pd.DataFrame:
    """Return a minimal all-OTHER domain DataFrame from gene metadata."""
    rows = []
    for _, gene in genes_df.iterrows():
        rows.append({
            "target_name": gene["gene_id"],
            "query_name":  "placeholder",
            "domain_type": "OTHER",
            "evalue":      1.0,
            "score":       0.0,
            "seq_from":    1,
            "seq_to":      max(1, int(gene.get("length", 100)) // 3),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# BGC classification
# ---------------------------------------------------------------------------

def _run_classification(domain_table_path: Path, output_dir: Path) -> dict:
    """
    Run classify_bgcs rule engine on a domain table.

    Returns dict with bgc_csv, bgc_log, total_bgcs_detected.
    """
    from classify_bgcs import BGCRuleEngine

    bgc_csv_path = output_dir / "bgc_candidates.csv"
    bgc_log_path = output_dir / "bgc_classification.log.json"

    total_bgcs = 0
    bgc_classes: dict = {}

    try:
        domain_table = pd.read_csv(domain_table_path)

        if domain_table.empty:
            # Write empty outputs
            pd.DataFrame(columns=[
                "region_id", "predicted_type", "confidence_score", "confidence_level",
                "completeness", "completeness_score", "completeness_tag",
                "has_start_codon", "has_stop_codon", "n_content_pct",
            ]).to_csv(bgc_csv_path, index=False)
        else:
            engine = BGCRuleEngine(domain_table)
            results = engine.filter_candidates(min_score=0.3, min_domains=1, min_completeness=0.0)
            results.to_csv(bgc_csv_path, index=False)
            total_bgcs = len(results)
            if total_bgcs > 0:
                bgc_classes = results["predicted_type"].value_counts().to_dict()

        print(f"  BGC classification: {total_bgcs} candidate(s) found")

    except Exception as exc:
        print(f"  [WARN] BGC classification error: {exc}")
        # Write empty CSV so downstream code doesn't crash
        pd.DataFrame(columns=[
            "region_id", "predicted_type", "confidence_score", "confidence_level",
            "completeness", "completeness_score", "completeness_tag",
            "has_start_codon", "has_stop_codon", "n_content_pct",
        ]).to_csv(bgc_csv_path, index=False)

    log_data = {
        "total_bgcs_detected": total_bgcs,
        "bgc_classes": bgc_classes,
        "status": "success",
    }
    with open(bgc_log_path, "w", encoding="utf-8") as fh:
        json.dump(log_data, fh, indent=2)

    return {
        "bgc_count": total_bgcs,
        "bgc_csv": bgc_csv_path,
        "bgc_log": bgc_log_path,
        "bgc_classes": bgc_classes,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_bgc_detection(
    input_fasta: Union[str, Path],
    work_dir: Union[str, Path],
    **kwargs,
) -> dict:
    """
    Run the full BGC detection pipeline on *input_fasta*.

    Steps:
      1. ORF calling with Prodigal
      2. Domain annotation (placeholder table when HMMER unavailable)
      3. BGC classification with rule engine

    Returns a dict with keys:
      bgc_count, bgc_log, bgc_csv, orf_log, domain_table,
      detection_status, detection_error, detection_warning
    """
    input_fasta = Path(input_fasta)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    detection_error = None
    detection_warning = None

    # Ensure scripts dir is on sys.path (needed when called from backend)
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    # --- Step 1: ORF calling ---
    orf_result = _run_prodigal(input_fasta, work_dir)
    orf_log = orf_result["orf_log"]

    if orf_result["status"] != "success":
        detection_warning = f"ORF calling skipped: {orf_result['error']}"

    # --- Step 2: Domain annotation (real hmmscan via WSL) ---
    proteins_faa = orf_result.get("proteins_faa")
    domain_table_path = _run_hmmscan(proteins_faa, input_fasta, work_dir)

    # --- Step 3: BGC classification ---
    clf_result = _run_classification(domain_table_path, work_dir)

    return {
        "bgc_count": clf_result["bgc_count"],
        "bgc_log": str(clf_result["bgc_log"]),
        "bgc_csv": str(clf_result["bgc_csv"]),
        "orf_log": str(orf_log),
        "domain_table": str(domain_table_path),
        "detection_status": "completed",
        "detection_error": detection_error,
        "detection_warning": detection_warning,
    }
