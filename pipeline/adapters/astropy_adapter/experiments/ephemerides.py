import json
import os
import math
import sys
import time

try:
    from ..common import (
        PLANET_EXPERIMENTS,
        PLANET_BARYCENTER_EXPERIMENTS,
        _astropy_geometric_geocentric,
        _astropy_ephemeris_spec,
    )
except ImportError:
    from common import (
        PLANET_EXPERIMENTS,
        PLANET_BARYCENTER_EXPERIMENTS,
        _astropy_geometric_geocentric,
        _astropy_ephemeris_spec,
    )


def _astropy_ephemeris_config():
    raw = os.environ.get("ASTROPY_EPHEMERIS", "builtin").strip()
    try:
        ephemeris = _astropy_ephemeris_spec()
    except FileNotFoundError as exc:
        return None, str(exc)

    if ephemeris not in {"builtin", "jpl"}:
        if not os.path.isfile(ephemeris):
            return None, f"Astropy local BSP path missing: {ephemeris}"

    return ephemeris, None


def _astropy_ephemeris_display(ephemeris):
    if ephemeris == "builtin":
        return "astropy", "Astropy solar_system_ephemeris('builtin') + get_body_barycentric"
    if ephemeris == "jpl":
        return "astropy_jpl", "Astropy solar_system_ephemeris('jpl') + get_body_barycentric"
    return (
        "astropy_de440_local",
        f"Astropy solar_system_ephemeris(local DE440: {ephemeris}) + get_body_barycentric",
    )


def _astropy_skipped_result(experiment, reason, library=None):
    if library is None:
        raw = os.environ.get("ASTROPY_EPHEMERIS", "builtin").strip()
        library = "astropy_de440_local" if raw == "de440-local" else "astropy_jpl"
    result = {
        "experiment": experiment,
        "library": library,
        "status": "skipped",
        "skipped": True,
        "reason": reason,
        "count": 0,
        "cases": [],
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_solar_position(lines_iter):
    """Sun geocentric RA/Dec via Astropy's public ephemeris API.

    ``ASTROPY_EPHEMERIS`` selects the Astropy ephemeris backend.  Supported
    values are ``builtin``, ``jpl``, ``de440-local``, or an explicit BSP path.
    """
    ephemeris, reason = _astropy_ephemeris_config()
    if reason is not None:
        return _astropy_skipped_result("solar_position", reason)

    library, model = _astropy_ephemeris_display(ephemeris)
    n = int(next(lines_iter).strip())
    cases = []
    for _ in range(n):
        jd_tt = float(next(lines_iter).strip())
        try:
            ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, "sun", ephemeris)
        except Exception as exc:
            return _astropy_skipped_result("solar_position", f"Astropy failed to load BSP {ephemeris}: {exc}")
        cases.append({"jd_tt": jd_tt, "ra_rad": ra, "dec_rad": dec, "dist_au": dist_au})

    result = {
        "experiment": "solar_position",
        "library": library,
        "model": model,
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_lunar_position(lines_iter):
    """Moon geocentric RA/Dec via Astropy's public ephemeris API."""
    ephemeris, reason = _astropy_ephemeris_config()
    if reason is not None:
        return _astropy_skipped_result("lunar_position", reason)

    library, model = _astropy_ephemeris_display(ephemeris)
    n = int(next(lines_iter).strip())
    cases = []
    for _ in range(n):
        jd_tt = float(next(lines_iter).strip())
        try:
            ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, "moon", ephemeris)
        except Exception as exc:
            return _astropy_skipped_result("lunar_position", f"Astropy failed to load BSP {ephemeris}: {exc}")
        cases.append({
            "jd_tt": jd_tt,
            "ra_rad": ra,
            "dec_rad": dec,
            "dist_km": dist_au * 149597870.700,
        })

    result = {
        "experiment": "lunar_position",
        "library": library,
        "model": model,
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_planet_position(lines_iter, experiment, planet_name, planet_np):
    """Planet geocentric RA/Dec via Astropy's public ephemeris API."""
    ephemeris, reason = _astropy_ephemeris_config()
    if reason is not None:
        return _astropy_skipped_result(experiment, reason)

    library, model = _astropy_ephemeris_display(ephemeris)
    n = int(next(lines_iter).strip())
    cases = []
    for _ in range(n):
        jd_tt = float(next(lines_iter).strip())
        try:
            ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, planet_name.lower(), ephemeris)
        except Exception as exc:
            return _astropy_skipped_result(experiment, f"Astropy failed to load BSP {ephemeris}: {exc}")
        cases.append({"jd_tt": jd_tt, "ra_rad": ra, "dec_rad": dec, "dist_au": dist_au})

    result = {
        "experiment": experiment,
        "library": library,
        "model": model,
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_planet_barycenter_position(lines_iter, experiment, planet_name):
    """Planet system-barycenter geocentric RA/Dec using astropy JPL ephemeris.

    Uses ``get_body_barycentric(planet_name) - get_body_barycentric('earth')``
    which, with the JPL (DE440) ephemeris, returns the planet's system
    barycenter since DE440 stores planet barycenters (NAIF 4, 5, …) for
    Mars through Neptune.
    """
    ephemeris, reason = _astropy_ephemeris_config()
    if reason is not None:
        return _astropy_skipped_result(experiment, reason)

    library, model = _astropy_ephemeris_display(ephemeris)
    n = int(next(lines_iter).strip())
    cases = []
    for _ in range(n):
        jd_tt = float(next(lines_iter).strip())
        try:
            ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, planet_name.lower(), ephemeris)
        except Exception as exc:
            return _astropy_skipped_result(experiment, f"Astropy failed to load BSP {ephemeris}: {exc}")
        cases.append({"jd_tt": jd_tt, "ra_rad": ra, "dec_rad": dec, "dist_au": dist_au})

    result = {
        "experiment": experiment,
        "library": library,
        "model": f"{model} ({planet_name} system barycenter)",
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_solar_position_perf(lines_iter):
    """Performance measurement for solar position computation."""
    ephemeris, reason = _astropy_ephemeris_config()
    if reason is not None:
        return _astropy_skipped_result("solar_position_perf", reason)

    library, _model = _astropy_ephemeris_display(ephemeris)
    n = int(next(lines_iter).strip())
    jds = [float(next(lines_iter).strip()) for _ in range(n)]

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        try:
            _astropy_geometric_geocentric(jds[i], "sun", ephemeris)
        except Exception as exc:
            return _astropy_skipped_result("solar_position_perf", f"Astropy failed to load BSP {ephemeris}: {exc}")

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd in jds:
        try:
            ra, dec, dist = _astropy_geometric_geocentric(jd, "sun", ephemeris)
        except Exception as exc:
            return _astropy_skipped_result("solar_position_perf", f"Astropy failed during performance evaluation: {exc}")
        sink += ra + dec + dist
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "solar_position_perf",
        "library": library,
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_lunar_position_perf(lines_iter):
    """Performance measurement for lunar position computation."""
    ephemeris, reason = _astropy_ephemeris_config()
    if reason is not None:
        return _astropy_skipped_result("lunar_position_perf", reason)

    library, _model = _astropy_ephemeris_display(ephemeris)
    n = int(next(lines_iter).strip())
    jds = [float(next(lines_iter).strip()) for _ in range(n)]

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        try:
            _astropy_geometric_geocentric(jds[i], "moon", ephemeris)
        except Exception as exc:
            return _astropy_skipped_result("lunar_position_perf", f"Astropy failed to load BSP {ephemeris}: {exc}")

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd in jds:
        try:
            ra, dec, dist_au = _astropy_geometric_geocentric(jd, "moon", ephemeris)
        except Exception as exc:
            return _astropy_skipped_result("lunar_position_perf", f"Astropy failed during performance evaluation: {exc}")
        sink += ra + dec + dist_au
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "lunar_position_perf",
        "library": library,
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_planet_position_perf(lines_iter, experiment, planet_np):
    """Performance measurement for planetary position computation."""
    ephemeris, reason = _astropy_ephemeris_config()
    if reason is not None:
        return _astropy_skipped_result(f"{experiment}_perf", reason)
    planet_name = experiment.replace("_position", "").lower()

    library, _model = _astropy_ephemeris_display(ephemeris)
    n = int(next(lines_iter).strip())
    jds = [float(next(lines_iter).strip()) for _ in range(n)]

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        try:
            _astropy_geometric_geocentric(jds[i], planet_name, ephemeris)
        except Exception as exc:
            return _astropy_skipped_result(f"{experiment}_perf", f"Astropy failed to load BSP {ephemeris}: {exc}")

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd in jds:
        try:
            ra, dec, dist_au = _astropy_geometric_geocentric(jd, planet_name, ephemeris)
        except Exception as exc:
            return _astropy_skipped_result(f"{experiment}_perf", f"Astropy failed during performance evaluation: {exc}")
        sink += ra + dec + dist_au
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": f"{experiment}_perf",
        "library": library,
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_planet_barycenter_position_perf(lines_iter, experiment, planet_name):
    ephemeris, reason = _astropy_ephemeris_config()
    if reason is not None:
        return _astropy_skipped_result(f"{experiment}_perf", reason)

    library, _model = _astropy_ephemeris_display(ephemeris)
    n = int(next(lines_iter).strip())
    jds = [float(next(lines_iter).strip()) for _ in range(n)]

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        try:
            _astropy_geometric_geocentric(jds[i], planet_name.lower(), ephemeris)
        except Exception as exc:
            return _astropy_skipped_result(f"{experiment}_perf", f"Astropy failed to load BSP {ephemeris}: {exc}")

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd in jds:
        try:
            ra, dec, dist = _astropy_geometric_geocentric(jd, planet_name.lower(), ephemeris)
        except Exception as exc:
            return _astropy_skipped_result(f"{experiment}_perf", f"Astropy failed during performance evaluation: {exc}")
        sink += ra + dec + dist
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": f"{experiment}_perf",
        "library": library,
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()
