"""Integration tests for libnova adapter LAB_LANE dispatch.

F1 fix verification: the adapter must route to the geometric (helio/geo
rectangular) code path for both LAB_LANE=geometric_vector (the canonical
orchestrator token) and LAB_LANE=geometric (backwards-compat).
"""
import json
import os
import subprocess
from pathlib import Path

ADAPTER = (
    Path(__file__).parent.parent
    / "adapters"
    / "libnova_adapter"
    / "build"
    / "libnova_adapter"
)

# One J2000 epoch is enough to probe the code path.
SOLAR_INPUT = "solar_position\n1\n2451545.000000000000000\n"
MARS_INPUT = "mars_position\n1\n2451545.000000000000000\n"


def _run(input_text: str, lane: str | None) -> dict:
    env = os.environ.copy()
    if lane is not None:
        env["LAB_LANE"] = lane
    else:
        env.pop("LAB_LANE", None)
    result = subprocess.run(
        [str(ADAPTER)],
        input=input_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, f"adapter exited {result.returncode}: {result.stderr}"
    return json.loads(result.stdout.strip())


def test_geometric_vector_uses_geometric_model():
    """LAB_LANE=geometric_vector must trigger the _geometric model path."""
    data = _run(SOLAR_INPUT, "geometric_vector")
    model = data.get("model", "")
    assert "_geometric" in model, (
        f"Expected '_geometric' in model name for geometric_vector lane, got: {model!r}"
    )


def test_geometric_uses_geometric_model():
    """LAB_LANE=geometric (backwards compat) must also trigger geometric path."""
    data = _run(SOLAR_INPUT, "geometric")
    model = data.get("model", "")
    assert "_geometric" in model, (
        f"Expected '_geometric' in model name for geometric lane, got: {model!r}"
    )


def test_apparent_lane_uses_apparent_model():
    """Absent or apparent LAB_LANE must use the apparent (equ_coords) path."""
    data_none = _run(SOLAR_INPUT, None)
    data_apparent = _run(SOLAR_INPUT, "apparent_observer")
    for data, desc in [(data_none, "no lane"), (data_apparent, "apparent_observer lane")]:
        model = data.get("model", "")
        assert "_geometric" not in model, (
            f"Expected apparent model for {desc}, got: {model!r}"
        )


def test_geometric_vector_mars():
    """geometric_vector lane works for a planet (not just solar_position)."""
    data = _run(MARS_INPUT, "geometric_vector")
    model = data.get("model", "")
    assert "_geometric" in model, (
        f"Expected '_geometric' in mars_position model for geometric_vector lane, got: {model!r}"
    )


def test_geometric_and_geometric_vector_produce_different_ra_than_apparent():
    """Geometric and apparent paths must produce meaningfully different RA/Dec."""
    geo = _run(SOLAR_INPUT, "geometric_vector")
    app = _run(SOLAR_INPUT, None)

    geo_cases = geo.get("cases", [])
    app_cases = app.get("cases", [])
    assert geo_cases and app_cases, "Both paths must return cases"

    geo_ra = geo_cases[0].get("ra_rad")
    app_ra = app_cases[0].get("ra_rad")
    assert geo_ra is not None and app_ra is not None
    # Geometric and apparent solar positions differ by at least ~20 arcsec
    # (~1e-4 rad) in RA due to aberration + nutation differences.
    assert abs(geo_ra - app_ra) > 1e-5, (
        f"Geometric and apparent RA should differ; geo={geo_ra}, app={app_ra}"
    )
