"""Performance publication gates — partial adapter output must not win crowns."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_DIR.parent))

import orchestrator as orch
import scorecard


def _rank_row(library: str, *, ns: float, perf_valid: bool = True, status: str = "ok") -> dict:
    return {
        "candidate_library": library,
        "candidate_profile": None,
        "tier": "public",
        "status": status,
        "support_status": "supported",
        "api_surface": "public",
        "rankable_accuracy": True,
        "comparability_class": "best-available",
        "accuracy": {"angular_error_mas": {"p99": 1.0}},
        "performance": {
            "scalar_warm": {
                "ns_per_op": ns,
                "cv": 1.0,
                "valid": perf_valid,
                "n_per_round": 1000,
                "count_requested": 1000,
                "count_valid": 1000 if perf_valid else 500,
                "error_count": 0 if perf_valid else 500,
            },
            "batch_throughput": None,
            "setup_metrics": None,
        },
    }


def test_adapter_perf_round_issues_count_valid_shortfall():
    issues = orch._adapter_perf_round_issues({
        "count_requested": 100,
        "count_valid": 80,
        "error_count": 20,
        "valid": True,
    })
    assert any("80/100" in i for i in issues)


def test_adapter_perf_round_issues_error_count():
    issues = orch._adapter_perf_round_issues({
        "count_requested": 10,
        "count_valid": 10,
        "error_count": 1,
        "valid": True,
    })
    assert any("error_count" in i for i in issues)


def test_adapter_perf_round_issues_partial_status():
    issues = orch._adapter_perf_round_issues({"status": "partial", "valid": True})
    assert any("partial" in i for i in issues)


def test_adapter_perf_round_issues_skipped():
    issues = orch._adapter_perf_round_issues({"skipped": True, "reason": "SPK missing"})
    assert issues


def test_run_multi_sample_perf_accepts_legacy_count_only():
    rounds = [
        {"per_op_ns": 100.0, "total_ns": 100000.0, "count": 1000, "error_count": 0},
    ]

    def fake_run(cmd, input_text, label, extra_env=None, timeout=120):
        return rounds.pop(0)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(orch, "run_adapter", fake_run)
        out = orch.run_multi_sample_perf(["x"], "in", "lbl", rounds=1)
    assert out is not None
    assert out["valid"] is True
    assert out["count_valid"] == 1000
    assert out["count_requested"] == 1000
    assert not any("Incomplete perf coverage" in w for w in out["warnings"])


def test_run_multi_sample_perf_rejects_hidden_partial_counts():
    rounds = [
        {"per_op_ns": 100.0, "total_ns": 1000.0, "count": 100, "count_requested": 100, "count_valid": 50, "error_count": 50},
    ]

    def fake_run(cmd, input_text, label, extra_env=None, timeout=120):
        return rounds.pop(0)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(orch, "run_adapter", fake_run)
        out = orch.run_multi_sample_perf(["x"], "in", "lbl", rounds=1)
    assert out is not None
    assert out["valid"] is False
    assert out["warnings"]


def test_invalidate_perf_on_row_partial_status():
    perf = {
        "scalar_warm": {"ns_per_op": 50.0, "cv": 1.0, "valid": True, "n_per_round": 1000, "count_requested": 1000, "count_valid": 1000},
        "batch_throughput": None,
        "setup_metrics": None,
    }
    out = orch._invalidate_perf_if_incomplete(
        perf, expected_scalar_n=1000, expected_batch_n=100000, row_status="partial",
    )
    assert out["scalar_warm"]["valid"] is False
    assert any("partial" in w for w in out["scalar_warm"]["warnings"])


def test_scalar_warm_summary_invalid_when_error_count():
    perf = {
        "per_op_ns": 100.0,
        "per_op_ns_cv_pct": 1.0,
        "valid": True,
        "batch_size": 1000,
        "count_requested": 1000,
        "count_valid": 900,
        "error_count": 100,
        "warnings": [],
    }
    block = orch._scalar_warm_summary(perf, rounds=3, n_per_round=1000)
    assert block["valid"] is False


def test_legacy_ephemeris_perf_becomes_scorecard_valid():
    rows = [
        {
            "candidate_library": "astropy",
            "candidate_profile": None,
            "tier": "public",
            "family": "solar_system_ephemerides",
            "status": "ok",
            "support_status": "supported",
            "api_surface": "public",
            "rankable_accuracy": True,
            "comparability_class": "best-available",
            "accuracy": {"angular_sep_arcsec": {"p99": 0.01}},
            "performance": {
                "scalar_warm": {
                    "ns_per_op": 314147.0,
                    "cv": 3.8,
                    "valid": True,
                    "n_per_round": 5000,
                    "count_requested": 5000,
                    "count_valid": 5000,
                    "error_count": 0,
                },
                "batch_throughput": {
                    "ns_per_op": 310950.0,
                    "items_per_sec": 3215.0,
                    "valid": True,
                    "n": 100000,
                    "count_requested": 100000,
                    "count_valid": 100000,
                    "error_count": 0,
                },
                "setup_metrics": None,
            },
        },
        {
            "candidate_library": "libnova",
            "candidate_profile": None,
            "tier": "public",
            "family": "solar_system_ephemerides",
            "status": "ok",
            "support_status": "supported",
            "api_surface": "public",
            "rankable_accuracy": True,
            "comparability_class": "best-available",
            "accuracy": {"angular_sep_arcsec": {"p99": 0.02}},
            "performance": {
                "scalar_warm": {
                    "ns_per_op": 37748.0,
                    "cv": 6.4,
                    "valid": True,
                    "n_per_round": 5000,
                    "count_requested": 5000,
                    "count_valid": 5000,
                    "error_count": 0,
                },
                "batch_throughput": {
                    "ns_per_op": 33078.0,
                    "items_per_sec": 30230.0,
                    "valid": True,
                    "n": 100000,
                    "count_requested": 100000,
                    "count_valid": 100000,
                    "error_count": 0,
                },
                "setup_metrics": None,
            },
        },
    ]
    sc = scorecard.compute_scorecard("t", {"solar_position": rows})
    exp = sc["families"][0]["experiments"][0]
    by_id = {row["candidate_id"]: row for row in exp["rows"]}
    assert by_id["astropy"]["perf_valid"] is True
    assert by_id["libnova"]["perf_valid"] is True
    assert by_id["astropy"]["performance"]["scalar_warm"]["count_valid"] == 5000


def test_partial_perf_cannot_win_scorecard():
    rows = [
        _rank_row("fastlib", ns=10.0, perf_valid=False),
        _rank_row("slowlib", ns=500.0, perf_valid=True),
    ]
    sc = scorecard.compute_scorecard("t", {"e": rows})
    exp = sc["families"][0]["experiments"][0]
    assert exp["best_performance"] == "slowlib"
    assert exp["raw_fastest"] == "fastlib"


def test_summarize_experiment_completeness_preserves_partial():
    results = [
        {
            "experiment": "mars_barycenter_position",
            "candidate_library": "libnova",
            "status": "partial",
            "alignment": {},
        },
        {
            "experiment": "mars_barycenter_position",
            "candidate_library": "siderust",
            "status": "ok",
            "alignment": {},
        },
    ]
    summary = orch.summarize_experiment_completeness(results)
    assert summary["mars_barycenter_position"]["partial"] == 1
    assert summary["mars_barycenter_position"]["ok"] == 1
    assert summary["mars_barycenter_position"]["rows"][0]["status"] == "partial"


def test_summarize_experiment_completeness_unknown_status_is_failed():
    results = [
        {
            "experiment": "gmst_era",
            "candidate_library": "astropy",
            "status": "bogus",
            "alignment": {},
        },
    ]
    summary = orch.summarize_experiment_completeness(results)
    assert summary["gmst_era"]["failed"] == 1
    assert summary["gmst_era"]["ok"] == 0
