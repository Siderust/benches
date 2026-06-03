"""Shared helpers for the Astropy adapter experiments."""

import math

import numpy as np

PLANET_EXPERIMENTS = {
    "mercury_position": ("Mercury", 1),
    "venus_position": ("Venus", 2),
    "mars_position": ("Mars", 4),
    "jupiter_position": ("Jupiter", 5),
    "saturn_position": ("Saturn", 6),
    "uranus_position": ("Uranus", 7),
    "neptune_position": ("Neptune", 8),
}

# Planet system barycenters: same body names as PLANET_EXPERIMENTS since
# astropy's DE440/JPL backend maps these names to NAIF system-barycenter IDs
# (1=Mercury, 2=Venus, 4=Mars Barycenter, 5=Jupiter Barycenter, …).
PLANET_BARYCENTER_EXPERIMENTS = {
    "mercury_barycenter_position": ("mercury", 1),
    "venus_barycenter_position": ("venus", 2),
    "mars_barycenter_position": ("mars", 4),
    "jupiter_barycenter_position": ("jupiter", 5),
    "saturn_barycenter_position": ("saturn", 6),
    "uranus_barycenter_position": ("uranus", 7),
    "neptune_barycenter_position": ("neptune", 8),
}


def normalize3(v):
    r = np.linalg.norm(v)
    if r > 0:
        return v / r
    return v

def ang_sep(a, b):
    dot = np.clip(np.dot(a, b), -1.0, 1.0)
    return math.acos(dot)

def solve_kepler_newton(M_rad, e, max_iter=100, tol=1e-15):
    """Deprecated stub — Astropy has no public Kepler-equation solver.

    The audit removed the previous local Newton implementation: publishing
    a hand-rolled Kepler solver under the ``astropy`` name fabricated an
    upstream API surface that Astropy does not expose.  Kept only so that
    older callers fail loudly rather than silently re-using the helper.
    """
    raise RuntimeError(
        "Astropy does not expose a public Kepler-equation solver; "
        "this row is excluded by the capability catalog."
    )

def _astropy_geometric_geocentric(jd_tt, body, ephemeris):
    """Return (ra_rad, dec_rad, dist_au) on the geometric lane using
    Astropy's public ``solar_system_ephemeris`` + ``get_body_barycentric``
    API.  ``ephemeris`` is ``"builtin"`` or ``"jpl"``.

    Geometric (instantaneous) geocentric vector = body_bary − earth_bary.
    Apparent corrections (light-time, aberration) are intentionally
    omitted: this lane is the JPL-style geometric vector.
    """
    from astropy.coordinates import (
        solar_system_ephemeris, get_body_barycentric,
    )
    from astropy.time import Time
    t = Time(jd_tt, format="jd", scale="tt")
    with solar_system_ephemeris.set(ephemeris):
        body_b = get_body_barycentric(body, t)
        earth_b = get_body_barycentric("earth", t)
    dx = (body_b.x - earth_b.x).to_value("AU")
    dy = (body_b.y - earth_b.y).to_value("AU")
    dz = (body_b.z - earth_b.z).to_value("AU")
    dist_au = math.sqrt(dx * dx + dy * dy + dz * dz)
    ra = math.atan2(dy, dx) % (2 * math.pi)
    dec = math.asin(dz / dist_au)
    return ra, dec, dist_au

def _get_astropy_jpl():
    """Backwards-compat shim — returns no-longer-used helpers.

    Retained so any external diagnostic still imports cleanly.  The
    runtime path now goes through :func:`_astropy_geometric_geocentric`.
    """
    from astropy.coordinates import get_body
    from astropy.time import Time
    return get_body, Time

def sun_ra_dec_dist_jpl(jd_tt):
    """Sun geocentric geometric vector via Astropy's public JPL path.

    Uses ``solar_system_ephemeris.set('jpl') + get_body_barycentric``;
    the previous implementation read ``get_body(...).gcrs``, which is
    Astropy's *apparent* (light-time + aberration) coordinate and is
    therefore wrong for the geometric-vector lane (audit fix).
    """
    return _astropy_geometric_geocentric(jd_tt, "sun", "jpl")

def moon_ra_dec_dist_jpl(jd_tt):
    """Moon geocentric geometric vector via Astropy's public JPL path."""
    ra, dec, dist_au = _astropy_geometric_geocentric(jd_tt, "moon", "jpl")
    dist_km = dist_au * 149597870.700
    return ra, dec, dist_km

def planet_ra_dec_dist_jpl(jd_tt, planet_name):
    """Planet geocentric geometric vector via Astropy's public JPL path."""
    return _astropy_geometric_geocentric(jd_tt, planet_name.lower(), "jpl")
