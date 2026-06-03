"""Catalog invariants — every published row carries the metadata reviewers
need to cite it (model, source, lane, parity, support).  Fails fast if a
new catalog entry forgets a required field.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalog import default_registry  # noqa: E402


@pytest.fixture(scope="module")
def registry():
    return default_registry()


def test_catalog_loads_with_entries(registry):
    assert len(registry.entries) > 0
    ids = {e.id for e in registry.entries}
    experiments = {e.experiment for e in registry.entries}
    assert len(ids) > 0
    assert len(experiments) > 0


def test_every_supported_entry_has_provenance(registry):
    for entry in registry.entries:
        if entry.support != "supported":
            continue
        assert entry.library, f"{entry.id}/{entry.experiment} missing library"
        assert entry.api_surface, f"{entry.id}/{entry.experiment} missing api_surface"
        assert entry.model, f"{entry.id}/{entry.experiment} missing model"
        assert entry.source, f"{entry.id}/{entry.experiment} missing source"
        assert entry.lane, f"{entry.id}/{entry.experiment} missing lane"
        assert entry.parity, f"{entry.id}/{entry.experiment} missing parity"


def test_non_supported_entries_have_exclusion_reason(registry):
    for entry in registry.entries:
        if entry.support == "supported":
            continue
        assert entry.exclusion_reason, (
            f"{entry.id}/{entry.experiment} has support={entry.support} "
            "but no exclusion_reason"
        )


def test_unsupported_never_rankable(registry):
    """Truth invariant: an entry with support='unsupported' is never
    advertised as a rankable candidate."""
    for entry in registry.entries:
        if entry.support == "unsupported":
            assert not entry.is_rankable, (
                f"{entry.id}/{entry.experiment}: unsupported but rankable"
            )
            assert not entry.is_published, (
                f"{entry.id}/{entry.experiment}: unsupported but published"
            )


def test_runtime_blocked_never_rankable(registry):
    for entry in registry.entries:
        if entry.support == "runtime-blocked":
            assert not entry.is_rankable
            assert not entry.is_published


def test_kepler_solver_excludes_astropy_and_erfa(registry):
    """Audit fix: astropy and erfa expose no public Kepler-equation
    solver, so they must not appear as supported candidates here."""
    for cid in ("astropy", "erfa"):
        entry = registry.get(cid, "kepler_solver")
        assert entry is not None, f"{cid}/kepler_solver missing from catalog"
        assert entry.support == "unsupported"


def test_de440_lunar_is_supported(registry):
    """Audit fix: siderust:de440 lunar position is now supported after
    the upstream body-chain math (Moon = moon_off / FRAC_EARTH) was
    corrected in vendor/siderust/src/calculus/jpl/bodies.rs."""
    entry = registry.get("siderust:de440", "lunar_position")
    assert entry is not None
    assert entry.support == "supported"
    # DE440 against the Horizons DE441 reference is same-family-jpl, not the
    # strict exact-model class (audit issue #4).
    assert entry.parity == "same-family-jpl"


def test_astropy_de440_local_candidate_is_present(registry):
    entry = registry.get("astropy:de440-local", "solar_position")
    assert entry is not None
    assert entry.support == "supported"
    assert "local" in entry.source.lower()


def test_planet_center_and_barycenter_siderust_profiles_are_separate(registry):
    center = registry.get("siderust:spk_center", "mars_position")
    bary_embedded = registry.get("siderust:de440_barycenter", "mars_barycenter_position")
    bary_runtime = registry.get("siderust:spk_barycenter", "mars_barycenter_position")
    assert center is not None and center.support == "supported"
    assert bary_embedded is not None and bary_embedded.support == "supported"
    assert bary_runtime is not None and bary_runtime.support == "supported"
    assert registry.get("siderust:spk_center", "mars_barycenter_position") is None
    assert registry.get("siderust:de440_barycenter", "mars_position") is None


def test_outer_astropy_jpl_center_rows_are_not_exact_center_parity(registry):
    mercury = registry.get("astropy:jpl", "mercury_position")
    mars = registry.get("astropy:jpl", "mars_position")
    # Mercury center is a true DE440 planet center → same-family-jpl vs the
    # DE441 reference. Mars+ map to barycenters, which is a different observable
    # than the planet-center reference → best-available.
    assert mercury is not None and mercury.parity == "same-family-jpl"
    assert mars is not None and mars.parity == "best-available"
    assert "barycenter" in mars.model.lower()


def test_erfa_is_reference_only(registry):
    """ERFA must always be reference-only — it is the truth column,
    never a competing candidate row in the public scoreboard."""
    for entry in registry.entries:
        if entry.id == "erfa" and entry.support == "supported":
            assert entry.api_surface == "reference"


def test_libnova_never_jpl_parity(registry):
    """libnova publishes only analytic models (VSOP87 / ELP2000) — it
    must never claim ``parity = jpl-spk``."""
    for entry in registry.entries:
        if entry.id == "libnova":
            assert entry.parity != "jpl-spk", (
                f"libnova/{entry.experiment} declares parity=jpl-spk"
            )


def test_published_astropy_frame_time_methods_use_public_api_names(registry):
    experiments = (
        "frame_rotation_bpn",
        "gmst_era",
        "equ_ecl",
        "equ_horizontal",
    )

    for experiment in experiments:
        entry = registry.get("astropy", experiment)
        assert entry is not None, f"astropy/{experiment} missing from catalog"
        assert entry.support == "supported"
        method = entry.api_method.lower()
        assert "via erfa" not in method
        assert "pyerfa" not in method
        assert "erfa." not in method
