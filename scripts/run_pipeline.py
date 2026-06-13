"""
BGC-QDR Pipeline Runner
========================
Orchestrates the full BGC discovery pipeline end-to-end:

  1. Input QC             – filter low-quality / synthetic contigs
  2. BGC Detection        – ORF calling → domain annotation → classification
  3. Novelty Assessment   – compare against MIBiG database
  4. VQC Ranking          – train quantum classifier on MiBIG, score candidates
  5. Results logging      – write pipeline_log.json

Usage (CLI):
    python run_pipeline.py --input <fasta> --output <dir> [--skip-vqc]

Programmatic usage:
    runner = PipelineRunner(input_fasta, output_dir)
    success = runner.run()
    runner = PipelineRunner(input_fasta, output_dir, skip_vqc=True)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure the scripts directory is importable when called from other locations
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from bgc_detection import count_fasta_sequences, run_bgc_detection  # noqa: E402

# MiBIG directory is at the project root (one level up from scripts/)
_PROJECT_ROOT  = Path(__file__).resolve().parents[1]
_DEFAULT_MIBIG = _PROJECT_ROOT / "mibig_gbk_4.0"


class PipelineRunner:
    """Run the full BGC-QDR pipeline for a single FASTA input."""

    def __init__(
        self,
        input_fasta: str,
        output_dir: str,
        skip_vqc: bool = False,
        mibig_dir: Optional[str] = None,
    ):
        self.input_fasta = Path(input_fasta)
        self.output_dir  = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.skip_vqc  = skip_vqc
        self.mibig_dir = Path(mibig_dir) if mibig_dir else _DEFAULT_MIBIG

        # Populated during run()
        self._steps: list[dict] = []
        self._sequences_input: int = 0
        self._bgc_count: int = 0
        self._vqc_meta: dict = {}

    # ------------------------------------------------------------------
    # Stage 1 – Input QC
    # ------------------------------------------------------------------

    def run_input_qc(self) -> tuple[bool, str]:
        """
        Stage 1: Input quality control.

        Returns (success, filtered_fasta_path).
        On failure returns (False, original_fasta_path).
        """
        try:
            from input_qc import InputQC

            qc = InputQC(str(self.input_fasta))
            qc_report, passed_sequences = qc.run_qc()

            filtered_fasta = self.output_dir / "input_filtered.fasta"
            qc.write_filtered_fasta(str(filtered_fasta), passed_sequences)

            qc_report_path = self.output_dir / "qc_report.json"
            with open(qc_report_path, "w", encoding="utf-8") as fh:
                json.dump(qc_report, fh, indent=2)

            return True, str(filtered_fasta)

        except ImportError:
            print("  [WARN] input_qc not available — skipping QC step")
            return True, str(self.input_fasta)
        except ValueError as exc:
            print(f"  [ERROR] QC aborted: {exc}")
            return False, str(self.input_fasta)
        except Exception as exc:
            print(f"  [WARN] QC failed ({exc}) — using original FASTA")
            return True, str(self.input_fasta)

    # ------------------------------------------------------------------
    # Stage 3 – Novelty Assessment
    # ------------------------------------------------------------------

    def run_novelty_assessment(self, bgc_fasta: str) -> tuple[bool, str]:
        """Stage 3: Novelty assessment against MIBiG."""
        try:
            from novelty_assessment import NoveltyAssessor, load_sequences_from_fasta

            sequences = load_sequences_from_fasta(bgc_fasta)
            assessor  = NoveltyAssessor(sequences)
            report    = assessor.assess_all_sequences()

            novelty_path = self.output_dir / "novelty_report.json"
            with open(novelty_path, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2)

            return True, str(novelty_path)

        except Exception as exc:
            print(f"  [WARN] Novelty assessment failed: {exc}")
            novelty_path = self.output_dir / "novelty_report.json"
            with open(novelty_path, "w", encoding="utf-8") as fh:
                json.dump({"error": str(exc)}, fh)
            return False, str(novelty_path)

    # ------------------------------------------------------------------
    # Stage 4 – VQC Ranking (real quantum circuit)
    # ------------------------------------------------------------------

    def run_vqc_ranking(self, detection_meta: dict) -> dict:
        """
        Stage 4: Train VQC on MiBIG BGCs and score detected candidates.

        Returns the vqc_ranking result dict (always — falls back gracefully).
        """
        from vqc_ranking import run_vqc_ranking

        bgc_csv = detection_meta.get("bgc_csv", "")
        domain_table = detection_meta.get("domain_table", "")

        vqc_out_dir = self.output_dir / "vqc_work"

        print(f"  [VQC] Starting quantum ranking ...")
        print(f"  [VQC] MiBIG dir: {self.mibig_dir}")
        print(f"  [VQC] bgc_csv  : {bgc_csv}")

        result = run_vqc_ranking(
            bgc_csv=bgc_csv,
            domain_table_csv=domain_table,
            mibig_dir=str(self.mibig_dir),
            output_dir=str(vqc_out_dir),
        )

        return result

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> bool:
        """
        Execute the full pipeline.

        Returns True on success, False if a fatal error occurred.
        Writes pipeline_log.json to output_dir regardless of outcome.
        """
        print(f"[INFO] Starting BGC-QDR pipeline")
        print(f"  Input:    {self.input_fasta}")
        print(f"  Output:   {self.output_dir}")
        print(f"  VQC:      {'DISABLED (--skip-vqc)' if self.skip_vqc else 'ENABLED'}")

        pipeline_start = time.time()

        self._sequences_input = count_fasta_sequences(self.input_fasta)
        print(f"  Sequences: {self._sequences_input}")

        # ---------------------------------------------------------------
        # Stage 1 – Input QC
        # ---------------------------------------------------------------
        qc_ok, filtered_fasta = self.run_input_qc()
        self._steps.append({
            "step": "input_qc",
            "status": "success" if qc_ok else "failed",
        })
        if not qc_ok:
            self._write_pipeline_log(status="failed", error="Input QC aborted pipeline")
            return False

        # ---------------------------------------------------------------
        # Stage 2 – BGC Detection (ORF → domains → classify)
        # ---------------------------------------------------------------
        detection_work_dir = self.output_dir / "detection_work"
        detection_meta: dict = {}

        try:
            detection_meta   = run_bgc_detection(filtered_fasta, detection_work_dir)
            self._bgc_count  = detection_meta.get("bgc_count", 0)

            orf_status   = "unknown"
            orf_log_path = detection_meta.get("orf_log")
            if orf_log_path and Path(orf_log_path).exists():
                with open(orf_log_path, encoding="utf-8") as fh:
                    orf_log_data = json.load(fh)
                orf_status = orf_log_data.get("status", "unknown")

            self._steps.append({"step": "orf_calling",        "status": orf_status})
            self._steps.append({"step": "domain_annotation",  "status": "success"})
            self._steps.append({"step": "bgc_classification", "status": "success"})

        except Exception as exc:
            print(f"  [ERROR] BGC detection failed: {exc}")
            self._steps.append({"step": "orf_calling",        "status": "failed"})
            self._steps.append({"step": "domain_annotation",  "status": "failed"})
            self._steps.append({"step": "bgc_classification", "status": "failed"})
            self._write_pipeline_log(status="failed", error=str(exc))
            return False

        # ---------------------------------------------------------------
        # Stage 3 – Novelty Assessment
        # ---------------------------------------------------------------
        novelty_ok, novelty_path = self.run_novelty_assessment(filtered_fasta)
        self._steps.append({
            "step": "novelty_assessment",
            "status": "success" if novelty_ok else "warning",
        })

        # ---------------------------------------------------------------
        # Stage 4 – VQC Ranking (real quantum circuit)
        # ---------------------------------------------------------------
        if self.skip_vqc:
            print("  [VQC] Skipped (--skip-vqc flag set)")
            self._steps.append({"step": "vqc_ranking", "status": "skipped"})
            self._vqc_meta = {"vqc_available": False,
                              "fallback_reason": "skipped by user"}
        elif self._bgc_count == 0:
            # No candidates to score — still run training to get real accuracy,
            # but report no candidates rather than skipping entirely.
            print("  [VQC] No BGC candidates detected — running training only "
                  "(no candidates to score)")
            try:
                vqc_result = self.run_vqc_ranking(detection_meta)
                self._vqc_meta = vqc_result
                status = "success" if vqc_result.get("vqc_available") else "warning"
                self._steps.append({
                    "step":   "vqc_ranking",
                    "status": status,
                    "vqc_accuracy": vqc_result.get("vqc_accuracy"),
                    "vqc_roc_auc":  vqc_result.get("vqc_roc_auc"),
                    "note":         "training only — 0 candidates",
                })
            except Exception as exc:
                print(f"  [WARN] VQC training failed: {exc}")
                self._steps.append({"step": "vqc_ranking", "status": "warning",
                                    "error": str(exc)})
                self._vqc_meta = {"vqc_available": False,
                                  "fallback_reason": str(exc)}
        else:
            try:
                print(f"\n[Stage 4] VQC Ranking — training quantum circuit ...")
                vqc_result      = self.run_vqc_ranking(detection_meta)
                self._vqc_meta  = vqc_result
                vqc_ok          = vqc_result.get("vqc_available", False)

                step_entry: dict = {
                    "step":   "vqc_ranking",
                    "status": "success" if vqc_ok else "warning",
                }
                if vqc_ok:
                    step_entry["vqc_accuracy"]  = vqc_result.get("vqc_accuracy")
                    step_entry["vqc_roc_auc"]   = vqc_result.get("vqc_roc_auc")
                    step_entry["architecture"]  = vqc_result.get("architecture")
                    step_entry["train_samples"] = vqc_result.get("train_samples")
                    step_entry["mibig_bgcs"]    = vqc_result.get("mibig_bgcs_used")
                    step_entry["training_time_s"] = vqc_result.get("training_time_s")
                    n_scored = len([c for c in vqc_result.get("candidates", [])
                                    if c.get("quantum_score") is not None])
                    step_entry["candidates_scored"] = n_scored
                    print(f"  [VQC] ✓ acc={vqc_result['vqc_accuracy']:.3f}  "
                          f"auc={vqc_result['vqc_roc_auc']:.3f}  "
                          f"scored {n_scored} candidate(s)")
                else:
                    step_entry["fallback_reason"] = vqc_result.get("fallback_reason")
                    print(f"  [VQC] ⚠  Fell back: {vqc_result.get('fallback_reason')}")

                self._steps.append(step_entry)

            except Exception as exc:
                print(f"  [WARN] VQC stage failed: {exc}")
                self._steps.append({"step": "vqc_ranking", "status": "warning",
                                    "error": str(exc)})
                self._vqc_meta = {"vqc_available": False,
                                  "fallback_reason": str(exc)}

        # ---------------------------------------------------------------
        # Write final pipeline log
        # ---------------------------------------------------------------
        duration = round(time.time() - pipeline_start, 2)
        self._write_pipeline_log(
            status="completed",
            duration=duration,
            detection_meta=detection_meta,
            vqc_meta=self._vqc_meta,
        )

        print(f"\n[OK] Pipeline complete in {duration}s — "
              f"{self._bgc_count} BGC(s) detected")
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_pipeline_log(
        self,
        status: str,
        error: Optional[str] = None,
        duration: float = 0.0,
        detection_meta: Optional[dict] = None,
        vqc_meta: Optional[dict] = None,
    ) -> None:
        """Write pipeline_log.json to output_dir."""
        log: dict = {
            "status":           status,
            "sequences_input":  self._sequences_input,
            "bgc_count":        self._bgc_count,
            "steps":            self._steps,
            "duration_seconds": duration,
        }
        if error:
            log["error"] = error
        if detection_meta:
            log["detection_meta"] = {
                k: str(v) if isinstance(v, Path) else v
                for k, v in detection_meta.items()
            }
        if vqc_meta:
            # Include a concise VQC summary in the top-level log
            log["vqc_summary"] = {
                "vqc_available":   vqc_meta.get("vqc_available"),
                "vqc_accuracy":    vqc_meta.get("vqc_accuracy"),
                "vqc_roc_auc":     vqc_meta.get("vqc_roc_auc"),
                "vqc_precision":   vqc_meta.get("vqc_precision"),
                "vqc_recall":      vqc_meta.get("vqc_recall"),
                "architecture":    vqc_meta.get("architecture"),
                "train_samples":   vqc_meta.get("train_samples"),
                "mibig_bgcs_used": vqc_meta.get("mibig_bgcs_used"),
                "training_time_s": vqc_meta.get("training_time_s"),
                "fallback_reason": vqc_meta.get("fallback_reason"),
                "candidates":      vqc_meta.get("candidates", []),
            }

        log_path = self.output_dir / "pipeline_log.json"
        with open(log_path, "w", encoding="utf-8") as fh:
            json.dump(log, fh, indent=2)

        print(f"  Pipeline log → {log_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="BGC-QDR Pipeline Runner — full end-to-end analysis"
    )
    parser.add_argument("--input",    "-i", required=True,
                        help="Input FASTA file")
    parser.add_argument("--output",   "-o", required=True,
                        help="Output directory for all results")
    parser.add_argument("--skip-vqc", action="store_true",
                        help="Skip VQC training/ranking (faster, for testing)")
    parser.add_argument("--mibig-dir", default=None,
                        help=f"Path to MiBIG GBK directory "
                             f"(default: {_DEFAULT_MIBIG})")
    args = parser.parse_args()

    runner = PipelineRunner(
        input_fasta=args.input,
        output_dir=args.output,
        skip_vqc=args.skip_vqc,
        mibig_dir=args.mibig_dir,
    )
    success = runner.run()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
