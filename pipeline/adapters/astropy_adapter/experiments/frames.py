import json
import math
import sys
import time

import numpy as np

try:
    from ..common import ang_sep
except ImportError:
    from common import ang_sep


UNSUPPORTED_FRAME_DIAGNOSTIC_REASON = (
    "Astropy does not expose a public high-level API for this isolated "
    "frame diagnostic; the adapter intentionally avoids direct ERFA/pyerfa "
    "kernel calls."
)


def _configure_astropy():
    from astropy.utils import iers

    iers.conf.auto_download = False


def _time(jd_tt):
    from astropy.time import Time

    return Time(jd_tt, format="jd", scale="tt")


def _icrs_to_mean_ecliptic(jd_tt, ra_rad, dec_rad):
    import astropy.units as u
    from astropy.coordinates import BarycentricMeanEcliptic, ICRS, SkyCoord

    t = _time(jd_tt)
    coord = SkyCoord(ra=ra_rad * u.rad, dec=dec_rad * u.rad, frame=ICRS())
    ecl = coord.transform_to(BarycentricMeanEcliptic(equinox=t))
    back = ecl.transform_to(ICRS())
    return float(ecl.lon.rad), float(ecl.lat.rad), float(back.ra.rad), float(back.dec.rad)


def _unsupported(exp_name, reason=UNSUPPORTED_FRAME_DIAGNOSTIC_REASON):
    result = {
        "experiment": exp_name,
        "library": "astropy",
        "model": "unsupported",
        "status": "unsupported",
        "reason": reason,
        "count": 0,
        "cases": [],
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def _run_mean_ecliptic_accuracy(exp_name, model, lines_iter):
    _configure_astropy()
    n = int(next(lines_iter).strip())
    cases = []

    for _ in range(n):
        parts = next(lines_iter).strip().split()
        jd_tt = float(parts[0])
        ra_rad = float(parts[1])
        dec_rad = float(parts[2])

        ecl_lon, ecl_lat, ra_back, dec_back = _icrs_to_mean_ecliptic(
            jd_tt, ra_rad, dec_rad
        )

        v_in = np.array([
            math.cos(dec_rad) * math.cos(ra_rad),
            math.cos(dec_rad) * math.sin(ra_rad),
            math.sin(dec_rad),
        ])
        v_bk = np.array([
            math.cos(dec_back) * math.cos(ra_back),
            math.cos(dec_back) * math.sin(ra_back),
            math.sin(dec_back),
        ])
        closure_rad = ang_sep(v_in, v_bk)

        cases.append({
            "jd_tt": jd_tt,
            "ra_rad": ra_rad,
            "dec_rad": dec_rad,
            "ecl_lon_rad": ecl_lon,
            "ecl_lat_rad": ecl_lat,
            "closure_rad": closure_rad,
        })

    result = {
        "experiment": exp_name,
        "library": "astropy",
        "model": model,
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def _run_mean_ecliptic_perf(exp_name, lines_iter):
    _configure_astropy()
    n = int(next(lines_iter).strip())
    params = []
    for _ in range(n):
        parts = next(lines_iter).strip().split()
        params.append((float(parts[0]), float(parts[1]), float(parts[2])))

    for i in range(min(n, 100)):
        _icrs_to_mean_ecliptic(*params[i])

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd_tt, ra_rad, dec_rad in params:
        ecl_lon, ecl_lat, _ra_back, _dec_back = _icrs_to_mean_ecliptic(
            jd_tt, ra_rad, dec_rad
        )
        sink += ecl_lon + ecl_lat
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": f"{exp_name}_perf",
        "library": "astropy",
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_equ_ecl(lines_iter):
    _run_mean_ecliptic_accuracy(
        "equ_ecl",
        "Astropy SkyCoord ICRS->BarycentricMeanEcliptic transform",
        lines_iter,
    )


def run_equ_ecl_perf(lines_iter):
    _run_mean_ecliptic_perf("equ_ecl", lines_iter)


def run_icrs_ecl_tod(lines_iter):
    _run_mean_ecliptic_accuracy(
        "icrs_ecl_tod",
        "Astropy SkyCoord ICRS->BarycentricMeanEcliptic transform",
        lines_iter,
    )


def run_icrs_ecl_tod_perf(lines_iter):
    _run_mean_ecliptic_perf("icrs_ecl_tod", lines_iter)


def run_icrs_ecl_j2000(lines_iter): _unsupported("icrs_ecl_j2000")
def run_icrs_ecl_j2000_perf(lines_iter): _unsupported("icrs_ecl_j2000_perf")
def run_inv_icrs_ecl_j2000(lines_iter): _unsupported("inv_icrs_ecl_j2000")
def run_inv_icrs_ecl_j2000_perf(lines_iter): _unsupported("inv_icrs_ecl_j2000_perf")
def run_obliquity(lines_iter): _unsupported("obliquity")
def run_obliquity_perf(lines_iter): _unsupported("obliquity_perf")
def run_inv_obliquity(lines_iter): _unsupported("inv_obliquity")
def run_inv_obliquity_perf(lines_iter): _unsupported("inv_obliquity_perf")
def run_inv_icrs_ecl_tod(lines_iter): _unsupported("inv_icrs_ecl_tod")
def run_inv_icrs_ecl_tod_perf(lines_iter): _unsupported("inv_icrs_ecl_tod_perf")
def run_inv_equ_ecl(lines_iter): _unsupported("inv_equ_ecl")
def run_inv_equ_ecl_perf(lines_iter): _unsupported("inv_equ_ecl_perf")
