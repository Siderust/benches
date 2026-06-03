"""Catalog truth invariants — mechanically enforced publication policy."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipeline import catalog, scorecard

LAB_ROOT = Path(__file__).resolve().parents[2]
LATEST = LAB_ROOT / "latest_results"

BARYCENTER_EXPERIMENTS = {
    "mercury_barycenter_position",
    "venus_barycenter_position",
    "mars_barycenter_position",
    "jupiter_barycenter_position",
    "saturn_barycenter_position",
    "uranus_barycenter_position",
    "neptune_barycenter_position",
}

CENTER_EXPERIMENTS = {
    "mercury_position",
    "venus_position",
    "mars_position",
    "jupiter_position",
    "saturn_position",
    "uranus_position",
    "neptune_position",
}

ADAPTER_SOLVER_PATTERNS = re.compile(
    r"newton|bisection|secant|halley|iteration\s+inside\s+the\s+adapter",
    re.IGNORECASE,
)

PUBLIC_BARYCENTER_MISLABEL = re.compile(
    r"\bplanet\s+center\b(?!\s+proxy)",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def registry():
    return catalog.default_registry()


def test_catalog_module_importable():
    assert catalog.CATALOG_PATH.is_file()


def test_every_catalog_entry_has_valid_vocabulary(registry):
    for e in registry.entries:
        assert e.api_surface in catalog.VALID_API_SURFACES, f"{e.id}/{e.experiment} api_surface"
        assert e.support in catalog.VALID_SUPPORT, f"{e.id}/{e.experiment} support"
        assert e.lane in catalog.VALID_LANES, f"{e.id}/{e.experiment} lane"
        assert e.parity in catalog.VALID_PARITIES, f"{e.id}/{e.experiment} parity"


def test_supported_entries_have_explicit_api_method(registry):
    for e in registry.entries:
        if e.support != "supported":
            continue
        assert e.api_method and e.api_method != "(unspecified)", (
            f"{e.id}/{e.experiment}: supported entry missing api_method"
        )


def test_non_supported_entries_have_exclusion_reason(registry):
    for e in registry.entries:
        if e.support == "supported":
            continue
        assert e.exclusion_reason.strip(), (
            f"{e.id}/{e.experiment}: support={e.support} requires exclusion_reason"
        )


def test_reference_surface_never_rankable_or_published(registry):
    for e in registry.entries:
        if e.api_surface != "reference":
            continue
        assert not e.is_rankable
        assert not e.is_published
        assert e.id == "erfa" or e.library == "erfa"


def test_unsupported_and_runtime_blocked_never_rankable(registry):
    for e in registry.entries:
        if e.support in {"unsupported", "runtime-blocked"}:
            assert not e.is_rankable


def test_libnova_never_jpl_spk_parity(registry):
    for e in registry.entries:
        if e.library == "libnova":
            assert e.parity != "jpl-spk", f"{e.id}/{e.experiment}"


def test_erfa_always_reference_only(registry):
    for e in registry.entries:
        if e.library == "erfa" or e.id == "erfa":
            assert e.api_surface == "reference"
            assert e.parity == "reference"


def test_supported_public_methods_are_not_adapter_solvers(registry):
    for e in registry.entries:
        if e.support != "supported" or e.api_surface != "public":
            continue
        assert not ADAPTER_SOLVER_PATTERNS.search(e.api_method), (
            f"{e.id}/{e.experiment}: api_method looks like an adapter solver: {e.api_method!r}"
        )


def test_candidate_id_experiment_tuples_unique(registry):
    seen: set[tuple[str, str]] = set()
    for e in registry.entries:
        key = (e.id, e.experiment)
        assert key not in seen, f"duplicate catalog tuple {key}"
        seen.add(key)


def test_public_barycenter_experiments_not_labelled_planet_center(registry):
    for e in registry.entries:
        if e.experiment not in BARYCENTER_EXPERIMENTS:
            continue
        if e.api_surface != "public":
            continue
        blob = " ".join(
            x for x in (e.display, e.description, e.api_method, e.model) if x
        )
        assert not PUBLIC_BARYCENTER_MISLABEL.search(blob), (
            f"{e.id}/{e.experiment}: public barycenter row must not say 'planet center' "
            f"(use planet-system barycenter)"
        )


def test_planet_center_experiments_are_not_public_barycenter_ids(registry):
    for e in registry.entries:
        if e.experiment in CENTER_EXPERIMENTS and e.api_surface == "public":
            assert "barycenter" not in e.experiment


def _load_latest_result_rows() -> list[tuple[str, dict]]:
    if not LATEST.is_dir():
        return []
    rows: list[tuple[str, dict]] = []
    for exp_dir in LATEST.iterdir():
        if not exp_dir.is_dir() or exp_dir.name == "manifest.json":
            continue
        for f in exp_dir.glob("*.json"):
            try:
                rows.append((exp_dir.name, json.loads(f.read_text())))
            except json.JSONDecodeError:
                continue
    return rows


def test_latest_results_rows_map_to_catalog_when_present():
    rows = _load_latest_result_rows()
    if not rows:
        pytest.skip("no latest_results JSON rows")
    reg = catalog.default_registry()
    for experiment, row in rows:
        cid = row.get("candidate_id")
        if not cid:
            continue
        entry = reg.get(cid, experiment)
        assert entry is not None, (
            f"latest_results/{experiment}: candidate_id={cid!r} not in catalog"
        )


def test_latest_results_partial_rows_not_ranked():
    rows = _load_latest_result_rows()
    if not rows:
        pytest.skip("no latest_results JSON rows")
    for experiment, row in rows:
        if row.get("status") != "partial":
            continue
        assert row.get("rankable_accuracy") is not True, (
            f"{experiment}/{row.get('candidate_id')}: partial row must not be rankable"
        )


def test_scorecard_ignores_mixed_status_rows():
    rows = [
        {
            "candidate_library": "good",
            "candidate_id": "good",
            "tier": "public",
            "family": "f",
            "status": "ok",
            "rankable_accuracy": True,
            "support_status": "supported",
            "api_surface": "public",
            "comparability_class": "best-available",
            "accuracy": {"angular_error_mas": {"p99": 1.0}},
            "performance": {"scalar_warm": {"ns_per_op": 100.0, "cv": 1.0, "valid": True}},
        },
        {
            "candidate_library": "partial",
            "candidate_id": "partial",
            "tier": "public",
            "family": "f",
            "status": "partial",
            "rankable_accuracy": True,
            "support_status": "supported",
            "api_surface": "public",
            "comparability_class": "best-available",
            "accuracy": {"angular_error_mas": {"p99": 0.1}},
            "performance": {"scalar_warm": {"ns_per_op": 1.0, "cv": 1.0, "valid": True}},
        },
        {
            "candidate_library": "erfa",
            "candidate_id": "erfa",
            "tier": "public",
            "family": "f",
            "status": "ok",
            "rankable_accuracy": False,
            "support_status": "supported",
            "api_surface": "reference",
            "comparability_class": "not-comparable",
            "accuracy": {"angular_error_mas": {"p99": 0.01}},
        },
    ]
    sc = scorecard.compute_scorecard("t", {"e": rows})
    exp = sc["families"][0]["experiments"][0]
    assert exp["best_accuracy"] == "good"
    assert exp["best_performance"] == "good"
