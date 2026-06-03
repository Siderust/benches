import json
import math
import sys
import time

try:
    from ..common import PLANET_EXPERIMENTS, PLANET_BARYCENTER_EXPERIMENTS, _astropy_geometric_geocentric
except ImportError:
    from common import PLANET_EXPERIMENTS, PLANET_BARYCENTER_EXPERIMENTS, _astropy_geometric_geocentric


def run_solar_position(lines_iter):
    """Sun geocentric RA/Dec via Astropy's public ephemeris API.

    ``ASTROPY_EPHEMERIS=jpl`` selects the JPL DE kernel (downloaded /
    cached by Astropy on first use); otherwise the bundled analytic
    ``builtin`` ephemeris is used.  Both go through
    ``solar_system_ephemeris.set(...) + get_body_barycentric`` so the
    published row honestly represents Astropy's public client API.
    """
    import os
    use_jpl = os.environ.get("ASTROPY_EPHEMERIS") == "jpl"
    ephemeris = "jpl" if use_jpl else "builtin"

    n = int(next(lines_iter).strip())
    cases = []
    for _ in range(n):
        jd_tt = float(next(lines_iter).strip())
        ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, "sun", ephemeris)
        cases.append({"jd_tt": jd_tt, "ra_rad": ra, "dec_rad": dec, "dist_au": dist_au})

    result = {
        "experiment": "solar_position",
        "library": "astropy_jpl" if use_jpl else "astropy",
        "model": (
            "Astropy solar_system_ephemeris('jpl') + get_body_barycentric"
            if use_jpl else "Astropy solar_system_ephemeris('builtin') + get_body_barycentric"
        ),
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_lunar_position(lines_iter):
    """Moon geocentric RA/Dec via Astropy's public ephemeris API."""
    import os
    use_jpl = os.environ.get("ASTROPY_EPHEMERIS") == "jpl"
    ephemeris = "jpl" if use_jpl else "builtin"

    n = int(next(lines_iter).strip())
    cases = []
    for _ in range(n):
        jd_tt = float(next(lines_iter).strip())
        ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, "moon", ephemeris)
        cases.append({
            "jd_tt": jd_tt,
            "ra_rad": ra,
            "dec_rad": dec,
            "dist_km": dist_au * 149597870.700,
        })

    result = {
        "experiment": "lunar_position",
        "library": "astropy_jpl" if use_jpl else "astropy",
        "model": (
            "Astropy solar_system_ephemeris('jpl') + get_body_barycentric"
            if use_jpl else "Astropy solar_system_ephemeris('builtin') + get_body_barycentric"
        ),
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_planet_position(lines_iter, experiment, planet_name, planet_np):
    """Planet geocentric RA/Dec via Astropy's public ephemeris API."""
    import os
    use_jpl = os.environ.get("ASTROPY_EPHEMERIS") == "jpl"
    ephemeris = "jpl" if use_jpl else "builtin"

    n = int(next(lines_iter).strip())
    cases = []
    for _ in range(n):
        jd_tt = float(next(lines_iter).strip())
        ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, planet_name.lower(), ephemeris)
        cases.append({"jd_tt": jd_tt, "ra_rad": ra, "dec_rad": dec, "dist_au": dist_au})

    result = {
        "experiment": experiment,
        "library": "astropy_jpl" if use_jpl else "astropy",
        "model": (
            f"Astropy solar_system_ephemeris('jpl') + get_body_barycentric({planet_name})"
            if use_jpl else f"Astropy solar_system_ephemeris('builtin') + get_body_barycentric({planet_name})"
        ),
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
    n = int(next(lines_iter).strip())
    cases = []
    for _ in range(n):
        jd_tt = float(next(lines_iter).strip())
        ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, planet_name.lower(), "jpl")
        cases.append({"jd_tt": jd_tt, "ra_rad": ra, "dec_rad": dec, "dist_au": dist_au})

    result = {
        "experiment": experiment,
        "library": "astropy_jpl",
        "model": f"Astropy solar_system_ephemeris('jpl') + get_body_barycentric({planet_name}) [system barycenter]",
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_solar_position_perf(lines_iter):
    """Performance measurement for solar position computation."""
    import os
    use_jpl = os.environ.get("ASTROPY_EPHEMERIS") == "jpl"
    ephemeris = "jpl" if use_jpl else "builtin"

    n = int(next(lines_iter).strip())
    jds = [float(next(lines_iter).strip()) for _ in range(n)]

    for i in range(min(n, 100)):
        _astropy_geometric_geocentric(jds[i], "sun", ephemeris)

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd in jds:
        ra, dec, dist = _astropy_geometric_geocentric(jd, "sun", ephemeris)
        sink += ra + dec + dist
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "solar_position_perf",
        "library": "astropy_jpl" if use_jpl else "astropy",
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
    import os
    use_jpl = os.environ.get("ASTROPY_EPHEMERIS") == "jpl"
    ephemeris = "jpl" if use_jpl else "builtin"

    n = int(next(lines_iter).strip())
    jds = [float(next(lines_iter).strip()) for _ in range(n)]

    for i in range(min(n, 100)):
        _astropy_geometric_geocentric(jds[i], "moon", ephemeris)

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd in jds:
        ra, dec, dist_au = _astropy_geometric_geocentric(jd, "moon", ephemeris)
        sink += ra + dec + dist_au
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "lunar_position_perf",
        "library": "astropy_jpl" if use_jpl else "astropy",
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
    import os
    use_jpl = os.environ.get("ASTROPY_EPHEMERIS") == "jpl"
    ephemeris = "jpl" if use_jpl else "builtin"
    planet_name = experiment.replace("_position", "").lower()

    n = int(next(lines_iter).strip())
    jds = [float(next(lines_iter).strip()) for _ in range(n)]

    for i in range(min(n, 100)):
        _astropy_geometric_geocentric(jds[i], planet_name, ephemeris)

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd in jds:
        ra, dec, dist_au = _astropy_geometric_geocentric(jd, planet_name, ephemeris)
        sink += ra + dec + dist_au
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": f"{experiment}_perf",
        "library": "astropy_jpl" if use_jpl else "astropy",
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_planet_barycenter_position_perf(lines_iter, experiment, planet_name):
    n = int(next(lines_iter).strip())
    jds = [float(next(lines_iter).strip()) for _ in range(n)]

    for i in range(min(n, 100)):
        _astropy_geometric_geocentric(jds[i], planet_name.lower(), "jpl")

    t0 = time.perf_counter_ns()
    sink = 0.0
    for jd in jds:
        ra, dec, dist = _astropy_geometric_geocentric(jd, planet_name.lower(), "jpl")
        sink += ra + dec + dist
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": f"{experiment}_perf",
        "library": "astropy_jpl",
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()
