#!/usr/bin/env python3
"""Astropy adapter dispatcher for the Siderust Lab."""

import sys
import json
import time

try:
    from .common import PLANET_EXPERIMENTS, PLANET_BARYCENTER_EXPERIMENTS
    from .experiments import ephemerides, frames, kepler, pointing, time_earth_rotation
except ImportError:
    from common import PLANET_EXPERIMENTS, PLANET_BARYCENTER_EXPERIMENTS
    from experiments import ephemerides, frames, kepler, pointing, time_earth_rotation


def run_setup(experiment):
    import os

    setup_ms = 0.0
    measured = True
    barycenter_exps = set(PLANET_BARYCENTER_EXPERIMENTS.keys())
    if os.environ.get("ASTROPY_EPHEMERIS") == "jpl" and experiment.replace("_setup", "") in {
        "solar_position", "lunar_position", "mercury_position", "venus_position",
        "mars_position", "jupiter_position", "saturn_position", "uranus_position", "neptune_position",
    } | barycenter_exps:
        body = experiment.replace("_setup", "").replace("_position", "").replace("_barycenter", "")
        body = {"solar": "sun", "lunar": "moon"}.get(body, body)
        t0 = time.perf_counter_ns()
        try:
            from common import _astropy_geometric_geocentric
        except ImportError:
            from .common import _astropy_geometric_geocentric
        _astropy_geometric_geocentric(2451545.0, body, "jpl")
        setup_ms = (time.perf_counter_ns() - t0) / 1e6
        measured = True
    json.dump({"setup_ms": setup_ms, "measured": measured}, sys.stdout)
    print()


def build_dispatch():
    dispatch = {
        "frame_rotation_bpn": time_earth_rotation.run_frame_rotation_bpn,
        "gmst_era": time_earth_rotation.run_gmst_era,
        "equ_ecl": frames.run_equ_ecl,
        "equ_horizontal": pointing.run_equ_horizontal,
        "solar_position": ephemerides.run_solar_position,
        "lunar_position": ephemerides.run_lunar_position,
        "kepler_solver": kepler.run_kepler_solver,
        "frame_rotation_bpn_perf": time_earth_rotation.run_frame_rotation_bpn_perf,
        "gmst_era_perf": time_earth_rotation.run_gmst_era_perf,
        "equ_ecl_perf": frames.run_equ_ecl_perf,
        "equ_horizontal_perf": pointing.run_equ_horizontal_perf,
        "solar_position_perf": ephemerides.run_solar_position_perf,
        "lunar_position_perf": ephemerides.run_lunar_position_perf,
        "kepler_solver_perf": kepler.run_kepler_solver_perf,
        "frame_bias": time_earth_rotation.run_frame_bias,
        "frame_bias_perf": time_earth_rotation.run_frame_bias_perf,
        "precession": time_earth_rotation.run_precession,
        "precession_perf": time_earth_rotation.run_precession_perf,
        "nutation": time_earth_rotation.run_nutation,
        "nutation_perf": time_earth_rotation.run_nutation_perf,
        "icrs_ecl_j2000": frames.run_icrs_ecl_j2000,
        "icrs_ecl_j2000_perf": frames.run_icrs_ecl_j2000_perf,
        "icrs_ecl_tod": frames.run_icrs_ecl_tod,
        "icrs_ecl_tod_perf": frames.run_icrs_ecl_tod_perf,
        "horiz_to_equ": pointing.run_horiz_to_equ,
        "horiz_to_equ_perf": pointing.run_horiz_to_equ_perf,
        "inv_frame_bias": time_earth_rotation.run_inv_frame_bias,
        "inv_frame_bias_perf": time_earth_rotation.run_inv_frame_bias_perf,
        "inv_precession": time_earth_rotation.run_inv_precession,
        "inv_precession_perf": time_earth_rotation.run_inv_precession_perf,
        "inv_nutation": time_earth_rotation.run_inv_nutation,
        "inv_nutation_perf": time_earth_rotation.run_inv_nutation_perf,
        "inv_bpn": time_earth_rotation.run_inv_bpn,
        "inv_bpn_perf": time_earth_rotation.run_inv_bpn_perf,
        "inv_icrs_ecl_j2000": frames.run_inv_icrs_ecl_j2000,
        "inv_icrs_ecl_j2000_perf": frames.run_inv_icrs_ecl_j2000_perf,
        "obliquity": frames.run_obliquity,
        "obliquity_perf": frames.run_obliquity_perf,
        "inv_obliquity": frames.run_inv_obliquity,
        "inv_obliquity_perf": frames.run_inv_obliquity_perf,
        "bias_precession": time_earth_rotation.run_bias_precession,
        "bias_precession_perf": time_earth_rotation.run_bias_precession_perf,
        "inv_bias_precession": time_earth_rotation.run_inv_bias_precession,
        "inv_bias_precession_perf": time_earth_rotation.run_inv_bias_precession_perf,
        "precession_nutation": time_earth_rotation.run_precession_nutation,
        "precession_nutation_perf": time_earth_rotation.run_precession_nutation_perf,
        "inv_precession_nutation": time_earth_rotation.run_inv_precession_nutation,
        "inv_precession_nutation_perf": time_earth_rotation.run_inv_precession_nutation_perf,
        "inv_icrs_ecl_tod": frames.run_inv_icrs_ecl_tod,
        "inv_icrs_ecl_tod_perf": frames.run_inv_icrs_ecl_tod_perf,
        "inv_equ_ecl": frames.run_inv_equ_ecl,
        "inv_equ_ecl_perf": frames.run_inv_equ_ecl_perf,
    }

    for exp_name, (planet_name, planet_np) in PLANET_EXPERIMENTS.items():
        dispatch[exp_name] = (
            lambda lines_iter, exp_name=exp_name, planet_name=planet_name, planet_np=planet_np:
                ephemerides.run_planet_position(lines_iter, exp_name, planet_name, planet_np)
        )
        dispatch[f"{exp_name}_perf"] = (
            lambda lines_iter, exp_name=exp_name, planet_np=planet_np:
                ephemerides.run_planet_position_perf(lines_iter, exp_name, planet_np)
        )

    for exp_name, (planet_name, planet_np) in PLANET_BARYCENTER_EXPERIMENTS.items():
        dispatch[exp_name] = (
            lambda lines_iter, exp_name=exp_name, planet_name=planet_name:
                ephemerides.run_planet_barycenter_position(lines_iter, exp_name, planet_name)
        )
        dispatch[f"{exp_name}_perf"] = (
            lambda lines_iter, exp_name=exp_name, planet_name=planet_name:
                ephemerides.run_planet_barycenter_position_perf(lines_iter, exp_name, planet_name)
        )
    return dispatch


def main():
    lines_iter = iter(sys.stdin)
    experiment = sys.argv[1] if len(sys.argv) > 1 else next(lines_iter).strip()
    dispatch = build_dispatch()

    if experiment.endswith("_setup"):
        run_setup(experiment)
        return

    if experiment not in dispatch:
        print(f"Unknown experiment: {experiment}", file=sys.stderr)
        sys.exit(1)

    dispatch[experiment](lines_iter)


if __name__ == "__main__":
    main()
