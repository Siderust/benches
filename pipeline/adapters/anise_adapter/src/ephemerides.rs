use anise::constants::celestial_objects::{JUPITER, MARS, MERCURY, NEPTUNE, SATURN, URANUS, VENUS};
use anise::constants::frames::{
    EARTH_J2000, JUPITER_BARYCENTER_J2000, MARS_BARYCENTER_J2000, MERCURY_J2000, MOON_J2000,
    NEPTUNE_BARYCENTER_J2000, SATURN_BARYCENTER_J2000, SUN_J2000, URANUS_BARYCENTER_J2000,
    VENUS_J2000,
};
use anise::constants::orientations::J2000;
use anise::math::cartesian::CartesianState;
use anise::prelude::{Aberration, Almanac, Frame};

use std::io::{self, Write};
use std::time::Instant;

use crate::common::{
    epoch_from_jd_tt, load_ephemeris_almanac, read_n, sanitized_reason, skip_experiment, KM_PER_AU,
};

fn run_solar_position(lines: &mut impl Iterator<Item = String>) {
    let n = read_n(lines);
    let almanac = load_ephemeris_almanac().unwrap();

    let stdout = io::stdout();
    let mut out = stdout.lock();

    write!(
        out,
        "{{\"experiment\":\"solar_position\",\"library\":\"anise\",\"model\":\"SPK_geometric_translation(SUN_J2000->EARTH_J2000)\",\"count\":{},\"cases\":[\n",
        n
    )
    .unwrap();

    for i in 0..n {
        let jd_tt: f64 = lines.next().unwrap().trim().parse().unwrap();
        let epoch = epoch_from_jd_tt(jd_tt);

        let state = match almanac.translate(SUN_J2000, EARTH_J2000, epoch, Aberration::NONE) {
            Ok(s) => s,
            Err(_) => {
                if i > 0 {
                    write!(out, ",\n").unwrap();
                }
                write!(
                    out,
                    "{{\"jd_tt\":{:.15},\"ra_rad\":null,\"dec_rad\":null,\"dist_au\":null}}",
                    jd_tt
                )
                .unwrap();
                continue;
            }
        };

        let x = state.radius_km[0];
        let y = state.radius_km[1];
        let z = state.radius_km[2];
        let dist_km = state.radius_km.norm();
        let ra = y.atan2(x).rem_euclid(2.0 * std::f64::consts::PI);
        let dec = (z / dist_km).asin();
        let dist_au = dist_km / KM_PER_AU;

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{:.15},\"ra_rad\":{:.17e},\"dec_rad\":{:.17e},\"dist_au\":{:.17e}}}",
            jd_tt, ra, dec, dist_au
        )
        .unwrap();
    }

    writeln!(out, "\n]}}").unwrap();
}

fn run_lunar_position(lines: &mut impl Iterator<Item = String>) {
    let n = read_n(lines);
    let almanac = load_ephemeris_almanac().unwrap();

    let stdout = io::stdout();
    let mut out = stdout.lock();

    write!(
        out,
        "{{\"experiment\":\"lunar_position\",\"library\":\"anise\",\"model\":\"SPK_geometric_translation(MOON_J2000->EARTH_J2000)\",\"count\":{},\"cases\":[\n",
        n
    )
    .unwrap();

    for i in 0..n {
        let jd_tt: f64 = lines.next().unwrap().trim().parse().unwrap();
        let epoch = epoch_from_jd_tt(jd_tt);

        let state = match almanac.translate(MOON_J2000, EARTH_J2000, epoch, Aberration::NONE) {
            Ok(s) => s,
            Err(_) => {
                if i > 0 {
                    write!(out, ",\n").unwrap();
                }
                write!(
                    out,
                    "{{\"jd_tt\":{:.15},\"ra_rad\":null,\"dec_rad\":null,\"dist_km\":null}}",
                    jd_tt
                )
                .unwrap();
                continue;
            }
        };

        let x = state.radius_km[0];
        let y = state.radius_km[1];
        let z = state.radius_km[2];
        let dist_km = state.radius_km.norm();
        let ra = y.atan2(x).rem_euclid(2.0 * std::f64::consts::PI);
        let dec = (z / dist_km).asin();

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{:.15},\"ra_rad\":{:.17e},\"dec_rad\":{:.17e},\"dist_km\":{:.17e}}}",
            jd_tt, ra, dec, dist_km
        )
        .unwrap();
    }

    writeln!(out, "\n]}}").unwrap();
}

fn run_planet_position(
    lines: &mut impl Iterator<Item = String>,
    experiment: &str,
    planet_name: &str,
    target_frame: Frame,
) {
    let n = read_n(lines);
    let almanac = load_ephemeris_almanac().unwrap();

    let mut jds = Vec::with_capacity(n);
    for _ in 0..n {
        jds.push(lines.next().unwrap().trim().parse::<f64>().unwrap());
    }

    if let Some(first_jd) = jds.first() {
        let epoch = epoch_from_jd_tt(*first_jd);
        if let Err(err) = almanac.translate(target_frame, EARTH_J2000, epoch, Aberration::NONE) {
            println!(
                "{{\"experiment\":\"{}\",\"library\":\"anise\",\"skipped\":true,\"reason\":\"{}\"}}",
                experiment,
                sanitized_reason(&format!(
                    "ANISE direct {} frame is unavailable in the loaded SPK: {}",
                    planet_name, err
                ))
            );
            return;
        }
    }

    let stdout = io::stdout();
    let mut out = stdout.lock();

    write!(
        out,
        "{{\"experiment\":\"{}\",\"library\":\"anise\",\"model\":\"SPK_geometric_translation({}->EARTH_J2000)\",\"count\":{},\"cases\":[\n",
        experiment, planet_name, n
    )
    .unwrap();

    for (i, jd_tt) in jds.iter().enumerate() {
        let epoch = epoch_from_jd_tt(*jd_tt);

        let state = match almanac.translate(target_frame, EARTH_J2000, epoch, Aberration::NONE) {
            Ok(s) => s,
            Err(_) => {
                if i > 0 {
                    write!(out, ",\n").unwrap();
                }
                write!(
                    out,
                    "{{\"jd_tt\":{:.15},\"ra_rad\":null,\"dec_rad\":null,\"dist_au\":null}}",
                    jd_tt
                )
                .unwrap();
                continue;
            }
        };

        let x = state.radius_km[0];
        let y = state.radius_km[1];
        let z = state.radius_km[2];
        let dist_km = state.radius_km.norm();
        let ra = y.atan2(x).rem_euclid(2.0 * std::f64::consts::PI);
        let dec = (z / dist_km).asin();
        let dist_au = dist_km / KM_PER_AU;

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{:.15},\"ra_rad\":{:.17e},\"dec_rad\":{:.17e},\"dist_au\":{:.17e}}}",
            jd_tt, ra, dec, dist_au
        )
        .unwrap();
    }

    writeln!(out, "\n]}}").unwrap();
}

fn translate_state_sink(state: &CartesianState, sink: &mut f64) {
    let x = state.radius_km[0];
    let y = state.radius_km[1];
    let z = state.radius_km[2];
    let dist_km = state.radius_km.norm();
    let ra = y.atan2(x).rem_euclid(2.0 * std::f64::consts::PI);
    let dec = (z / dist_km).asin();
    *sink += ra + dec + dist_km / KM_PER_AU;
    std::hint::black_box((ra, dec, dist_km));
}

fn emit_anise_perf_skip(experiment: &str, count_requested: usize, reason: &str) {
    println!(
        "{{\"experiment\":\"{experiment}_perf\",\"library\":\"anise\",\
         \"count_requested\":{count_requested},\"count_valid\":0,\"error_count\":{count_requested},\
         \"count\":{count_requested},\"valid\":false,\"skipped\":true,\
         \"reason\":\"{}\"}}",
        sanitized_reason(reason),
    );
}

fn emit_anise_valid_perf(
    experiment: &str,
    count_requested: usize,
    total_ns: f64,
    sink: f64,
) {
    let per_op_ns = total_ns / count_requested as f64;
    println!(
        "{{\"experiment\":\"{experiment}_perf\",\"library\":\"anise\",\
         \"count_requested\":{count_requested},\"count_valid\":{count_requested},\
         \"error_count\":0,\"count\":{count_requested},\"valid\":true,\"skipped\":false,\
         \"total_ns\":{total_ns:.0},\"per_op_ns\":{per_op_ns:.1},\
         \"throughput_ops_s\":{:.0},\"_sink\":{sink:.17e}}}",
        count_requested as f64 / (total_ns * 1e-9),
    );
}

/// Preflight every epoch, then time a full successful batch (no silent `if let Ok` drops).
fn run_translate_ephemeris_perf(
    experiment: &str,
    jds: &[f64],
    almanac: &Almanac,
    from: Frame,
    to: Frame,
    planet_label: Option<&str>,
) {
    let n = jds.len();
    for jd in jds {
        let epoch = epoch_from_jd_tt(*jd);
        if let Err(err) = almanac.translate(from, to, epoch, Aberration::NONE) {
            let reason = match planet_label {
                Some(name) => format!(
                    "ANISE {name} frame unavailable in the loaded SPK: {err}"
                ),
                None => format!("ANISE translate failed: {err}"),
            };
            emit_anise_perf_skip(experiment, n, &reason);
            return;
        }
    }

    let warmup = crate::perf_warmup();
    for jd in jds.iter().take(n.min(warmup)) {
        let epoch = epoch_from_jd_tt(*jd);
        let state = almanac
            .translate(from, to, epoch, Aberration::NONE)
            .expect("preflight guaranteed success");
        let mut warmup_sink = 0.0_f64;
        translate_state_sink(&state, &mut warmup_sink);
    }

    let start = Instant::now();
    let mut sink = 0.0_f64;
    for jd in jds {
        let epoch = epoch_from_jd_tt(*jd);
        let state = almanac
            .translate(from, to, epoch, Aberration::NONE)
            .expect("preflight guaranteed success");
        translate_state_sink(&state, &mut sink);
    }
    let total_ns = start.elapsed().as_nanos() as f64;
    emit_anise_valid_perf(experiment, n, total_ns, sink);
}

fn run_solar_position_perf(lines: &mut impl Iterator<Item = String>) {
    let n = read_n(lines);
    let almanac = load_ephemeris_almanac().unwrap();
    let mut jds = Vec::with_capacity(n);
    for _ in 0..n {
        jds.push(lines.next().unwrap().trim().parse::<f64>().unwrap());
    }
    run_translate_ephemeris_perf("solar_position", &jds, &almanac, SUN_J2000, EARTH_J2000, None);
}

fn run_lunar_position_perf(lines: &mut impl Iterator<Item = String>) {
    let n = read_n(lines);
    let almanac = load_ephemeris_almanac().unwrap();
    let mut jds = Vec::with_capacity(n);
    for _ in 0..n {
        jds.push(lines.next().unwrap().trim().parse::<f64>().unwrap());
    }
    run_translate_ephemeris_perf("lunar_position", &jds, &almanac, MOON_J2000, EARTH_J2000, None);
}

fn run_planet_position_perf(
    lines: &mut impl Iterator<Item = String>,
    experiment: &str,
    planet_name: &str,
    target_frame: Frame,
) {
    let n = read_n(lines);
    let almanac = load_ephemeris_almanac().unwrap();
    let mut jds = Vec::with_capacity(n);
    for _ in 0..n {
        jds.push(lines.next().unwrap().trim().parse::<f64>().unwrap());
    }
    run_translate_ephemeris_perf(
        experiment,
        &jds,
        &almanac,
        target_frame,
        EARTH_J2000,
        Some(planet_name),
    );
}

pub(crate) fn is_ephemeris_experiment(experiment: &str) -> bool {
    matches!(
        experiment,
        "solar_position"
            | "solar_position_perf"
            | "lunar_position"
            | "lunar_position_perf"
            | "mercury_position"
            | "mercury_position_perf"
            | "venus_position"
            | "venus_position_perf"
            | "mars_position"
            | "mars_position_perf"
            | "jupiter_position"
            | "jupiter_position_perf"
            | "saturn_position"
            | "saturn_position_perf"
            | "uranus_position"
            | "uranus_position_perf"
            | "neptune_position"
            | "neptune_position_perf"
            | "mercury_barycenter_position"
            | "mercury_barycenter_position_perf"
            | "venus_barycenter_position"
            | "venus_barycenter_position_perf"
            | "mars_barycenter_position"
            | "mars_barycenter_position_perf"
            | "jupiter_barycenter_position"
            | "jupiter_barycenter_position_perf"
            | "saturn_barycenter_position"
            | "saturn_barycenter_position_perf"
            | "uranus_barycenter_position"
            | "uranus_barycenter_position_perf"
            | "neptune_barycenter_position"
            | "neptune_barycenter_position_perf"
    )
}

pub(crate) fn dispatch(experiment: &str, lines: &mut impl Iterator<Item = String>) -> bool {
    match experiment {
        "solar_position" => run_solar_position(lines),
        "solar_position_perf" => run_solar_position_perf(lines),
        "lunar_position" => run_lunar_position(lines),
        "lunar_position_perf" => run_lunar_position_perf(lines),
        "mercury_position" => {
            run_planet_position(lines, "mercury_position", "Mercury", Frame::new(MERCURY, J2000))
        }
        "mercury_position_perf" => run_planet_position_perf(
            lines,
            "mercury_position",
            "Mercury",
            Frame::new(MERCURY, J2000),
        ),
        "venus_position" => {
            run_planet_position(lines, "venus_position", "Venus", Frame::new(VENUS, J2000))
        }
        "venus_position_perf" => run_planet_position_perf(
            lines,
            "venus_position",
            "Venus",
            Frame::new(VENUS, J2000),
        ),
        "mars_position" => {
            run_planet_position(lines, "mars_position", "Mars", Frame::new(MARS, J2000))
        }
        "mars_position_perf" => run_planet_position_perf(
            lines,
            "mars_position",
            "Mars",
            Frame::new(MARS, J2000),
        ),
        "jupiter_position" => run_planet_position(
            lines,
            "jupiter_position",
            "Jupiter",
            Frame::new(JUPITER, J2000),
        ),
        "jupiter_position_perf" => run_planet_position_perf(
            lines,
            "jupiter_position",
            "Jupiter",
            Frame::new(JUPITER, J2000),
        ),
        "saturn_position" => {
            run_planet_position(lines, "saturn_position", "Saturn", Frame::new(SATURN, J2000))
        }
        "saturn_position_perf" => run_planet_position_perf(
            lines,
            "saturn_position",
            "Saturn",
            Frame::new(SATURN, J2000),
        ),
        "uranus_position" => {
            run_planet_position(lines, "uranus_position", "Uranus", Frame::new(URANUS, J2000))
        }
        "uranus_position_perf" => run_planet_position_perf(
            lines,
            "uranus_position",
            "Uranus",
            Frame::new(URANUS, J2000),
        ),
        "neptune_position" => run_planet_position(
            lines,
            "neptune_position",
            "Neptune",
            Frame::new(NEPTUNE, J2000),
        ),
        "neptune_position_perf" => run_planet_position_perf(
            lines,
            "neptune_position",
            "Neptune",
            Frame::new(NEPTUNE, J2000),
        ),
        "solar_ssb_position" | "solar_ssb_position_perf"
        | "lunar_ssb_position" | "lunar_ssb_position_perf"
        | "mercury_ssb_position" | "mercury_ssb_position_perf"
        | "venus_ssb_position" | "venus_ssb_position_perf"
        | "mars_ssb_position" | "mars_ssb_position_perf"
        | "jupiter_ssb_position" | "jupiter_ssb_position_perf"
        | "saturn_ssb_position" | "saturn_ssb_position_perf"
        | "uranus_ssb_position" | "uranus_ssb_position_perf"
        | "neptune_ssb_position" | "neptune_ssb_position_perf" => {
            skip_experiment(lines, experiment, "SSB lane has been removed from the lab")
        }
        "mercury_barycenter_position" => {
            run_planet_position(lines, "mercury_barycenter_position", "Mercury Barycenter", MERCURY_J2000)
        }
        "mercury_barycenter_position_perf" => run_planet_position_perf(
            lines,
            "mercury_barycenter_position",
            "Mercury Barycenter",
            MERCURY_J2000,
        ),
        "venus_barycenter_position" => {
            run_planet_position(lines, "venus_barycenter_position", "Venus Barycenter", VENUS_J2000)
        }
        "venus_barycenter_position_perf" => run_planet_position_perf(
            lines,
            "venus_barycenter_position",
            "Venus Barycenter",
            VENUS_J2000,
        ),
        "mars_barycenter_position" => {
            run_planet_position(lines, "mars_barycenter_position", "Mars Barycenter", MARS_BARYCENTER_J2000)
        }
        "mars_barycenter_position_perf" => run_planet_position_perf(
            lines,
            "mars_barycenter_position",
            "Mars Barycenter",
            MARS_BARYCENTER_J2000,
        ),
        "jupiter_barycenter_position" => run_planet_position(
            lines,
            "jupiter_barycenter_position",
            "Jupiter Barycenter",
            JUPITER_BARYCENTER_J2000,
        ),
        "jupiter_barycenter_position_perf" => run_planet_position_perf(
            lines,
            "jupiter_barycenter_position",
            "Jupiter Barycenter",
            JUPITER_BARYCENTER_J2000,
        ),
        "saturn_barycenter_position" => {
            run_planet_position(lines, "saturn_barycenter_position", "Saturn Barycenter", SATURN_BARYCENTER_J2000)
        }
        "saturn_barycenter_position_perf" => run_planet_position_perf(
            lines,
            "saturn_barycenter_position",
            "Saturn Barycenter",
            SATURN_BARYCENTER_J2000,
        ),
        "uranus_barycenter_position" => {
            run_planet_position(lines, "uranus_barycenter_position", "Uranus Barycenter", URANUS_BARYCENTER_J2000)
        }
        "uranus_barycenter_position_perf" => run_planet_position_perf(
            lines,
            "uranus_barycenter_position",
            "Uranus Barycenter",
            URANUS_BARYCENTER_J2000,
        ),
        "neptune_barycenter_position" => run_planet_position(
            lines,
            "neptune_barycenter_position",
            "Neptune Barycenter",
            NEPTUNE_BARYCENTER_J2000,
        ),
        "neptune_barycenter_position_perf" => run_planet_position_perf(
            lines,
            "neptune_barycenter_position",
            "Neptune Barycenter",
            NEPTUNE_BARYCENTER_J2000,
        ),
        "kepler_solver" => skip_experiment(
            lines,
            "kepler_solver",
            "ANISE adapter does not include standalone Kepler solver benchmark path in this lab integration",
        ),
        "kepler_solver_perf" => skip_experiment(
            lines,
            "kepler_solver_perf",
            "ANISE adapter does not include standalone Kepler solver benchmark path in this lab integration",
        ),
        _ => return false,
    }
    true
}
