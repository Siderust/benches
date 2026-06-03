//! Siderust Adapter for the Lab Pipeline
//!
//! Reads experiment + inputs from stdin (simple text protocol),
//! runs Siderust transformations, writes JSON results to stdout.

mod common;
mod ephemerides;
mod frames;
mod kepler;
mod pointing;
mod time_earth_rotation;

pub(crate) use common::{
    affn, ang_sep, frame_rotation_selected, normalize3, pure_bpn_matrix, qtty,
    selected_nutation_profile, CartesianDirectionCompat,
};

use std::io::{self, BufRead};

use ephemerides::*;
use frames::*;
use kepler::*;
use pointing::*;
use time_earth_rotation::*;

fn main() {
    let stdin = io::stdin();
    let mut lines = stdin.lock().lines().map(|l| l.unwrap());

    let experiment_arg = std::env::args().nth(1);
    let experiment_stdin;
    let experiment = if let Some(arg) = experiment_arg.as_deref() {
        arg.trim()
    } else {
        experiment_stdin = lines.next().expect("expected experiment name");
        experiment_stdin.trim()
    };

    if experiment.ends_with("_setup") {
        ephemerides::run_setup(experiment);
        return;
    }

    match experiment {
        "frame_rotation_bpn" => run_frame_rotation_bpn(&mut lines),
        "gmst_era" => run_gmst_era(&mut lines),
        "equ_ecl" => run_equ_ecl(&mut lines),
        "equ_horizontal" => run_equ_horizontal(&mut lines),
        "solar_position" => run_solar_position(&mut lines),
        "lunar_position" => run_lunar_position(&mut lines),
        "mercury_position" => run_mercury_position(&mut lines),
        "venus_position" => run_venus_position(&mut lines),
        "mars_position" => run_mars_position(&mut lines),
        "jupiter_position" => run_jupiter_position(&mut lines),
        "saturn_position" => run_saturn_position(&mut lines),
        "uranus_position" => run_uranus_position(&mut lines),
        "neptune_position" => run_neptune_position(&mut lines),
        "mercury_barycenter_position" => run_mercury_barycenter_position(&mut lines),
        "venus_barycenter_position" => run_venus_barycenter_position(&mut lines),
        "mars_barycenter_position" => run_mars_barycenter_position(&mut lines),
        "jupiter_barycenter_position" => run_jupiter_barycenter_position(&mut lines),
        "saturn_barycenter_position" => run_saturn_barycenter_position(&mut lines),
        "uranus_barycenter_position" => run_uranus_barycenter_position(&mut lines),
        "neptune_barycenter_position" => run_neptune_barycenter_position(&mut lines),
        "kepler_solver" => run_kepler_solver(&mut lines),
        "frame_rotation_bpn_perf" => run_frame_rotation_bpn_perf(&mut lines),
        "gmst_era_perf" => run_gmst_era_perf(&mut lines),
        "equ_ecl_perf" => run_equ_ecl_perf(&mut lines),
        "equ_horizontal_perf" => run_equ_horizontal_perf(&mut lines),
        "solar_position_perf" => run_solar_position_perf(&mut lines),
        "lunar_position_perf" => run_lunar_position_perf(&mut lines),
        "mercury_position_perf" => run_mercury_position_perf(&mut lines),
        "venus_position_perf" => run_venus_position_perf(&mut lines),
        "mars_position_perf" => run_mars_position_perf(&mut lines),
        "jupiter_position_perf" => run_jupiter_position_perf(&mut lines),
        "saturn_position_perf" => run_saturn_position_perf(&mut lines),
        "uranus_position_perf" => run_uranus_position_perf(&mut lines),
        "neptune_position_perf" => run_neptune_position_perf(&mut lines),
        "mercury_barycenter_position_perf" => run_mercury_barycenter_position_perf(&mut lines),
        "venus_barycenter_position_perf" => run_venus_barycenter_position_perf(&mut lines),
        "mars_barycenter_position_perf" => run_mars_barycenter_position_perf(&mut lines),
        "jupiter_barycenter_position_perf" => run_jupiter_barycenter_position_perf(&mut lines),
        "saturn_barycenter_position_perf" => run_saturn_barycenter_position_perf(&mut lines),
        "uranus_barycenter_position_perf" => run_uranus_barycenter_position_perf(&mut lines),
        "neptune_barycenter_position_perf" => run_neptune_barycenter_position_perf(&mut lines),
        "kepler_solver_perf" => run_kepler_solver_perf(&mut lines),
        "frame_bias" => run_frame_bias(&mut lines),
        "frame_bias_perf" => run_frame_bias_perf(&mut lines),
        "precession" => run_precession(&mut lines),
        "precession_perf" => run_precession_perf(&mut lines),
        "nutation" => run_nutation(&mut lines),
        "nutation_perf" => run_nutation_perf(&mut lines),
        "icrs_ecl_j2000" => run_icrs_ecl_j2000(&mut lines),
        "icrs_ecl_j2000_perf" => run_icrs_ecl_j2000_perf(&mut lines),
        "icrs_ecl_tod" => run_icrs_ecl_tod(&mut lines),
        "icrs_ecl_tod_perf" => run_icrs_ecl_tod_perf(&mut lines),
        "horiz_to_equ" => run_horiz_to_equ(&mut lines),
        "horiz_to_equ_perf" => run_horiz_to_equ_perf(&mut lines),
        "inv_frame_bias" => run_inv_frame_bias(&mut lines),
        "inv_frame_bias_perf" => run_inv_frame_bias_perf(&mut lines),
        "inv_precession" => run_inv_precession(&mut lines),
        "inv_precession_perf" => run_inv_precession_perf(&mut lines),
        "inv_nutation" => run_inv_nutation(&mut lines),
        "inv_nutation_perf" => run_inv_nutation_perf(&mut lines),
        "inv_bpn" => run_inv_bpn(&mut lines),
        "inv_bpn_perf" => run_inv_bpn_perf(&mut lines),
        "inv_icrs_ecl_j2000" => run_inv_icrs_ecl_j2000(&mut lines),
        "inv_icrs_ecl_j2000_perf" => run_inv_icrs_ecl_j2000_perf(&mut lines),
        "obliquity" => run_obliquity(&mut lines),
        "obliquity_perf" => run_obliquity_perf(&mut lines),
        "inv_obliquity" => run_inv_obliquity(&mut lines),
        "inv_obliquity_perf" => run_inv_obliquity_perf(&mut lines),
        "bias_precession" => run_bias_precession(&mut lines),
        "bias_precession_perf" => run_bias_precession_perf(&mut lines),
        "inv_bias_precession" => run_inv_bias_precession(&mut lines),
        "inv_bias_precession_perf" => run_inv_bias_precession_perf(&mut lines),
        "precession_nutation" => run_precession_nutation(&mut lines),
        "precession_nutation_perf" => run_precession_nutation_perf(&mut lines),
        "inv_precession_nutation" => run_inv_precession_nutation(&mut lines),
        "inv_precession_nutation_perf" => run_inv_precession_nutation_perf(&mut lines),
        "inv_icrs_ecl_tod" => run_inv_icrs_ecl_tod(&mut lines),
        "inv_icrs_ecl_tod_perf" => run_inv_icrs_ecl_tod_perf(&mut lines),
        "inv_equ_ecl" => run_inv_equ_ecl(&mut lines),
        "inv_equ_ecl_perf" => run_inv_equ_ecl_perf(&mut lines),
        _ => {
            eprintln!("Unknown experiment: {}", experiment);
            std::process::exit(1);
        }
    }
}
