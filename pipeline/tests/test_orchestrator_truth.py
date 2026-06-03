"""Orchestrator-level truth invariants.

These tests verify that the catalog is correctly wired into the
candidate-list construction so that no fabricated row reaches the
downstream pipeline.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orchestrator as o  # noqa: E402


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
    """``astropy:jpl`` and ``siderust:de440`` must be canonical ids,
    distinct from their base library (no collapse to ``astropy`` /
    ``siderust``)."""
    assert o.candidate_id_for("astropy:jpl") == "astropy:jpl"
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
    assert "astropy:jpl" not in labels
    assert "siderust:de440" not in labels
