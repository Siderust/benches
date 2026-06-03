import json
import math
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from pipeline.adapters.astropy_adapter import adapter
from pipeline.adapters.astropy_adapter import common
from pipeline.adapters.astropy_adapter.experiments import time_earth_rotation


LAB_ROOT = Path(__file__).resolve().parents[2]
ASTROPY_ADAPTER = LAB_ROOT / "pipeline" / "adapters" / "astropy_adapter" / "adapter.py"


CORE_EXPERIMENT_INPUTS = {
    "frame_rotation_bpn": "1\n2451545.0 1.0 0.0 0.0\n",
    "gmst_era": "1\n2451545.0 2451545.0007428704\n",
    "equ_ecl": "1\n2451545.0 1.0 0.5\n",
    "equ_horizontal": "1\n2451545.0 2451545.0007428704 1.0 0.5 -1.0 0.7\n",
}


def test_jpl_lunar_setup_uses_astropy_moon_body(capsys):
    with patch.dict("os.environ", {"ASTROPY_EPHEMERIS": "jpl"}), \
         patch.object(common, "_astropy_geometric_geocentric") as geometric:
        adapter.run_setup("lunar_position_setup")

    geometric.assert_called_once_with(2451545.0, "moon", "jpl")
    assert json.loads(capsys.readouterr().out)["measured"] is True


def run_adapter(experiment, stdin):
    completed = subprocess.run(
        [sys.executable, str(ASTROPY_ADAPTER), experiment],
        input=stdin,
        text=True,
        capture_output=True,
        check=True,
        cwd=LAB_ROOT,
    )
    return json.loads(completed.stdout)


def test_core_astropy_experiments_return_public_api_results():
    for experiment, stdin in CORE_EXPERIMENT_INPUTS.items():
        result = run_adapter(experiment, stdin)
        model = result.get("model", "").lower()

        assert result["experiment"] == experiment
        assert result["library"] == "astropy"
        assert result.get("status") != "unsupported"
        assert result["cases"]
        assert "via erfa" not in model
        assert "erfa." not in model


def test_equ_ecl_uses_mean_ecliptic_model_matching_sofa():
    import erfa

    result = run_adapter("equ_ecl", CORE_EXPERIMENT_INPUTS["equ_ecl"])
    case = result["cases"][0]
    ref_lon, ref_lat = erfa.eqec06(
        2451545.0,
        case["jd_tt"] - 2451545.0,
        case["ra_rad"],
        case["dec_rad"],
    )

    assert result["model"] == "Astropy SkyCoord ICRS->BarycentricMeanEcliptic transform"
    assert abs(case["ecl_lon_rad"] - ref_lon) < 1e-12
    assert abs(case["ecl_lat_rad"] - ref_lat) < 1e-12


def test_frame_rotation_bpn_uses_tete_model_matching_sofa():
    import erfa
    import numpy as np

    result = run_adapter("frame_rotation_bpn", CORE_EXPERIMENT_INPUTS["frame_rotation_bpn"])
    case = result["cases"][0]
    vin = np.array(case["input"])
    vout = np.array(case["output"])
    ref = erfa.pnm06a(2451545.0, case["jd_tt"] - 2451545.0) @ vin

    assert result["model"] == "Astropy SkyCoord GCRS->TETE transform"
    assert math.acos(float(np.clip(np.dot(vout, ref), -1.0, 1.0))) < 1e-12


def test_gmst_era_time_helper_respects_input_ut1():
    jd_ut1 = 2451545.0
    jd_tt = 2451545.0007428704

    t = time_earth_rotation._time_from_tt_ut1(jd_tt, jd_ut1)

    assert abs(t.ut1.jd - jd_ut1) < 1e-10


def test_astropy_adapter_sources_do_not_call_erfa_directly():
    source_dir = LAB_ROOT / "pipeline" / "adapters" / "astropy_adapter"
    forbidden_tokens = ("import erfa", "astropy._erfa", "_get_erfa", "erfa.")

    for path in source_dir.rglob("*.py"):
        if "vendor" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"{path.relative_to(LAB_ROOT)} contains {token!r}"
