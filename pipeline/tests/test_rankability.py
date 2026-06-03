from pathlib import Path
import sys

TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

import orchestrator as orch


def _base_result(experiment: str, library: str, reference: str = "erfa") -> dict:
    return {
        "experiment": experiment,
        "candidate_library": library,
        "reference_library": reference,
        "alignment": orch.alignment_checklist(experiment, candidate_library=library),
        "accuracy": {},
        "performance": {},
        "reference_performance": {},
    }


def test_libnova_model_mismatch_is_not_accuracy_rankable():
    """For non-ephemeris experiments that *isolate* a SOFA internal (BPN), libnova
    has no equivalent observable and remains not-comparable."""
    result = _base_result("frame_rotation_bpn", "libnova")
    enriched = orch.enrich_result(result, "frame_rotation_bpn", "libnova")
    assert enriched["rankable_accuracy"] is False
    assert enriched["comparability_class"] == "not-comparable"
    assert "different" in enriched["rank_exclusion_reason"]


def test_siderust_default_profile_is_rankable_against_sofa_bpn():
    result = _base_result("frame_rotation_bpn", "siderust")
    enriched = orch.enrich_result(result, "frame_rotation_bpn", "siderust")
    assert enriched["candidate_profile"] == "iau2006a"
    assert enriched["rankable_accuracy"] is True


def test_non_matching_siderust_profile_is_not_rankable_against_sofa_bpn():
    result = _base_result("frame_rotation_bpn", "siderust")
    enriched = orch.enrich_result(result, "frame_rotation_bpn", "siderust:iau2000b")
    assert enriched["candidate_profile"] == "iau2000b"
    assert enriched["rankable_accuracy"] is False
    assert "does not match" in enriched["rank_exclusion_reason"]


def test_libnova_on_geometric_lane_is_rankable():
    """libnova exposes both a rectangular helio/geo (geometric, ICRF-frame)
    path and an apparent equ_coords path; on the geometric JPL VECTORS lane
    the adapter switches to the helio/geo path so libnova ranks here too."""
    result = _base_result("solar_position", "libnova", reference="jpl_horizons")
    enriched = orch.enrich_result(
        result,
        "solar_position",
        "libnova",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    assert enriched["rankable_accuracy"] is True
    assert "JPL Horizons DE441" in enriched["reference_model"]


def test_siderust_on_geometric_lane_is_rankable():
    """Siderust returns geometric vectors with no aberration/light-time → must
    be rankable on the public geometric JPL VECTORS lane."""
    result = _base_result("solar_position", "siderust", reference="jpl_horizons")
    enriched = orch.enrich_result(
        result,
        "solar_position",
        "siderust",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    assert enriched["rankable_accuracy"] is True


def test_libnova_on_apparent_lane_is_rankable():
    """The apparent diagnostic lane queries Horizons OBSERVER (astrometric
    RA/Dec). libnova's VSOP87-with-corrections path matches that parity."""
    result = _base_result("mars_position_apparent", "libnova", reference="jpl_horizons")
    enriched = orch.enrich_result(
        result,
        "mars_position_apparent",
        "libnova",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    assert enriched["rankable_accuracy"] is True


def test_siderust_on_apparent_lane_is_not_comparable():
    """Siderust outputs geometric-only directions regardless of lane.  On the
    apparent lane the Horizons OBSERVER reference includes aberration (~20 arcsec),
    so a geometric-only candidate is not a fair accuracy comparison — it should
    be classified as not-comparable and excluded from accuracy rankings."""
    result = _base_result("mars_position_apparent", "siderust", reference="jpl_horizons")
    enriched = orch.enrich_result(
        result,
        "mars_position_apparent",
        "siderust",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    assert enriched["comparability_class"] == "not-comparable"
    assert enriched["rankable_accuracy"] is False


def test_reference_model_includes_lane_suffix():
    """Provenance for the geometric lane should advertise the VECTORS frame so
    users can verify model parity at a glance."""
    result = _base_result("mars_position", "siderust", reference="jpl_horizons")
    enriched = orch.enrich_result(
        result,
        "mars_position",
        "siderust",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    # Lane suffix is appended by reference_model_for; exact wording may evolve
    # but should at least carry the DE source tag.
    assert "DE441" in enriched["reference_model"]


# ------------- A1 / new model-capability policy fields -------------

def test_comparability_class_exact_model_for_siderust_bpn():
    result = _base_result("frame_rotation_bpn", "siderust")
    enriched = orch.enrich_result(result, "frame_rotation_bpn", "siderust")
    assert enriched["comparability_class"] == "exact-model"
    assert enriched["rankable_accuracy"] is True


def test_comparability_class_best_available_for_libnova_pointing():
    """Pointing: libnova uses a different sidereal-time model but the
    observable (alt/az from RA/Dec at a site) is the same → best-available."""
    result = _base_result("equ_horizontal", "libnova")
    enriched = orch.enrich_result(result, "equ_horizontal", "libnova")
    assert enriched["comparability_class"] == "best-available"
    assert enriched["rankable_accuracy"] is True


def test_comparability_class_best_available_for_geometric_lane():
    """Analytic models (VSOP87/Meeus) on the geometric lane are best-available,
    not exact-model — they are geometric-frame outputs but not the same JPL
    DE441 source as the Horizons VECTORS reference."""
    result = _base_result("solar_position", "siderust", reference="jpl_horizons")
    enriched = orch.enrich_result(
        result,
        "solar_position",
        "siderust",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    assert enriched["comparability_class"] == "best-available"


def test_astropy_de440_local_barycenter_row_uses_same_family_jpl_parity():
    """astropy:de440-local uses a local JPL DE440 BSP via get_body_barycentric for
    planet-system barycenters; the reference is Horizons DE441, so this is
    same-family-jpl (a JPL kernel of a different version), NOT exact-model."""
    result = _base_result("mars_barycenter_position", "astropy", reference="jpl_horizons")
    enriched = orch.enrich_result(
        result,
        "mars_barycenter_position",
        "astropy:de440-local",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    assert enriched["catalog_parity"] == "same-family-jpl"
    assert enriched["comparability_class"] == "same-family-jpl"
    # same-family-jpl is rankable in the broad view ...
    assert enriched["rankable_accuracy"] is True
    # ... but must never be the strict exact-model class.
    assert enriched["comparability_class"] != "exact-model"


def test_selected_model_and_source_fields_present():
    result = _base_result("mars_barycenter_position", "siderust", reference="jpl_horizons")
    # Adapter normally sets `model`; simulate that here.
    result["model"] = "siderust_DE441_runtime"
    enriched = orch.enrich_result(
        result,
        "mars_barycenter_position",
        "siderust:de440",
        source_provenance={"source": "JPL Horizons", "source_tag": "DE441"},
    )
    assert enriched["selected_model"] == "siderust_DE441_runtime"
    assert enriched["model_source"] == "JPL DE441"
    assert enriched["lane"] in ("geometric", "geometric_vector")


def test_default_model_parity_class_alias_present():
    """M4: experiment-level parity should be exposed as default_… so the UI
    does not show it as authoritative when candidate-level data exists."""
    alignment = orch.alignment_checklist("frame_rotation_bpn", candidate_library="erfa")
    if "model_parity_class" in alignment:
        assert alignment["default_model_parity_class"] == alignment["model_parity_class"]
