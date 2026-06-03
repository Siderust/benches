import json
import os
import math
import sys
import time

import numpy as np

try:
    from ..common import ang_sep, normalize3
except ImportError:
    from common import ang_sep, normalize3


UNSUPPORTED_COMPONENT_REASON = (
    "Astropy does not expose a public high-level API for this isolated "
    "SOFA component diagnostic; the adapter intentionally avoids direct "
    "ERFA/pyerfa kernel calls."
)


def _configure_astropy():
    from astropy.utils import iers

    iers.conf.auto_download = False


def _time_from_tt_ut1(jd_tt, jd_ut1=None):
    from astropy.time import Time

    t = Time(jd_tt, format="jd", scale="tt")
    if jd_ut1 is not None:
        t.delta_ut1_utc = (jd_ut1 - t.utc.jd) * 86400.0
    return t


def _gcrs_to_tete_vector(jd_tt, vin):
    import astropy.units as u
    from astropy.coordinates import GCRS, SkyCoord, TETE

    t = _time_from_tt_ut1(jd_tt)
    coord = SkyCoord(
        x=vin[0] * u.one,
        y=vin[1] * u.one,
        z=vin[2] * u.one,
        representation_type="cartesian",
        frame=GCRS(obstime=t),
    )
    out = coord.transform_to(TETE(obstime=t))
    return normalize3(out.cartesian.xyz.to_value(u.one))


def _tete_to_gcrs_vector(jd_tt, vin):
    import astropy.units as u
    from astropy.coordinates import GCRS, SkyCoord, TETE

    t = _time_from_tt_ut1(jd_tt)
    coord = SkyCoord(
        x=vin[0] * u.one,
        y=vin[1] * u.one,
        z=vin[2] * u.one,
        representation_type="cartesian",
        frame=TETE(obstime=t),
    )
    out = coord.transform_to(GCRS(obstime=t))
    return normalize3(out.cartesian.xyz.to_value(u.one))


def _unsupported(exp_name, reason=UNSUPPORTED_COMPONENT_REASON):
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


def run_frame_rotation_bpn(lines_iter):
    """GCRS -> TETE using Astropy's public coordinate transform graph."""
    _configure_astropy()
    n = int(next(lines_iter).strip())
    cases = []

    for _ in range(n):
        parts = next(lines_iter).strip().split()
        jd_tt = float(parts[0])
        vin = normalize3(np.array([float(parts[1]), float(parts[2]), float(parts[3])]))

        vout = _gcrs_to_tete_vector(jd_tt, vin)
        vback = _tete_to_gcrs_vector(jd_tt, vout)
        closure_rad = ang_sep(vin, vback)

        cases.append({
            "jd_tt": jd_tt,
            "input": vin.tolist(),
            "output": vout.tolist(),
            "closure_rad": closure_rad,
        })

    result = {
        "experiment": "frame_rotation_bpn",
        "library": "astropy",
        "model": "Astropy SkyCoord GCRS->TETE transform",
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_gmst_era(lines_iter):
    """Compute GMST, ERA, and GAST using Astropy's public Time API."""
    import astropy.units as u

    _configure_astropy()
    n = int(next(lines_iter).strip())
    cases = []

    for _ in range(n):
        parts = next(lines_iter).strip().split()
        jd_ut1 = float(parts[0])
        jd_tt = float(parts[1])
        t = _time_from_tt_ut1(jd_tt, jd_ut1)

        gmst = t.sidereal_time("mean", longitude=0 * u.deg, model="IAU2006").rad
        era = t.earth_rotation_angle(longitude=0 * u.deg).rad
        gast = t.sidereal_time("apparent", longitude=0 * u.deg, model="IAU2006A").rad

        cases.append({
            "jd_ut1": jd_ut1,
            "jd_tt": jd_tt,
            "gmst_rad": float(gmst),
            "era_rad": float(era),
            "gast_rad": float(gast),
        })

    result = {
        "experiment": "gmst_era",
        "library": "astropy",
        "model": "Astropy Time.sidereal_time + earth_rotation_angle",
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_frame_rotation_bpn_perf(lines_iter):
    _configure_astropy()
    n = int(next(lines_iter).strip())
    jds = []
    vecs = []
    for _ in range(n):
        parts = next(lines_iter).strip().split()
        jds.append(float(parts[0]))
        vecs.append(normalize3(np.array([float(parts[1]), float(parts[2]), float(parts[3])])))

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        _gcrs_to_tete_vector(jds[i], vecs[i])

    t0 = time.perf_counter_ns()
    sink = np.zeros(3)
    for i in range(n):
        sink = _gcrs_to_tete_vector(jds[i], vecs[i])
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "frame_rotation_bpn_perf",
        "library": "astropy",
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink[0]),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_gmst_era_perf(lines_iter):
    import astropy.units as u

    _configure_astropy()
    n = int(next(lines_iter).strip())
    params = []
    for _ in range(n):
        parts = next(lines_iter).strip().split()
        params.append((float(parts[0]), float(parts[1])))

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        jd_ut1, jd_tt = params[i]
        t = _time_from_tt_ut1(jd_tt, jd_ut1)
        t.sidereal_time("mean", longitude=0 * u.deg, model="IAU2006")

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd_ut1, jd_tt in params:
        t = _time_from_tt_ut1(jd_tt, jd_ut1)
        sink += t.sidereal_time("mean", longitude=0 * u.deg, model="IAU2006").rad
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "gmst_era_perf",
        "library": "astropy",
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_inv_bpn(lines_iter):
    """TETE -> GCRS using Astropy's public coordinate transform graph."""
    _configure_astropy()
    n = int(next(lines_iter).strip())
    cases = []

    for _ in range(n):
        parts = next(lines_iter).strip().split()
        jd_tt = float(parts[0])
        vin = normalize3(np.array([float(parts[1]), float(parts[2]), float(parts[3])]))
        vout = _tete_to_gcrs_vector(jd_tt, vin)
        vback = _gcrs_to_tete_vector(jd_tt, vout)
        closure_rad = ang_sep(vin, vback)

        cases.append({
            "jd_tt": jd_tt,
            "input": vin.tolist(),
            "output": vout.tolist(),
            "closure_rad": closure_rad,
        })

    result = {
        "experiment": "inv_bpn",
        "library": "astropy",
        "model": "Astropy SkyCoord TETE->GCRS transform",
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_inv_bpn_perf(lines_iter):
    _configure_astropy()
    n = int(next(lines_iter).strip())
    jds = []
    vecs = []
    for _ in range(n):
        parts = next(lines_iter).strip().split()
        jds.append(float(parts[0]))
        vecs.append(normalize3(np.array([float(parts[1]), float(parts[2]), float(parts[3])])))

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        _tete_to_gcrs_vector(jds[i], vecs[i])

    t0 = time.perf_counter_ns()
    sink = np.zeros(3)
    for i in range(n):
        sink = _tete_to_gcrs_vector(jds[i], vecs[i])
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "inv_bpn_perf",
        "library": "astropy",
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink[0]),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_frame_bias(lines_iter): _unsupported("frame_bias")
def run_frame_bias_perf(lines_iter): _unsupported("frame_bias_perf")
def run_precession(lines_iter): _unsupported("precession")
def run_precession_perf(lines_iter): _unsupported("precession_perf")
def run_nutation(lines_iter): _unsupported("nutation")
def run_nutation_perf(lines_iter): _unsupported("nutation_perf")
def run_inv_frame_bias(lines_iter): _unsupported("inv_frame_bias")
def run_inv_frame_bias_perf(lines_iter): _unsupported("inv_frame_bias_perf")
def run_inv_precession(lines_iter): _unsupported("inv_precession")
def run_inv_precession_perf(lines_iter): _unsupported("inv_precession_perf")
def run_inv_nutation(lines_iter): _unsupported("inv_nutation")
def run_inv_nutation_perf(lines_iter): _unsupported("inv_nutation_perf")
def run_bias_precession(lines_iter): _unsupported("bias_precession")
def run_bias_precession_perf(lines_iter): _unsupported("bias_precession_perf")
def run_inv_bias_precession(lines_iter): _unsupported("inv_bias_precession")
def run_inv_bias_precession_perf(lines_iter): _unsupported("inv_bias_precession_perf")
def run_precession_nutation(lines_iter): _unsupported("precession_nutation")
def run_precession_nutation_perf(lines_iter): _unsupported("precession_nutation_perf")
def run_inv_precession_nutation(lines_iter): _unsupported("inv_precession_nutation")
def run_inv_precession_nutation_perf(lines_iter): _unsupported("inv_precession_nutation_perf")
