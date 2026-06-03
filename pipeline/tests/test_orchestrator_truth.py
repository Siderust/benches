"""Orchestrator-level truth invariants.

These tests verify that the catalog is correctly wired into the
candidate-list construction so that no fabricated row reaches the
downstream pipeline.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orchestrator as o  # noqa: E402
from lab_config import load_pipeline_config  # noqa: E402


def test_kepler_solver_excludes_astropy_and_erfa():
    """Audit invariant: astropy / erfa kepler_solver rows never reach
    the candidate list — they are dropped by the catalog filter."""
    labels = {label for label, _cmd in o.candidate_adapters_for("kepler_solver")}
    assert "astropy" not in labels
    assert "astropy:jpl" not in labels
    # erfa is the reference adapter and is added separately by the runner;
    # candidate_adapters() already excludes it, so it can't sneak into
    # candidate_adapters_for() either.
    assert "erfa" not in labels


def test_lunar_de440_is_included_in_candidates():
    """siderust:de440 lunar is now supported following the upstream
    moon_off / FRAC_EARTH fix; it must appear in the candidate list."""
    labels = {label for label, _cmd in o.candidate_adapters_for("lunar_position")}
    assert "siderust:de440" in labels


def test_lunar_de440_not_runtime_blocked():
    blocked = o.runtime_blocked_for("lunar_position")
    ids = {cid for _label, cid, _reason in blocked}
    assert "siderust:de440" not in ids


def test_variant_identity_distinct():
    """``astropy:de440-local`` and ``siderust:de440`` must be canonical ids,
    distinct from their base library (no collapse to ``astropy`` /
    ``siderust``)."""
    assert o.candidate_id_for("astropy:de440-local") == "astropy:de440-local"
    assert o.candidate_id_for("siderust:de440") == "siderust:de440"
    assert o.candidate_id_for("siderust:spk_center") == "siderust:spk_center"
    assert o.candidate_id_for("siderust:elp2000") == "siderust:elp2000"


def test_planet_barycenter_profiles_only_enter_barycenter_lane():
    bary_labels = {label for label, _cmd in o.candidate_adapters_for("mars_barycenter_position")}
    center_labels = {label for label, _cmd in o.candidate_adapters_for("mars_position")}
    assert {"siderust:de440_barycenter", "siderust:spk_barycenter"} <= bary_labels
    assert "siderust:spk_center" in center_labels
    assert "siderust:spk_center" not in bary_labels
    assert "siderust:de440_barycenter" not in center_labels


def test_siderust_nutation_profiles_collapse_to_base():
    """Nutation-profile variants share the siderust kepler / transform
    code paths — the catalog publishes them under the bare ``siderust``
    id."""
    for profile in ("iau2000a", "iau2000b", "precession_only"):
        assert o.candidate_id_for(f"siderust:{profile}") == "siderust"


def test_runtime_blocked_excluded_from_adapters_but_listed_in_manifest_helper():
    """Option B policy: runtime-blocked rows are not adapter runs; manifest lists them."""
    from pipeline import catalog

    reg = catalog.default_registry()
    blocked_entry = next(
        (e for e in reg.entries if e.support == "runtime-blocked"),
        None,
    )
    if blocked_entry is None:
        pytest.skip("no runtime-blocked catalog entries declared")
    labels = {o.candidate_id_for(label) for label, _cmd in o.candidate_adapters_for(blocked_entry.experiment)}
    assert blocked_entry.id not in labels
    blocked = o.runtime_blocked_for(blocked_entry.experiment)
    ids = {cid for _label, cid, _reason in blocked}
    assert blocked_entry.id in ids


def test_unknown_variant_drops_to_none():
    """Variants without a catalog entry are dropped entirely — no
    silent passthrough that would re-publish the base candidate's
    numbers under a different label."""
    labels = {label for label, _cmd in o.candidate_adapters_for("frame_rotation_bpn")}
    assert "astropy:de440-local" not in labels
    assert "siderust:de440" not in labels


def test_de440_local_only_when_kernel_enabled():
    labels_enabled = {label for label, _cmd in o.candidate_adapters_for("solar_position")}
    with patch.dict("os.environ", {"SIDERUST_KERNEL_DE440_ENABLED": "0"}):
        labels_disabled = {label for label, _cmd in o.candidate_adapters_for("solar_position")}
    assert "astropy:de440-local" in labels_enabled
    assert "astropy:de440-local" not in labels_disabled


def test_full_fast_candidate_rows_are_catalogued_and_executed():
    """The full smoke config must not emit dense cross-product placeholders."""
    cfg = load_pipeline_config(Path(__file__).resolve().parents[1] / "configs" / "full_fast.toml")
    previous_adapters = o.ACTIVE_ADAPTERS.copy() if o.ACTIVE_ADAPTERS is not None else None
    previous_profiles = list(o.SIDERUST_PROFILES)
    try:
        o.configure_run(adapters=cfg.adapters, siderust_profiles=cfg.siderust_profiles)
        for exp in cfg.experiments:
            labels = {label for label, _cmd in o.candidate_adapters_for(exp)}
            ids = {o.candidate_id_for(label) for label in labels}
            for label in labels:
                assert o._default_catalog().get(o.candidate_id_for(label), exp) is not None

            if exp in {"gmst_era", "frame_rotation_bpn", "equ_ecl", "equ_horizontal"}:
                assert "siderust:elp2000" not in labels
                assert "siderust:de440" not in labels
                assert "astropy:de440-local" not in labels
                assert "anise" not in labels
                assert "siderust:elp2000" not in ids
                assert "siderust:de440" not in ids
                assert "astropy:de440-local" not in ids
                assert "anise" not in ids
    finally:
        o.ACTIVE_ADAPTERS = previous_adapters
        o.SIDERUST_PROFILES = previous_profiles


def test_result_integrity_rejects_non_executed_supported_row():
    row = {
        "experiment": "gmst_era",
        "candidate_library": "siderust",
        "candidate_profile": "elp2000",
        "candidate_id": "siderust:elp2000",
        "status": "ok",
        "support_status": "supported",
        "rankable_accuracy": True,
        "rankable_performance": True,
    }
    issues = o.result_integrity_issues([row])
    assert any("not catalogued" in issue for issue in issues)


def test_result_integrity_rejects_non_supported_ok_placeholder():
    row = {
        "experiment": "kepler_solver",
        "candidate_library": "astropy",
        "candidate_id": "astropy",
        "status": "ok",
        "support_status": "unsupported",
        "rankable_accuracy": False,
        "rankable_performance": False,
    }
    issues = o.result_integrity_issues([row])
    assert any("status=ok" in issue for issue in issues)


def test_libnova_equ_ecl_model_mismatch_is_not_rankable():
    result = {
        "experiment": "equ_ecl",
        "candidate_library": "libnova",
        "reference_library": "erfa",
        "status": "ok",
        "alignment": o.alignment_checklist("equ_ecl", candidate_library="libnova", candidate_label="libnova"),
        "accuracy": {},
    }
    enriched = o.enrich_result(result, "equ_ecl", "libnova")
    assert enriched["support_status"] == "supported"
    assert enriched["catalog_parity"] == "model-mismatch"
    assert enriched["rankable_accuracy"] is False
    assert enriched["rankable_performance"] is False
    assert "Meeus/equinox-of-date convention" in enriched["rank_exclusion_reason"]
