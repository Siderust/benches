import json
import os
import math
import sys
import time

import numpy as np

try:
    from ..common import ang_sep
except ImportError:
    from common import ang_sep


def _configure_astropy():
    from astropy.utils import iers

    iers.conf.auto_download = False


def _time_from_tt_ut1(jd_tt, jd_ut1, location=None):
    from astropy.time import Time

    t = Time(jd_tt, format="jd", scale="tt", location=location)
    t.delta_ut1_utc = (jd_ut1 - t.utc.jd) * 86400.0
    return t


def _location(lon_rad, lat_rad):
    import astropy.units as u
    from astropy.coordinates import EarthLocation

    return EarthLocation.from_geodetic(
        lon=lon_rad * u.rad,
        lat=lat_rad * u.rad,
        height=0 * u.m,
    )


def _equ_to_horizontal(jd_ut1, jd_tt, ra_rad, dec_rad, obs_lon, obs_lat):
    import astropy.units as u
    from astropy.coordinates import AltAz, SkyCoord, TETE

    loc = _location(obs_lon, obs_lat)
    t = _time_from_tt_ut1(jd_tt, jd_ut1, loc)
    coord = SkyCoord(
        ra=ra_rad * u.rad,
        dec=dec_rad * u.rad,
        frame=TETE(obstime=t, location=loc),
    )
    altaz = coord.transform_to(AltAz(obstime=t, location=loc, pressure=0 * u.hPa))
    back = altaz.transform_to(TETE(obstime=t, location=loc))
    return float(altaz.az.rad), float(altaz.alt.rad), float(back.ra.rad), float(back.dec.rad)


def _horizontal_to_equ(jd_ut1, jd_tt, az_rad, alt_rad, obs_lon, obs_lat):
    import astropy.units as u
    from astropy.coordinates import AltAz, SkyCoord, TETE

    loc = _location(obs_lon, obs_lat)
    t = _time_from_tt_ut1(jd_tt, jd_ut1, loc)
    coord = SkyCoord(
        az=az_rad * u.rad,
        alt=alt_rad * u.rad,
        frame=AltAz(obstime=t, location=loc, pressure=0 * u.hPa),
    )
    equ = coord.transform_to(TETE(obstime=t, location=loc))
    back = equ.transform_to(AltAz(obstime=t, location=loc, pressure=0 * u.hPa))
    equ_back = back.transform_to(TETE(obstime=t, location=loc))
    return (
        float(equ.ra.rad),
        float(equ.dec.rad),
        float(equ_back.ra.rad),
        float(equ_back.dec.rad),
    )


def run_equ_horizontal(lines_iter):
    """Equatorial -> horizontal using Astropy public TETE/AltAz transforms."""
    _configure_astropy()
    n = int(next(lines_iter).strip())
    cases = []

    for _ in range(n):
        parts = next(lines_iter).strip().split()
        jd_ut1 = float(parts[0])
        jd_tt = float(parts[1])
        ra_rad = float(parts[2])
        dec_rad = float(parts[3])
        obs_lon = float(parts[4])
        obs_lat = float(parts[5])

        az, alt, ra_back, dec_back = _equ_to_horizontal(
            jd_ut1, jd_tt, ra_rad, dec_rad, obs_lon, obs_lat
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
            "jd_ut1": jd_ut1,
            "jd_tt": jd_tt,
            "ra_rad": ra_rad,
            "dec_rad": dec_rad,
            "obs_lon_rad": obs_lon,
            "obs_lat_rad": obs_lat,
            "az_rad": az,
            "alt_rad": alt,
            "closure_rad": closure_rad,
        })

    result = {
        "experiment": "equ_horizontal",
        "library": "astropy",
        "model": "Astropy SkyCoord TETE->AltAz transform",
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_equ_horizontal_perf(lines_iter):
    _configure_astropy()
    n = int(next(lines_iter).strip())
    params = []
    for _ in range(n):
        parts = next(lines_iter).strip().split()
        params.append(tuple(float(p) for p in parts))

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        _equ_to_horizontal(*params[i])

    t0 = time.perf_counter_ns()
    sink = 0.0
    for params_i in params:
        az, alt, _ra_back, _dec_back = _equ_to_horizontal(*params_i)
        sink += az + alt
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "equ_horizontal_perf",
        "library": "astropy",
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_horiz_to_equ(lines_iter):
    """Horizontal -> equatorial using Astropy public AltAz/TETE transforms."""
    _configure_astropy()
    n = int(next(lines_iter).strip())
    cases = []

    for _ in range(n):
        parts = next(lines_iter).strip().split()
        jd_ut1 = float(parts[0])
        jd_tt = float(parts[1])
        az_rad = float(parts[2])
        alt_rad = float(parts[3])
        obs_lon = float(parts[4])
        obs_lat = float(parts[5])

        ra, dec, ra_back, dec_back = _horizontal_to_equ(
            jd_ut1, jd_tt, az_rad, alt_rad, obs_lon, obs_lat
        )

        v_in = np.array([
            math.cos(dec) * math.cos(ra),
            math.cos(dec) * math.sin(ra),
            math.sin(dec),
        ])
        v_bk = np.array([
            math.cos(dec_back) * math.cos(ra_back),
            math.cos(dec_back) * math.sin(ra_back),
            math.sin(dec_back),
        ])
        closure_rad = ang_sep(v_in, v_bk)

        cases.append({
            "jd_ut1": jd_ut1,
            "jd_tt": jd_tt,
            "az_rad": az_rad,
            "alt_rad": alt_rad,
            "obs_lon_rad": obs_lon,
            "obs_lat_rad": obs_lat,
            "ra_rad": ra,
            "dec_rad": dec,
            "closure_rad": closure_rad,
        })

    result = {
        "experiment": "horiz_to_equ",
        "library": "astropy",
        "model": "Astropy SkyCoord AltAz->TETE transform",
        "count": n,
        "cases": cases,
    }
    json.dump(result, sys.stdout, indent=None)
    print()


def run_horiz_to_equ_perf(lines_iter):
    _configure_astropy()
    n = int(next(lines_iter).strip())
    params = []
    for _ in range(n):
        parts = next(lines_iter).strip().split()
        params.append(tuple(float(p) for p in parts))

    warmup = int(os.environ.get("LAB_PERF_WARMUP", "100"))
    for i in range(min(n, warmup)):
        _horizontal_to_equ(*params[i])

    t0 = time.perf_counter_ns()
    sink = 0.0
    for params_i in params:
        ra, dec, _ra_back, _dec_back = _horizontal_to_equ(*params_i)
        sink += ra + dec
    elapsed_ns = time.perf_counter_ns() - t0

    result = {
        "experiment": "horiz_to_equ_perf",
        "library": "astropy",
        "count": n,
        "total_ns": elapsed_ns,
        "per_op_ns": elapsed_ns / n,
        "throughput_ops_s": n / (elapsed_ns * 1e-9),
        "_sink": float(sink),
    }
    json.dump(result, sys.stdout, indent=None)
    print()
