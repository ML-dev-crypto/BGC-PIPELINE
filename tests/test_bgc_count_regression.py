#!/usr/bin/env python3
"""Regression tests for classifier-derived BGC counts."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backend_api  # noqa: E402
import run_pipeline  # noqa: E402
from bgc_detection import read_bgc_count  # noqa: E402


def test_read_bgc_count_uses_classifier_outputs(tmp_path):
    """Count should come from classifier log/CSV, not FASTA-style header counts."""
    bgc_log = tmp_path / "bgc_classification.log.json"
    bgc_csv = tmp_path / "bgc_candidates.csv"

    bgc_log.write_text(json.dumps({"total_bgcs_detected": 2}), encoding="utf-8")
    bgc_csv.write_text(
        "region_id,confidence_score\nseq1_region_1,0.91\nseq2_region_1,0.35\n",
        encoding="utf-8",
    )

    assert read_bgc_count(bgc_log, bgc_csv, min_score=0.8) == 2


def test_detect_endpoint_reports_sequences_input_and_classifier_bgc_count(
    tmp_path, monkeypatch
):
    """Backend should count total input sequences before QC and BGCs after classification."""

    upload_dir = tmp_path / "uploads"
    results_dir = tmp_path / "results"
    qc_dir = tmp_path / "qc"
    cache_dir = tmp_path / "cache"
    for directory in (upload_dir, results_dir, qc_dir, cache_dir):
        directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(backend_api, "UPLOAD_FOLDER", upload_dir)
    monkeypatch.setattr(backend_api, "RESULTS_FOLDER", results_dir)
    monkeypatch.setattr(backend_api, "QC_FOLDER", qc_dir)
    monkeypatch.setattr(backend_api, "CACHE_FOLDER", cache_dir)
    monkeypatch.setattr(backend_api, "QC_AVAILABLE", True)
    backend_api.API_CACHE.clear()

    class FakeQC:
        def __init__(self, fasta_path: str):
            self.fasta_path = fasta_path
            self.qc_results = []

        def run_qc(self):
            passed = [
                SimpleNamespace(id="seq1", sequence="AAAA"),
                SimpleNamespace(id="seq3", sequence="GGGG"),
            ]
            report = {
                "passed": 2,
                "failed": 1,
                "pass_rate": 66.7,
                "failure_reasons": {"too_short": 1},
                "sequence_origins": {},
            }
            return report, passed

        def write_filtered_fasta(self, output_path: str, passed_sequences):
            with open(output_path, "w", encoding="utf-8") as handle:
                for seq in passed_sequences:
                    handle.write(f">{seq.id}\n{seq.sequence}\n")

    captured = {}

    def fake_run_bgc_detection(input_fasta, work_dir, **_kwargs):
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        bgc_log = work_dir / "bgc_classification.log.json"
        bgc_csv = work_dir / "bgc_candidates.csv"
        bgc_log.write_text(json.dumps({"total_bgcs_detected": 1}), encoding="utf-8")
        bgc_csv.write_text(
            "region_id,confidence_score\nseq1_region_1,0.95\n",
            encoding="utf-8",
        )
        captured["input_fasta"] = str(input_fasta)
        return {
            "bgc_count": 1,
            "bgc_log": str(bgc_log),
            "bgc_csv": str(bgc_csv),
            "detection_status": "completed",
            "detection_error": None,
        }

    monkeypatch.setattr(backend_api, "InputQC", FakeQC)
    monkeypatch.setattr(backend_api, "run_bgc_detection", fake_run_bgc_detection)

    client = backend_api.app.test_client()
    fasta_payload = b">seq1\nAAAA\n>seq2\nTT\n>seq3\nGGGG\n"
    response = client.post(
        "/api/detect",
        data={"fasta_file": (io.BytesIO(fasta_payload), "sample.fasta")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["sequences_input"] == 3
    assert payload["bgc_count"] == 1
    assert payload["qc_summary"]["passed_sequences"] == 2
    assert captured["input_fasta"].endswith("_filtered.fasta")


def test_pipeline_runner_writes_sequences_input_and_bgc_count_to_final_log(
    tmp_path, monkeypatch
):
    """Pipeline log should preserve total input count and classifier-derived BGC count."""

    input_fasta = tmp_path / "input.fasta"
    output_dir = tmp_path / "pipeline_output"
    input_fasta.write_text(
        ">seq1\nAAAA\n>seq2\nCCCC\n>seq3\nGGGG\n",
        encoding="utf-8",
    )

    def fake_run_input_qc(self):
        return True, str(self.input_fasta)

    def fake_run_novelty_assessment(self, _bgc_fasta):
        return True, str(self.output_dir / "novelty_report.json")

    def fake_run_bgc_detection(input_fasta, work_dir, **_kwargs):
        work_dir = Path(work_dir)
        (work_dir / "domains").mkdir(parents=True, exist_ok=True)
        orf_log = work_dir / "orf_calling.log.json"
        bgc_log = work_dir / "bgc_classification.log.json"
        bgc_csv = work_dir / "bgc_candidates.csv"
        domain_table = work_dir / "domains" / "domain_table.csv"

        orf_log.write_text(
            json.dumps(
                {
                    "status": "success",
                    "total_orfs_predicted": 7,
                    "input_hash": "abc123",
                }
            ),
            encoding="utf-8",
        )
        bgc_log.write_text(json.dumps({"total_bgcs_detected": 2}), encoding="utf-8")
        bgc_csv.write_text(
            "region_id,confidence_score\nseq1_region_1,0.92\nseq3_region_1,0.88\n",
            encoding="utf-8",
        )
        domain_table.write_text("region_id,domain_type\nseq1_region_1,PKS\n", encoding="utf-8")

        return {
            "bgc_count": 2,
            "orf_log": str(orf_log),
            "domain_table": str(domain_table),
            "bgc_csv": str(bgc_csv),
            "bgc_log": str(bgc_log),
            "detection_status": "completed",
            "detection_error": None,
        }

    monkeypatch.setattr(run_pipeline.PipelineRunner, "run_input_qc", fake_run_input_qc)
    monkeypatch.setattr(
        run_pipeline.PipelineRunner,
        "run_novelty_assessment",
        fake_run_novelty_assessment,
    )
    monkeypatch.setattr(run_pipeline, "run_bgc_detection", fake_run_bgc_detection)

    runner = run_pipeline.PipelineRunner(str(input_fasta), str(output_dir))
    assert runner.run() is True

    pipeline_log = json.loads((output_dir / "pipeline_log.json").read_text(encoding="utf-8"))
    assert pipeline_log["sequences_input"] == 3
    assert pipeline_log["bgc_count"] == 2

    steps_by_name = {step["step"]: step for step in pipeline_log["steps"]}
    assert "orf_calling" in steps_by_name
    assert "domain_annotation" in steps_by_name
    assert "bgc_classification" in steps_by_name
    assert "vqc_ranking" in steps_by_name
    assert steps_by_name["orf_calling"]["status"] == "success"
    assert steps_by_name["bgc_classification"]["status"] == "success"
    assert steps_by_name["vqc_ranking"]["status"] == "api_only"


def test_rank_endpoint_returns_low_confidence_fallback_candidates(tmp_path, monkeypatch):
    """Ranking should still return best available candidates when novelty is below threshold."""

    results_dir = tmp_path / "results"
    cache_dir = tmp_path / "cache"
    results_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(backend_api, "RESULTS_FOLDER", results_dir)
    monkeypatch.setattr(backend_api, "CACHE_FOLDER", cache_dir)
    backend_api.API_CACHE.clear()

    job_id = "job_123456"
    (results_dir / f"{job_id}_novelty.json").write_text(
        json.dumps({"novel_count": 0, "novelty_confidence": 0.7}),
        encoding="utf-8",
    )
    (results_dir / f"{job_id}_reconstruction.json").write_text(
        json.dumps({"virtual_bgc_count": 2}),
        encoding="utf-8",
    )
    classifier_csv = results_dir / "bgc_candidates.csv"
    classifier_csv.write_text(
        (
            "region_id,confidence_score,predicted_type,completeness,completeness_score,"
            "completeness_tag,has_start_codon,has_stop_codon,n_content_pct,confidence_level\n"
            "BGC_terpene_002,0.91,Terpene,partial,0.5,partial,true,false,0.27,high\n"
        ),
        encoding="utf-8",
    )
    (results_dir / f"{job_id}_detection.json").write_text(
        json.dumps({"classifier_csv_path": str(classifier_csv)}),
        encoding="utf-8",
    )

    client = backend_api.app.test_client()
    response = client.post("/api/rank", json={"job_id": job_id, "score_threshold": 0.99})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["top_candidates"]
    assert payload["reason"] == "no_novel_candidates"
    assert all(candidate["low_confidence"] is True for candidate in payload["top_candidates"])
    assert payload["top_candidates"][0]["completeness"] == "partial"
    assert payload["top_candidates"][0]["has_stop_codon"] is False
    assert payload["top_candidates"][0]["n_content_pct"] == 0.27


def test_rank_endpoint_explains_when_no_candidates_can_be_generated(tmp_path, monkeypatch):
    """Ranking should explain why the response is empty when no source candidates exist."""

    results_dir = tmp_path / "results"
    cache_dir = tmp_path / "cache"
    results_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(backend_api, "RESULTS_FOLDER", results_dir)
    monkeypatch.setattr(backend_api, "CACHE_FOLDER", cache_dir)
    backend_api.API_CACHE.clear()

    job_id = "job_654321"
    (results_dir / f"{job_id}_novelty.json").write_text(
        json.dumps({"novel_count": 0, "novelty_confidence": 0.7}),
        encoding="utf-8",
    )
    (results_dir / f"{job_id}_reconstruction.json").write_text(
        json.dumps({"virtual_bgc_count": 0}),
        encoding="utf-8",
    )

    client = backend_api.app.test_client()
    response = client.post("/api/rank", json={"job_id": job_id})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["top_candidates"] == []
    assert payload["reason"] == "below_minimum_bgc_threshold"
