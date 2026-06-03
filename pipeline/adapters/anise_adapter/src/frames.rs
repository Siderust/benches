use anise::constants::orientations::{ECLIPJ2000, J2000, J2000_TO_ECLIPJ2000_ANGLE_RAD};
use anise::math::rotation::DCM;
use anise::math::Vector3;

use std::io::{self, Write};
use std::time::Instant;

use crate::common::{ang_sep, normalize, parse_numbers, read_n, skip_experiment};

fn run_direction_rotation(
    lines: &mut impl Iterator<Item = String>,
    exp_name: &str,
    model: &str,
    j2000_to_ecliptic: bool,
) {
    let n = read_n(lines);
    let base = DCM::r1(J2000_TO_ECLIPJ2000_ANGLE_RAD, J2000, ECLIPJ2000);

    let stdout = io::stdout();
    let mut out = stdout.lock();

    write!(
        out,
        "{{\"experiment\":\"{}\",\"library\":\"anise\",\"model\":\"{}\",\"count\":{},\"cases\":[\n",
        exp_name, model, n
    )
    .unwrap();

    for i in 0..n {
        let p = parse_numbers(&lines.next().unwrap());
        let jd_tt = p[0];

        let dcm = if j2000_to_ecliptic {
            base
        } else {
            base.transpose()
        };

        let vin = normalize(Vector3::new(p[1], p[2], p[3]));
        let vout = dcm * vin;
        let vback = dcm.transpose() * vout;
        let closure = ang_sep(vin, vback);

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{:.15},\"input\":[{:.17e},{:.17e},{:.17e}],\"output\":[{:.17e},{:.17e},{:.17e}],\"closure_rad\":{:.17e},\"matrix\":[[{:.17e},{:.17e},{:.17e}],[{:.17e},{:.17e},{:.17e}],[{:.17e},{:.17e},{:.17e}]]}}",
            jd_tt,
            vin[0],
            vin[1],
            vin[2],
            vout[0],
            vout[1],
            vout[2],
            closure,
            dcm.rot_mat[(0, 0)],
            dcm.rot_mat[(0, 1)],
            dcm.rot_mat[(0, 2)],
            dcm.rot_mat[(1, 0)],
            dcm.rot_mat[(1, 1)],
            dcm.rot_mat[(1, 2)],
            dcm.rot_mat[(2, 0)],
            dcm.rot_mat[(2, 1)],
            dcm.rot_mat[(2, 2)],
        )
        .unwrap();
    }

    writeln!(out, "\n]}}").unwrap();
}

fn run_direction_rotation_perf(
    lines: &mut impl Iterator<Item = String>,
    exp_name: &str,
    j2000_to_ecliptic: bool,
) {
    let n = read_n(lines);
    let base = DCM::r1(J2000_TO_ECLIPJ2000_ANGLE_RAD, J2000, ECLIPJ2000);

    let mut jds = Vec::with_capacity(n);
    let mut vecs = Vec::with_capacity(n);
    for _ in 0..n {
        let p = parse_numbers(&lines.next().unwrap());
        jds.push(p[0]);
        vecs.push(normalize(Vector3::new(p[1], p[2], p[3])));
    }

    let warmup = crate::perf_warmup();
    for i in 0..n.min(warmup) {
        let _ = jds[i];
        let dcm = if j2000_to_ecliptic {
            base
        } else {
            base.transpose()
        };
        let out = dcm * vecs[i];
        std::hint::black_box(out);
    }

    let start = Instant::now();
    let mut sink = 0.0_f64;
    for i in 0..n {
        let _ = jds[i];
        let dcm = if j2000_to_ecliptic {
            base
        } else {
            base.transpose()
        };
        let out = dcm * vecs[i];
        sink = out[0];
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;

    println!(
        "{{\"experiment\":\"{}\",\"library\":\"anise\",\"count\":{},\"total_ns\":{:.0},\"per_op_ns\":{:.1},\"throughput_ops_s\":{:.0},\"_sink\":{:.17e}}}",
        exp_name,
        n,
        total_ns,
        total_ns / n as f64,
        n as f64 / (total_ns * 1e-9),
        sink
    );
}

pub(crate) fn dispatch(experiment: &str, lines: &mut impl Iterator<Item = String>) -> bool {
    match experiment {
        "icrs_ecl_j2000" => run_direction_rotation(
            lines,
            "icrs_ecl_j2000",
            "ANISE_J2000_to_ECLIPJ2000_rotation",
            true,
        ),
        "icrs_ecl_j2000_perf" => {
            run_direction_rotation_perf(lines, "icrs_ecl_j2000_perf", true)
        }
        "inv_icrs_ecl_j2000" => run_direction_rotation(
            lines,
            "inv_icrs_ecl_j2000",
            "ANISE_ECLIPJ2000_to_J2000_rotation",
            false,
        ),
        "inv_icrs_ecl_j2000_perf" => {
            run_direction_rotation_perf(lines, "inv_icrs_ecl_j2000_perf", false)
        }
        "obliquity" => run_direction_rotation(
            lines,
            "obliquity",
            "ANISE_ECLIPJ2000_to_J2000_obliquity_rotation",
            false,
        ),
        "obliquity_perf" => run_direction_rotation_perf(lines, "obliquity_perf", false),
        "inv_obliquity" => run_direction_rotation(
            lines,
            "inv_obliquity",
            "ANISE_J2000_to_ECLIPJ2000_obliquity_rotation",
            true,
        ),
        "inv_obliquity_perf" => {
            run_direction_rotation_perf(lines, "inv_obliquity_perf", true)
        }
        "frame_bias" => skip_experiment(
            lines,
            "frame_bias",
            "ANISE adapter does not provide isolated frame-bias benchmark output in this lab integration",
        ),
        "frame_bias_perf" => skip_experiment(
            lines,
            "frame_bias_perf",
            "ANISE adapter does not provide isolated frame-bias benchmark output in this lab integration",
        ),
        "precession" => skip_experiment(
            lines,
            "precession",
            "ANISE adapter does not provide isolated precession benchmark output in this lab integration",
        ),
        "precession_perf" => skip_experiment(
            lines,
            "precession_perf",
            "ANISE adapter does not provide isolated precession benchmark output in this lab integration",
        ),
        "nutation" => skip_experiment(
            lines,
            "nutation",
            "ANISE adapter does not provide isolated nutation benchmark output in this lab integration",
        ),
        "nutation_perf" => skip_experiment(
            lines,
            "nutation_perf",
            "ANISE adapter does not provide isolated nutation benchmark output in this lab integration",
        ),
        "inv_frame_bias" => skip_experiment(
            lines,
            "inv_frame_bias",
            "ANISE adapter does not provide isolated inverse frame-bias benchmark output in this lab integration",
        ),
        "inv_frame_bias_perf" => skip_experiment(
            lines,
            "inv_frame_bias_perf",
            "ANISE adapter does not provide isolated inverse frame-bias benchmark output in this lab integration",
        ),
        "inv_precession" => skip_experiment(
            lines,
            "inv_precession",
            "ANISE adapter does not provide isolated inverse precession benchmark output in this lab integration",
        ),
        "inv_precession_perf" => skip_experiment(
            lines,
            "inv_precession_perf",
            "ANISE adapter does not provide isolated inverse precession benchmark output in this lab integration",
        ),
        "inv_nutation" => skip_experiment(
            lines,
            "inv_nutation",
            "ANISE adapter does not provide isolated inverse nutation benchmark output in this lab integration",
        ),
        "inv_nutation_perf" => skip_experiment(
            lines,
            "inv_nutation_perf",
            "ANISE adapter does not provide isolated inverse nutation benchmark output in this lab integration",
        ),
        "inv_bpn" => skip_experiment(
            lines,
            "inv_bpn",
            "ANISE adapter does not provide isolated inverse BPN benchmark output in this lab integration",
        ),
        "inv_bpn_perf" => skip_experiment(
            lines,
            "inv_bpn_perf",
            "ANISE adapter does not provide isolated inverse BPN benchmark output in this lab integration",
        ),
        "bias_precession" => skip_experiment(
            lines,
            "bias_precession",
            "ANISE adapter does not provide isolated bias+precession benchmark output in this lab integration",
        ),
        "bias_precession_perf" => skip_experiment(
            lines,
            "bias_precession_perf",
            "ANISE adapter does not provide isolated bias+precession benchmark output in this lab integration",
        ),
        "inv_bias_precession" => skip_experiment(
            lines,
            "inv_bias_precession",
            "ANISE adapter does not provide isolated inverse bias+precession benchmark output in this lab integration",
        ),
        "inv_bias_precession_perf" => skip_experiment(
            lines,
            "inv_bias_precession_perf",
            "ANISE adapter does not provide isolated inverse bias+precession benchmark output in this lab integration",
        ),
        "precession_nutation" => skip_experiment(
            lines,
            "precession_nutation",
            "ANISE adapter does not provide isolated precession+nutation benchmark output in this lab integration",
        ),
        "precession_nutation_perf" => skip_experiment(
            lines,
            "precession_nutation_perf",
            "ANISE adapter does not provide isolated precession+nutation benchmark output in this lab integration",
        ),
        "inv_precession_nutation" => skip_experiment(
            lines,
            "inv_precession_nutation",
            "ANISE adapter does not provide isolated inverse precession+nutation benchmark output in this lab integration",
        ),
        "inv_precession_nutation_perf" => skip_experiment(
            lines,
            "inv_precession_nutation_perf",
            "ANISE adapter does not provide isolated inverse precession+nutation benchmark output in this lab integration",
        ),
        "equ_ecl" => skip_experiment(
            lines,
            "equ_ecl",
            "ANISE adapter currently supports only J2000 ecliptic rotation, not ecliptic-of-date transform",
        ),
        "equ_ecl_perf" => skip_experiment(
            lines,
            "equ_ecl_perf",
            "ANISE adapter currently supports only J2000 ecliptic rotation, not ecliptic-of-date transform",
        ),
        "icrs_ecl_tod" => skip_experiment(
            lines,
            "icrs_ecl_tod",
            "ANISE adapter currently supports J2000 ecliptic rotation only (no ecliptic-of-date path)",
        ),
        "icrs_ecl_tod_perf" => skip_experiment(
            lines,
            "icrs_ecl_tod_perf",
            "ANISE adapter currently supports J2000 ecliptic rotation only (no ecliptic-of-date path)",
        ),
        "inv_icrs_ecl_tod" => skip_experiment(
            lines,
            "inv_icrs_ecl_tod",
            "ANISE adapter currently supports J2000 ecliptic rotation only (no ecliptic-of-date path)",
        ),
        "inv_icrs_ecl_tod_perf" => skip_experiment(
            lines,
            "inv_icrs_ecl_tod_perf",
            "ANISE adapter currently supports J2000 ecliptic rotation only (no ecliptic-of-date path)",
        ),
        "inv_equ_ecl" => skip_experiment(
            lines,
            "inv_equ_ecl",
            "ANISE adapter currently supports J2000 ecliptic rotation only (no ecliptic-of-date path)",
        ),
        "inv_equ_ecl_perf" => skip_experiment(
            lines,
            "inv_equ_ecl_perf",
            "ANISE adapter currently supports J2000 ecliptic rotation only (no ecliptic-of-date path)",
        ),
        _ => return false,
    }
    true
}
