"""Regression tests for libnova equ_ecl / icrs_ecl_tod frame contract."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
LAB_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

import orchestrator as orch

LIBNOVA_BIN = LAB_ROOT / "pipeline" / "adapters" / "libnova_adapter" / "build" / "libnova_adapter"
ERFA_BIN = LAB_ROOT / "pipeline" / "adapters" / "erfa_adapter" / "build" / "erfa_adapter"
FRAMES_C = LAB_ROOT / "pipeline" / "adapters" / "libnova_adapter" / "src" / "frames.c"

# J2000, ~2025, ~2100 with varied RA/Dec (radians).
EQU_ECL_CASES = [
    (2451545.0, 0.5, 0.3),
    (2460676.5, 1.0, -0.2),
    (2488070.0, 2.0, 0.5),
]


def _require_bins() -> None:
    if not LIBNOVA_BIN.is_file():
        pytest.skip(f"libnova adapter not built: {LIBNOVA_BIN}")
    if not ERFA_BIN.is_file():
        pytest.skip(f"erfa adapter not built: {ERFA_BIN}")


def _run_adapter(bin_path: Path, experiment: str, body: str) -> dict:
    proc = subprocess.run(
        [str(bin_path)],
        input=body,
        text=True,
        capture_output=True,
        check=True,
        cwd=str(LAB_ROOT),
        timeout=30,
    )
    return json.loads(proc.stdout)


def _equ_ecl_input(cases: list[tuple[float, float, float]]) -> str:
    lines = ["equ_ecl", str(len(cases))]
    for jd, ra, dec in cases:
        lines.append(f"{jd:.15f} {ra:.17e} {dec:.17e}")
    return "\n".join(lines) + "\n"


def _icrs_ecl_tod_input(cases: list[tuple[float, float, float]]) -> str:
    lines = ["icrs_ecl_tod", str(len(cases))]
    for jd, ra, dec in cases:
        lines.append(f"{jd:.15f} {ra:.17e} {dec:.17e}")
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def equ_ecl_results():
    _require_bins()
    inp = _equ_ecl_input(EQU_ECL_CASES)
    return {
        "libnova": _run_adapter(LIBNOVA_BIN, "equ_ecl", inp),
        "erfa": _run_adapter(ERFA_BIN, "equ_ecl", inp),
    }


def test_frames_c_uses_icrs_to_ecl_helpers():
    src = FRAMES_C.read_text(encoding="utf-8")
    assert "libnova_icrs_to_ecl_of_date" in src
    assert "libnova_ecl_of_date_to_icrs" in src
    assert "run_equ_ecl" in src
    run_equ = src.split("void run_equ_ecl(void)")[1].split("void run_equ_ecl_perf")[0]
    assert "libnova_icrs_to_ecl_of_date" in run_equ
    assert "libnova_ecl_of_date_to_icrs" in run_equ
    assert "ln_get_ecl_from_equ(&equ, jd_tt, &ecl)" not in run_equ


def test_equ_ecl_perf_matches_accuracy_path():
    src = FRAMES_C.read_text(encoding="utf-8")
    perf = src.split("void run_equ_ecl_perf(void)")[1].split("/* ---")[0]
    assert "libnova_icrs_to_ecl_of_date" in perf
    assert "ln_get_ecl_from_equ(&equ" not in perf


def test_icrs_ecl_tod_perf_uses_composite_path_and_perf_warmup():
    src = FRAMES_C.read_text(encoding="utf-8")
    perf = src.split("void run_icrs_ecl_tod_perf(void)")[1].split("/* ---")[0]
    assert "libnova_icrs_to_ecl_of_date" in perf
    assert "get_perf_warmup()" in perf
    assert "i < 100" not in perf


def test_libnova_equ_ecl_errors_are_sub_arcminute(equ_ecl_results):
    acc = orch.compute_angular_accuracy(
        equ_ecl_results["erfa"]["cases"],
        equ_ecl_results["libnova"]["cases"],
        "erfa",
        "libnova",
        ra_key="ecl_lon_rad",
        dec_key="ecl_lat_rad",
    )
    sep = acc["angular_sep_arcsec"]
    assert sep["p50"] is not None
    assert sep["p50"] < 20.0, f"p50 too large: {sep['p50']} arcsec"
    assert sep["max"] < 100.0, f"max too large: {sep['max']} arcsec"


def test_libnova_equ_ecl_closure_is_tight(equ_ecl_results):
    for case in equ_ecl_results["libnova"]["cases"]:
        closure = case["closure_rad"]
        assert closure < 1e-9, f"closure_rad={closure}"


def test_libnova_equ_ecl_still_model_mismatch_not_rankable(equ_ecl_results):
    row = {
        "experiment": "equ_ecl",
        "candidate_library": "libnova",
        "reference_library": "erfa",
        "status": "ok",
        "alignment": orch.alignment_checklist(
            "equ_ecl", candidate_library="libnova", candidate_label="libnova"
        ),
        "accuracy": orch.compute_angular_accuracy(
            equ_ecl_results["erfa"]["cases"],
            equ_ecl_results["libnova"]["cases"],
            "erfa",
            "libnova",
            ra_key="ecl_lon_rad",
            dec_key="ecl_lat_rad",
        ),
    }
    enriched = orch.enrich_result(row, "equ_ecl", "libnova")
    assert enriched["catalog_parity"] == "model-mismatch"
    assert enriched["rankable_accuracy"] is False
    assert "model-mismatch" in (enriched.get("rank_exclusion_reason") or "").lower() or (
        "Meeus" in (enriched.get("rank_exclusion_reason") or "")
    )


def test_libnova_icrs_ecl_tod_matches_equ_ecl_contract():
    _require_bins()
    inp = _icrs_ecl_tod_input(EQU_ECL_CASES)
    libnova = _run_adapter(LIBNOVA_BIN, "icrs_ecl_tod", inp)
    erfa = _run_adapter(ERFA_BIN, "icrs_ecl_tod", inp)
    acc = orch.compute_angular_accuracy(
        erfa["cases"],
        libnova["cases"],
        "erfa",
        "libnova",
        ra_key="ecl_lon_rad",
        dec_key="ecl_lat_rad",
    )
    sep = acc["angular_sep_arcsec"]
    assert sep["p50"] < 20.0
    assert sep["max"] < 100.0
    for case in libnova["cases"]:
        assert case["closure_rad"] < 1e-9
