"""Tests for validated baseline reuse."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import baselines, scorecard
from pipeline.catalog import CandidateEntry, default_registry
from pipeline.lab_config import load_pipeline_config
from pipeline.run_pipeline import build_orchestrator_command


LAB_ROOT = Path(__file__).resolve().parents[2]


def _sample_row(
    *,
    candidate_id: str = "astropy",
    experiment: str = "gmst_era",
    dataset_fingerprint: str = "abc123",
) -> dict:
    library = candidate_id.split(":")[0]
    return {
        "experiment": experiment,
        "candidate_library": library,
        "candidate_id": candidate_id,
        "candidate_profile": None,
        "reference_library": "erfa",
        "reference_model": "SOFA IAU 2006 GMST / IAU 2000 ERA",
        "reference_source_tag": "ERFA/SOFA",
        "reference_lane": None,
        "status": "ok",
        "api_surface": "public",
        "support_status": "supported",
        "rankable_accuracy": True,
        "rankable_performance": True,
        "comparability_class": "best-available",
        "family": "time_earth_rotation",
        "tier": "public",
        "source_provenance": {"source": "SOFA", "adapter": "erfa"},
        "inputs": {"count": 250, "seed": 42, "dataset_fingerprint": dataset_fingerprint},
        "accuracy": {
            "count_requested": 250,
            "count_valid": 250,
            "error_count": 0,
            "gmst_error_arcsec": {"p50": 1.0, "p99": 2.0, "max": 3.0, "mean": 1.1, "rms": 1.2},
        },
        "performance": {
            "scalar_warm": {
                "ns_per_op": 1000.0,
                "cv": 5.0,
                "valid": True,
                "warnings": [],
                "rounds": 5,
                "n_per_round": 1000,
            },
            "batch_throughput": None,
        },
    }


def _metadata() -> dict:
    return {
        "cpu_model": "test-cpu",
        "platform_detail": "Linux-test",
        "toolchain": {"rustc": "rustc 1.0", "cc": "gcc 13", "python": "3.12"},
        "git_shas": {"astropy": "abc", "siderust": "def"},
        "adapter_binaries": {
            "astropy_adapter": {"sha256": "aa" * 32},
            "siderust_adapter": {"sha256": "bb" * 32},
        },
        "cargo_lock_sha256": {},
    }


def _policy(tmp_path: Path, **overrides) -> baselines.BaselinePolicy:
    raw = {
        "enabled": True,
        "root": str(tmp_path / "baseline_results"),
        "reuse_candidates": ["astropy", "libnova", "anise"],
        "refresh_candidates": ["siderust"],
        "reuse_accuracy": True,
        "reuse_performance": False,
        "require_complete_baselines": False,
        "write_missing_baselines": True,
    }
    raw.update(overrides)
    return baselines.parse_baseline_policy(raw, lab_root=tmp_path)


def _fingerprints(candidate_id: str = "astropy", **kwargs) -> baselines.RunFingerprints:
    entry = default_registry().get(candidate_id, "gmst_era")
    defaults = dict(
        experiment="gmst_era",
        candidate_id=candidate_id,
        metadata=_metadata(),
        n=250,
        seed=42,
        dataset_fingerprint="abc123",
        reference_model="SOFA IAU 2006 GMST / IAU 2000 ERA",
        reference_source_tag="ERFA/SOFA",
        reference_lane=None,
        catalog_entry=entry,
        perf_enabled=True,
        perf_rounds=5,
        perf_scalar_n=1000,
        perf_batch_n=0,
        perf_batch_rounds=0,
        perf_warmup=50,
        perf_timeout_s=60,
        horizons_use_cache=True,
        horizons_allow_network=False,
        suite="core",
    )
    defaults.update(kwargs)
    return baselines.build_run_fingerprints(**defaults)


def test_baseline_policy_defaults_disabled(tmp_path):
    policy = baselines.parse_baseline_policy({}, lab_root=tmp_path)
    assert policy.enabled is False
    assert policy.reuse_candidates == frozenset()
    assert policy.reuse_performance is False


def test_invalid_reuse_performance_rejected(tmp_path):
    with pytest.raises(ValueError, match="reuse_performance"):
        baselines.parse_baseline_policy(
            {"enabled": True, "reuse_performance": "maybe"},
            lab_root=tmp_path,
        )


def test_dev_delta_config_parses_baselines():
    cfg = load_pipeline_config(LAB_ROOT / "pipeline" / "configs" / "dev_delta.toml", lab_root=LAB_ROOT)
    assert cfg.baseline_policy.enabled is True
    assert "astropy" in cfg.baseline_policy.reuse_candidates
    assert "siderust" in cfg.baseline_policy.refresh_candidates
    assert cfg.baseline_policy.reuse_performance is False
    assert cfg.n == 250


def test_publication_delta_config_is_strict():
    cfg = load_pipeline_config(
        LAB_ROOT / "pipeline" / "configs" / "publication_delta.toml",
        lab_root=LAB_ROOT,
    )
    assert cfg.baseline_policy.reuse_performance == "same-machine-only"
    assert cfg.baseline_policy.require_complete_baselines is True
    assert cfg.baseline_policy.write_missing_baselines is False
    assert cfg.publish_latest is True


def test_build_orchestrator_command_forwards_baseline_flags():
    cmd = build_orchestrator_command(LAB_ROOT / "pipeline" / "configs" / "dev_delta.toml")
    assert "--baselines-enabled" in cmd
    assert "--baselines-reuse-accuracy" in cmd
    assert "--suite" in cmd
    assert cmd[cmd.index("--suite") + 1] == "core"


def test_baseline_key_stable_and_sensitive(tmp_path):
    fp_a = _fingerprints()
    key_a = baselines.compute_baseline_key(
        candidate_id="astropy", experiment="gmst_era", fingerprints=fp_a,
    )
    key_b = baselines.compute_baseline_key(
        candidate_id="astropy", experiment="gmst_era", fingerprints=fp_a,
    )
    assert key_a == key_b

    fp_other_n = _fingerprints(n=100)
    key_n = baselines.compute_baseline_key(
        candidate_id="astropy", experiment="gmst_era", fingerprints=fp_other_n,
    )
    assert key_n != key_a

    fp_other_seed = _fingerprints(seed=99)
    key_seed = baselines.compute_baseline_key(
        candidate_id="astropy", experiment="gmst_era", fingerprints=fp_other_seed,
    )
    assert key_seed != key_a

    fp_other_exp = _fingerprints()
    key_exp = baselines.compute_baseline_key(
        candidate_id="astropy", experiment="equ_ecl", fingerprints=fp_other_exp,
    )
    assert key_exp != key_a


def test_catalog_entry_change_invalidates_key(tmp_path):
    fp = _fingerprints()
    key = baselines.compute_baseline_key(
        candidate_id="astropy", experiment="gmst_era", fingerprints=fp,
    )
    other_entry = CandidateEntry(
        id="astropy",
        library="astropy",
        experiment="gmst_era",
        api_surface="public",
        api_method="x",
        model="changed",
        source="src",
        lane="geometric_vector",
        parity="best-available",
        support="supported",
    )
    fp2 = _fingerprints(catalog_entry=other_entry)
    key2 = baselines.compute_baseline_key(
        candidate_id="astropy", experiment="gmst_era", fingerprints=fp2,
    )
    assert key2 != key


def test_workload_and_machine_fingerprints_affect_validation(tmp_path):
    policy = _policy(tmp_path, reuse_performance="same-machine-only")
    fp = _fingerprints()
    row = _sample_row()
    baselines.write_baseline(
        policy=policy,
        candidate_id="astropy",
        experiment="gmst_era",
        fingerprints=fp,
        row=row,
        run_id="run-a",
    )
    artifact, validation = baselines.load_valid_baseline(
        policy=policy,
        candidate_id="astropy",
        experiment="gmst_era",
        expected=fp,
    )
    assert artifact is not None
    assert validation.valid is True
    assert validation.reuse_kind == "combined"

    fp_other_machine = _fingerprints(
        metadata={
            **_metadata(),
            "cpu_model": "other-cpu",
        }
    )
    _, stale = baselines.load_valid_baseline(
        policy=policy,
        candidate_id="astropy",
        experiment="gmst_era",
        expected=fp_other_machine,
    )
    assert stale.valid is False


def test_accuracy_only_reuse_invalidates_performance_ranking(tmp_path):
    policy = _policy(tmp_path, reuse_performance=False)
    fp = _fingerprints()
    row = _sample_row()
    baselines.write_baseline(
        policy=policy,
        candidate_id="astropy",
        experiment="gmst_era",
        fingerprints=fp,
        row=row,
        run_id="run-a",
    )
    artifact, validation = baselines.load_valid_baseline(
        policy=policy,
        candidate_id="astropy",
        experiment="gmst_era",
        expected=fp,
    )
    reused = baselines.annotate_reused_row(
        artifact["result"],
        validation=validation,
        artifact=artifact,
        policy=policy,
    )
    assert reused["execution_origin"] == "baseline"
    assert reused["baseline_reuse_kind"] == "accuracy"
    assert reused["performance"]["scalar_warm"]["valid"] is False
    assert scorecard._performance_rank_eligible(reused) is False
    assert scorecard._accuracy_rank_eligible(reused) is True


def test_compose_reuses_valid_baseline_and_keeps_siderust_fresh(tmp_path):
    policy = _policy(tmp_path)
    fp = _fingerprints()
    row = _sample_row()
    baselines.write_baseline(
        policy=policy,
        candidate_id="astropy",
        experiment="gmst_era",
        fingerprints=fp,
        row=row,
        run_id="seed-run",
    )
    fresh_rows = [_sample_row(candidate_id="siderust")]
    composition = baselines.CompositionState(mode="baseline_delta", baseline_root=str(policy.root))
    run_context = {
        "metadata": _metadata(),
        "n": 250,
        "seed": 42,
        "suite": "core",
        "perf_enabled": True,
        "perf_rounds": 5,
        "perf_scalar_n": 1000,
        "perf_batch_n": 0,
        "perf_batch_rounds": 0,
        "perf_warmup": 50,
        "perf_timeout_s": 60,
        "horizons_use_cache": True,
        "horizons_allow_network": False,
    }
    composed = baselines.compose_experiment_results(
        experiment="gmst_era",
        fresh_rows=fresh_rows,
        policy=policy,
        composition=composition,
        run_context=run_context,
    )
    by_id = {r["candidate_id"]: r for r in composed}
    assert by_id["astropy"]["execution_origin"] == "baseline"
    assert by_id["siderust"]["execution_origin"] == "fresh"
    assert "astropy" in composition.baseline_candidates
    assert "siderust" in composition.fresh_candidates


def test_missing_baseline_computed_when_allowed(tmp_path):
    policy = _policy(tmp_path, reuse_candidates=["astropy"])
    fresh_rows = [_sample_row(candidate_id="astropy")]
    composition = baselines.CompositionState(mode="baseline_delta")
    run_context = {
        "metadata": _metadata(),
        "n": 250,
        "seed": 42,
        "perf_enabled": True,
        "perf_rounds": 5,
        "perf_scalar_n": 1000,
        "perf_batch_n": 0,
        "perf_batch_rounds": 0,
        "perf_warmup": 50,
        "perf_timeout_s": 60,
        "horizons_use_cache": True,
        "horizons_allow_network": False,
    }
    composed = baselines.compose_experiment_results(
        experiment="gmst_era",
        fresh_rows=fresh_rows,
        policy=policy,
        composition=composition,
        run_context=run_context,
    )
    assert composed[0]["execution_origin"] == "fresh"
    assert composition.missing_baselines == []


def test_require_complete_baselines_flags_missing(tmp_path):
    policy = _policy(tmp_path, require_complete_baselines=True)
    composition = baselines.CompositionState(
        mode="baseline_delta",
        missing_baselines=["gmst_era/astropy"],
        all_baselines_valid=False,
    )
    blockers = baselines.validate_composition_for_publication(composition, policy)
    assert blockers
    assert any("missing required baselines" in b for b in blockers)


def test_partial_row_rejected_as_baseline(tmp_path):
    policy = _policy(tmp_path)
    fp = _fingerprints()
    row = _sample_row()
    row["status"] = "partial"
    row["accuracy"]["count_valid"] = 100
    with pytest.raises(ValueError, match="non-reusable"):
        baselines.write_baseline(
            policy=policy,
            candidate_id="astropy",
            experiment="gmst_era",
            fingerprints=fp,
            row=row,
            run_id="bad",
        )


def test_scorecard_preserves_execution_origin(tmp_path):
    experiments = {
        "gmst_era": [
            baselines.annotate_fresh_row(_sample_row()),
            baselines.annotate_reused_row(
                _sample_row(candidate_id="libnova"),
                validation=baselines.BaselineValidation(
                    True, None, "key", None, "accuracy",
                ),
                artifact={"created_from_run_id": "old", "created_at": "2026-01-01"},
                policy=_policy(tmp_path),
            ),
        ]
    }
    card = scorecard.compute_scorecard("test", experiments)
    rows = card["families"][0]["experiments"][0]["rows"]
    origins = {r["display_name"]: r.get("execution_origin") for r in rows}
    assert origins["astropy"] == "fresh"
    assert origins["libnova"] == "baseline"


def test_convergence_config_parses_disabled_by_default(tmp_path):
    cfg = load_pipeline_config(LAB_ROOT / "pipeline" / "configs" / "core.toml", lab_root=LAB_ROOT)
    assert cfg.convergence.enabled is False
    assert cfg.convergence.stages == (50, 100, 250, 1000)


def test_convergence_config_parses_when_present(tmp_path):
    path = tmp_path / "conv.toml"
    path.write_text(
        """
suite = "ci"
[convergence]
enabled = true
stages = [50, 100]
primary_metric = "p99"
relative_tolerance = 0.01
absolute_tolerance = 1e-10
stop_after_stable_stages = 1
"""
    )
    cfg = load_pipeline_config(path, lab_root=tmp_path)
    assert cfg.convergence.enabled is True
    assert cfg.convergence.stages == (50, 100)
    assert cfg.convergence.primary_metric == "p99"
