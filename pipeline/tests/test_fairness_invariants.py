"""Fairness invariants the lab must enforce automatically (task Part F).

These tests fail if the lab regresses on any of the audit fairness rules:

  * provenance: a published manifest never carries an "unknown" submodule SHA;
  * JPL parity: DE440-vs-DE441 is never classified exact-model;
  * performance crown: an invalid timing never wins ``best_performance``;
  * scope: a partial run (core subset) is labelled ``partial``;
  * uniqueness: every (candidate_id, experiment) tuple is unique;
  * reference adapters never appear as a public candidate row.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import catalog, orchestrator, scorecard
from pipeline.lab_config import PUBLIC_EXPERIMENTS

LAB_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Provenance (audit issue #6)
# ---------------------------------------------------------------------------

def test_submodule_shas_are_resolved_not_unknown():
    """run_metadata must resolve every present submodule to a real SHA."""
    shas = orchestrator._collect_git_shas()
    assert shas["lab"] != "unknown"
    for name, path in orchestrator.SUBMODULE_PATHS.items():
        if path.exists():
            assert shas[name] != "unknown", f"{name} SHA is unknown but {path} exists"
            assert len(shas[name]) == 12, f"{name} SHA malformed: {shas[name]!r}"


def _published_manifests() -> list[Path]:
    """The canonical published artifact is ``latest_results``.

    Historical dated runs under ``results/`` predate the provenance fix
    (issue #6) and their original submodule SHAs cannot be reconstructed
    retroactively, so the manifest-SHA invariant is enforced on the published
    ``latest_results`` artifact (and on the live ``run_metadata`` path).
    """
    out = []
    latest = LAB_ROOT / "latest_results" / "manifest.json"
    if latest.is_file():
        out.append(latest)
    return out


def test_published_manifests_have_no_unknown_submodule_shas():
    """F9: a published manifest must not carry unknown siderust/anise SHAs."""
    manifests = _published_manifests()
    if not manifests:
        pytest.skip("no published manifests present")
    for mp in manifests:
        meta = json.loads(mp.read_text()).get("metadata", {})
        shas = meta.get("git_shas", {})
        for key in ("siderust", "anise"):
            assert shas.get(key) not in (None, "unknown"), (
                f"{mp.relative_to(LAB_ROOT)} has {key} SHA = {shas.get(key)!r}"
            )


# ---------------------------------------------------------------------------
# JPL parity taxonomy (audit issue #4)
# ---------------------------------------------------------------------------

def test_parity_vocabulary_is_the_six_audit_classes():
    assert catalog.VALID_PARITIES == {
        "exact-same-kernel", "same-family-jpl", "best-available",
        "model-mismatch", "diagnostic-only", "reference",
    }


def test_no_de440_candidate_is_exact_same_kernel_vs_de441_reference():
    """The reference is Horizons DE441; any candidate whose model is a DE440
    kernel must be same-family-jpl, never exact-same-kernel (issue #4)."""
    reg = catalog.default_registry()
    for e in reg.entries:
        if "de440" in (e.model or "").lower() or "de440" in (e.source or "").lower():
            assert e.parity != "exact-same-kernel", (
                f"{e.id}/{e.experiment}: DE440 model tagged exact-same-kernel "
                f"against the DE441 reference"
            )


def test_jpl_ephemeris_candidates_are_same_family_not_exact_model():
    reg = catalog.default_registry()
    jpl_ids = {"anise", "astropy:jpl", "siderust:de440",
               "siderust:de440_barycenter", "siderust:spk_barycenter",
               "siderust:spk_center"}
    seen = 0
    for e in reg.entries:
        if e.id in jpl_ids and e.parity not in ("model-mismatch", "best-available"):
            seen += 1
            assert e.parity == "same-family-jpl", (
                f"{e.id}/{e.experiment} parity={e.parity}; expected same-family-jpl"
            )
    assert seen > 0, "expected at least one JPL-SPK ephemeris catalog entry"


def test_de440_barycenter_row_is_not_exact_model_comparability():
    """End-to-end: an enriched DE440 ephemeris row must not earn the strict
    exact-model comparability class, but must remain rankable (broad view)."""
    result = {
        "candidate_library": "siderust",
        "reference_library": "jpl_horizons",
        "accuracy": {"angular_error_mas": {"p99": 1.0}},
        "alignment": {"lane": "geometric_vector"},
    }
    enriched = orchestrator.enrich_result(
        result, "mars_barycenter_position", "siderust:de440_barycenter",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    assert enriched["comparability_class"] == "same-family-jpl"
    assert enriched["comparability_class"] != "exact-model"
    assert enriched["rankable_accuracy"] is True


# ---------------------------------------------------------------------------
# Performance crown validity (audit issue #3)
# ---------------------------------------------------------------------------

def _perf_row(library: str, ns: float, *, valid: bool, p99: float) -> dict:
    return {
        "candidate_library": library,
        "candidate_id": library,
        "tier": "public",
        "family": "perf_family",
        "status": "ok",
        "support_status": "supported",
        "api_surface": "public",
        "rankable_accuracy": True,
        "comparability_class": "best-available",
        "accuracy": {"angular_error_mas": {"p99": p99}},
        "performance": {
            "scalar_warm": {
                "ns_per_op": ns,
                "cv": 1.0 if valid else 90.0,
                "valid": valid,
                "warnings": [] if valid else ["high CV"],
            }
        },
    }


def test_invalid_timing_cannot_win_best_performance_but_is_raw_fastest():
    # "fastlib" is fastest but statistically invalid (high CV); "slowlib" is valid.
    rows = [
        _perf_row("fastlib", 5.0, valid=False, p99=2.0),
        _perf_row("slowlib", 50.0, valid=True, p99=1.0),
    ]
    sc = scorecard.compute_scorecard("t", {"e": rows})
    exp = sc["families"][0]["experiments"][0]
    assert exp["best_performance"] == "slowlib", "invalid timing won the perf crown"
    assert exp["raw_fastest"] == "fastlib", "raw_fastest should record the raw minimum"


def test_best_performance_none_when_no_valid_timing():
    rows = [_perf_row("fastlib", 5.0, valid=False, p99=2.0)]
    sc = scorecard.compute_scorecard("t", {"e": rows})
    exp = sc["families"][0]["experiments"][0]
    assert exp["best_performance"] is None
    assert exp["raw_fastest"] == "fastlib"


# ---------------------------------------------------------------------------
# Run scope / partial labelling (audit issue #5)
# ---------------------------------------------------------------------------

def test_core_subset_run_is_marked_partial():
    subset = PUBLIC_EXPERIMENTS[:3]
    scope = orchestrator._run_scope(subset, subset)
    assert scope["partial"] is True
    assert scope["suite_label"] == "core-subset"
    assert scope["core_experiments_covered"] == 3


def test_full_core_run_is_not_partial():
    scope = orchestrator._run_scope(list(PUBLIC_EXPERIMENTS), list(PUBLIC_EXPERIMENTS))
    assert scope["partial"] is False
    assert scope["suite_label"] == "core"
    assert scope["core_complete"] is True


def test_incomplete_requested_run_is_partial_even_when_core_complete():
    requested = [*PUBLIC_EXPERIMENTS, "frame_bias"]
    completed = list(PUBLIC_EXPERIMENTS)
    scope = orchestrator._run_scope(requested, completed)
    assert scope["partial"] is True
    assert scope["core_complete"] is True


def test_latest_results_declares_scope_when_partial():
    mp = LAB_ROOT / "latest_results" / "manifest.json"
    if not mp.is_file():
        pytest.skip("no latest_results manifest")
    m = json.loads(mp.read_text())
    scope = m.get("scope")
    assert scope is not None, "latest_results manifest missing scope block"
    completed = m.get("completeness", {}).get("completed_experiments") or []
    if set(completed) < set(PUBLIC_EXPERIMENTS):
        assert scope["partial"] is True


# ---------------------------------------------------------------------------
# Catalog structural invariants (audit issues #1, #8)
# ---------------------------------------------------------------------------

def test_candidate_id_experiment_tuples_are_unique():
    reg = catalog.default_registry()
    seen = set()
    for e in reg.entries:
        key = (e.id, e.experiment)
        assert key not in seen, f"duplicate catalog tuple {key}"
        seen.add(key)


def test_reference_adapters_never_published_or_rankable():
    reg = catalog.default_registry()
    for e in reg.entries:
        if e.api_surface == "reference":
            assert not e.is_published
            assert not e.is_rankable
