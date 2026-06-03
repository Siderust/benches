"""Regression tests for the small-angle metric stability fix (audit F5)
and the variant-aware ephemeris parity lookup (audit F4)."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orchestrator as o  # noqa: E402


# --- Small-angle (atan2-based) metric -------------------------------------


def test_angular_separation_identical_directions_is_zero():
    sep = o.angular_separation(1.234, 0.567, 1.234, 0.567)
    assert sep == 0.0


def test_angular_separation_microarcsec_pair_is_resolved():
    """At ~1e-12 rad the legacy acos floor saturated at ~3e-8 rad
    (the sqrt(eps) cliff). The atan2 form must return the angle within
    a few ulp of the input (well below the old saturation floor)."""
    ra1, dec1 = 1.0, 0.3
    sep = o.angular_separation(ra1, dec1, ra1, dec1 + 1e-12)
    # Must resolve to within 0.1% of the true 1e-12 — vastly below the
    # ~3e-8 floor the old acos formulation produced.
    assert abs(sep - 1e-12) / 1e-12 < 1e-3, f"sep={sep}"
    # And must be very far from the legacy acos floor.
    assert sep < 1e-10, f"sep={sep} exceeds plausible bound"


def test_angular_separation_pico_radian_pair():
    sep = o.angular_separation(1.0, 0.3, 1.0, 0.3 + 1e-15)
    assert sep > 0.0, "must not return zero for non-zero offset"
    assert sep < 1e-10, f"sep={sep} should still be tiny"


def test_angular_separation_arcsec_scale_pair():
    arcsec = math.radians(1.0 / 3600.0)
    sep = o.angular_separation(1.0, 0.3, 1.0, 0.3 + arcsec)
    assert abs(sep - arcsec) / arcsec < 1e-11


def test_angular_separation_normal_separations():
    sep = o.angular_separation(0.0, 0.0, math.pi / 2, 0.0)
    assert abs(sep - math.pi / 2) < 1e-12

    sep = o.angular_separation(0.0, 0.0, math.pi, 0.0)
    assert abs(sep - math.pi) < 1e-12


# --- Variant-aware ephemeris parity (audit F4) ----------------------------


def test_variant_parity_siderust_de440_is_jpl_spk_on_geometric():
    """The de440-backed variant must not be collapsed to the base
    `siderust` analytic parity."""
    parity = o._ephemeris_candidate_parity(
        "siderust", o.LANE_GEOMETRIC, candidate_label="siderust:de440"
    )
    assert parity == "jpl-spk"


def test_variant_parity_astropy_jpl_is_jpl_spk_on_geometric():
    parity = o._ephemeris_candidate_parity(
        "astropy", o.LANE_GEOMETRIC, candidate_label="astropy:jpl"
    )
    assert parity == "jpl-spk"


def test_base_library_still_analytic_when_no_variant():
    parity = o._ephemeris_candidate_parity("siderust", o.LANE_GEOMETRIC)
    assert parity == "analytic"


def test_unknown_variant_falls_back_to_base():
    parity = o._ephemeris_candidate_parity(
        "siderust", o.LANE_GEOMETRIC, candidate_label="siderust:iau2000a"
    )
    # Falls back to the base "siderust" → analytic.
    assert parity == "analytic"


def test_alignment_checklist_preserves_variant_parity():
    """End-to-end: a JPL-backed variant must surface as `jpl-spk` parity
    in the alignment checklist output, not as the base library's
    analytic parity."""
    # Use a known geometric ephemeris experiment.
    geom_exp = next(iter(o.PLANET_POSITION_EXPERIMENTS), None) or "solar_position"
    alignment = o.alignment_checklist(
        geom_exp, candidate_library="siderust", candidate_label="siderust:de440"
    )
    # Confirm variant survived: parity should be jpl-spk for the de440 variant.
    assert alignment.get("candidate_parity") == "jpl-spk"
