use std::io::{self, Write};
use std::time::Instant;

use siderust::astro::eop::NullEop;
use siderust::coordinates::cartesian;
use siderust::coordinates::frames::{
    EquatorialMeanJ2000, EquatorialMeanOfDate, EquatorialTrueOfDate, ICRS,
};
use siderust::coordinates::transform::context::DefaultEphemeris;
use siderust::coordinates::transform::AstroContext;
use siderust::time::JulianDate;

use crate::{
    ang_sep, frame_rotation_selected, normalize3, pure_bpn_matrix, selected_nutation_profile,
    CartesianDirectionCompat,
};

macro_rules! dir_experiment {
    ($fn_acc:ident, $fn_perf:ident, $exp:expr, $model:expr, $Src:ty, $Dst:ty) => {
        pub fn $fn_acc(lines: &mut impl Iterator<Item = String>) {
            let n: usize = lines.next().unwrap().trim().parse().unwrap();
            let stdout = io::stdout();
            let mut out = stdout.lock();
            write!(
                out,
                concat!(
                    "{{\"experiment\":\"",
                    $exp,
                    "\",\"library\":\"siderust\",",
                    "\"model\":\"",
                    $model,
                    "+NullEop\",\"count\":{},\"cases\":[\n"
                ),
                n
            )
            .unwrap();
            for i in 0..n {
                let line = lines.next().unwrap();
                let p: Vec<f64> = line
                    .trim()
                    .split_whitespace()
                    .map(|s| s.parse().unwrap())
                    .collect();
                let jd = JulianDate::new(p[0]);
                let src = cartesian::Direction::<$Src>::new(p[1], p[2], p[3]);
                let vin = [src.x(), src.y(), src.z()];
                // Pure-model BPN-family transforms: no EOP needed; using
                // NullEop avoids IERS coverage restrictions on epoch range.
                let ctx: AstroContext<DefaultEphemeris, NullEop> = AstroContext::with_types();
                let rot = frame_rotation_selected::<$Src, $Dst, _, _>(jd, &ctx);
                let vout = normalize3(rot.apply_array(vin));
                let inv = frame_rotation_selected::<$Dst, $Src, _, _>(jd, &ctx);
                let vback = normalize3(inv.apply_array(vout));
                let cl = ang_sep(&vin, &vback);
                if i > 0 {
                    write!(out, ",\n").unwrap();
                }
                write!(
                    out,
                    "{{\"jd_tt\":{:.15},\"input\":[{:.17e},{:.17e},{:.17e}],\
                     \"output\":[{:.17e},{:.17e},{:.17e}],\"closure_rad\":{:.17e}}}",
                    p[0], vin[0], vin[1], vin[2], vout[0], vout[1], vout[2], cl,
                )
                .unwrap();
            }
            writeln!(out, "\n]}}").unwrap();
        }

        pub fn $fn_perf(lines: &mut impl Iterator<Item = String>) {
            let n: usize = lines.next().unwrap().trim().parse().unwrap();
            let mut jds = Vec::with_capacity(n);
            let mut dirs: Vec<cartesian::Direction<$Src>> = Vec::with_capacity(n);
            for _ in 0..n {
                let line = lines.next().unwrap();
                let p: Vec<f64> = line
                    .trim()
                    .split_whitespace()
                    .map(|s| s.parse().unwrap())
                    .collect();
                jds.push(p[0]);
                dirs.push(cartesian::Direction::<$Src>::new(p[1], p[2], p[3]));
            }
            for i in 0..n.min(100) {
                let jd = JulianDate::new(jds[i]);
                let ctx: AstroContext<DefaultEphemeris, NullEop> = AstroContext::with_types();
                let rot = frame_rotation_selected::<$Src, $Dst, _, _>(jd, &ctx);
                let vout = normalize3(rot.apply_array([dirs[i].x(), dirs[i].y(), dirs[i].z()]));
                std::hint::black_box(vout);
            }
            let start = Instant::now();
            let mut sink = 0.0_f64;
            for i in 0..n {
                let jd = JulianDate::new(jds[i]);
                let ctx: AstroContext<DefaultEphemeris, NullEop> = AstroContext::with_types();
                let rot = frame_rotation_selected::<$Src, $Dst, _, _>(jd, &ctx);
                let vout = normalize3(rot.apply_array([dirs[i].x(), dirs[i].y(), dirs[i].z()]));
                sink = vout[0];
            }
            let elapsed = start.elapsed();
            let total_ns = elapsed.as_nanos() as f64;
            println!(
                concat!(
                    "{{\"experiment\":\"",
                    $exp,
                    "_perf\",\"library\":\"siderust\",",
                    "\"count\":{},\"total_ns\":{:.0},\"per_op_ns\":{:.1},",
                    "\"throughput_ops_s\":{:.0},\"_sink\":{:.17e}}}"
                ),
                n,
                total_ns,
                total_ns / n as f64,
                n as f64 / (total_ns * 1e-9),
                sink,
            );
        }
    };
}

dir_experiment!(
    run_frame_bias,
    run_frame_bias_perf,
    "frame_bias",
    "IERS2003_frame_bias",
    ICRS,
    EquatorialMeanJ2000
);
dir_experiment!(
    run_precession,
    run_precession_perf,
    "precession",
    "IAU_2006_precession",
    EquatorialMeanJ2000,
    EquatorialMeanOfDate
);
dir_experiment!(
    run_nutation,
    run_nutation_perf,
    "nutation",
    "IAU_2006_2000A_nutation",
    EquatorialMeanOfDate,
    EquatorialTrueOfDate
);

pub(crate) fn run_frame_rotation_bpn(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let stdout = io::stdout();
    let mut out = stdout.lock();

    let profile = selected_nutation_profile();
    write!(
        out,
        "{{\"experiment\":\"frame_rotation_bpn\",\"library\":\"siderust\",\
         \"model\":\"IAU2006_precession+{}_nutation+IERS2003_bias+NullEop\",\
         \"count\":{},\"cases\":[\n",
        profile, n
    )
    .unwrap();

    for i in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .trim()
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        let jd_tt = parts[0];
        let jd = JulianDate::new(jd_tt);

        let dir_icrs = cartesian::Direction::<ICRS>::new(parts[1], parts[2], parts[3]);
        let vin = dir_icrs.as_vec3();

        // Pure-IAU BPN: no Earth-orientation corrections, no UT1 conversion.
        // See pure_bpn_matrix() for why this avoids AstroContext::eop_at_tt.
        let rot = pure_bpn_matrix(jd);
        let vout = normalize3(rot.apply_array(vin));
        let inv = rot.transpose();
        let vback = normalize3(inv.apply_array(vout));
        let closure_rad = ang_sep(&vin, &vback);
        let mat = *rot.as_matrix();

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{:.15},\"input\":[{:.17e},{:.17e},{:.17e}],\
             \"output\":[{:.17e},{:.17e},{:.17e}],\
             \"closure_rad\":{:.17e},\
             \"matrix\":[[{:.17e},{:.17e},{:.17e}],[{:.17e},{:.17e},{:.17e}],[{:.17e},{:.17e},{:.17e}]]}}",
            jd_tt, vin[0], vin[1], vin[2],
            vout[0], vout[1], vout[2],
            closure_rad,
            mat[0][0], mat[0][1], mat[0][2],
            mat[1][0], mat[1][1], mat[1][2],
            mat[2][0], mat[2][1], mat[2][2],
        )
        .unwrap();
    }

    writeln!(out, "\n]}}").unwrap();
}

pub(crate) fn run_gmst_era(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let stdout = io::stdout();
    let mut out = stdout.lock();

    write!(
        out,
        "{{\"experiment\":\"gmst_era\",\"library\":\"siderust\",\
         \"model\":\"IAU_2006_GMST\",\
         \"count\":{},\"cases\":[\n",
        n
    )
    .unwrap();

    for i in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .trim()
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        let jd_ut1 = parts[0];
        let jd_tt = parts[1];

        let jd_ut1_q = JulianDate::new(jd_ut1);
        let jd_tt_q = JulianDate::new(jd_tt);

        // IAU 2006 GMST (ERA-based, returns radians already normalized)
        let gst_rad = siderust::astro::sidereal::gmst_iau2006(jd_ut1_q, jd_tt_q).value();

        // ERA via siderust's earth_rotation_angle
        let era_rad = siderust::astro::era::earth_rotation_angle(jd_ut1_q).value();

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_ut1\":{:.15},\"jd_tt\":{:.15},\
             \"gmst_rad\":{:.17e},\"era_rad\":{:.17e}}}",
            jd_ut1, jd_tt, gst_rad, era_rad,
        )
        .unwrap();
    }

    writeln!(out, "\n]}}").unwrap();
}

pub(crate) fn run_frame_rotation_bpn_perf(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let mut jds: Vec<f64> = Vec::with_capacity(n);
    let mut dirs: Vec<cartesian::Direction<ICRS>> = Vec::with_capacity(n);

    for _ in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .trim()
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        jds.push(parts[0]);
        dirs.push(cartesian::Direction::<ICRS>::new(
            parts[1], parts[2], parts[3],
        ));
    }

    // Warm-up
    for i in 0..n.min(100) {
        let jd = JulianDate::new(jds[i]);
        let rot = pure_bpn_matrix(jd);
        let dir_tod = normalize3(rot.apply_array(dirs[i].as_vec3()));
        std::hint::black_box(&dir_tod);
    }

    // Timed run
    let start = Instant::now();
    let mut sink = 0.0_f64;
    for i in 0..n {
        let jd = JulianDate::new(jds[i]);
        let rot = pure_bpn_matrix(jd);
        let dir_tod = normalize3(rot.apply_array(dirs[i].as_vec3()));
        sink = dir_tod[0];
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;
    let per_op_ns = total_ns / n as f64;

    println!(
        "{{\"experiment\":\"frame_rotation_bpn_perf\",\"library\":\"siderust\",\
         \"count\":{},\"total_ns\":{:.0},\"per_op_ns\":{:.1},\
         \"throughput_ops_s\":{:.0},\"_sink\":{:.17e}}}",
        n,
        total_ns,
        per_op_ns,
        n as f64 / (total_ns * 1e-9),
        sink,
    );
}

pub(crate) fn run_gmst_era_perf(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let mut jd_ut1_vals: Vec<f64> = Vec::with_capacity(n);
    let mut jd_tt_vals: Vec<f64> = Vec::with_capacity(n);

    for _ in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .trim()
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        jd_ut1_vals.push(parts[0]);
        jd_tt_vals.push(parts[1]);
    }

    // Warm-up
    for i in 0..n.min(100) {
        let jd_ut1 = JulianDate::new(jd_ut1_vals[i]);
        let jd_tt = JulianDate::new(jd_tt_vals[i]);
        let gst = siderust::astro::sidereal::gmst_iau2006(jd_ut1, jd_tt);
        std::hint::black_box(&gst);
    }

    // Timed run
    let start = Instant::now();
    let mut sink: f64 = 0.0;
    for i in 0..n {
        let jd_ut1 = JulianDate::new(jd_ut1_vals[i]);
        let jd_tt = JulianDate::new(jd_tt_vals[i]);
        let gst = siderust::astro::sidereal::gmst_iau2006(jd_ut1, jd_tt);
        sink += gst.value();
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;
    let per_op_ns = total_ns / n as f64;

    println!(
        "{{\"experiment\":\"gmst_era_perf\",\"library\":\"siderust\",\
         \"count\":{},\"total_ns\":{:.0},\"per_op_ns\":{:.1},\
         \"throughput_ops_s\":{:.0},\"_sink\":{:.17e}}}",
        n,
        total_ns,
        per_op_ns,
        n as f64 / (total_ns * 1e-9),
        sink,
    );
}

dir_experiment!(
    run_inv_frame_bias,
    run_inv_frame_bias_perf,
    "inv_frame_bias",
    "IERS2003_inv_bias",
    EquatorialMeanJ2000,
    ICRS
);
dir_experiment!(
    run_inv_precession,
    run_inv_precession_perf,
    "inv_precession",
    "IAU2006_inv_prec",
    EquatorialMeanOfDate,
    EquatorialMeanJ2000
);
dir_experiment!(
    run_inv_nutation,
    run_inv_nutation_perf,
    "inv_nutation",
    "IAU2006_2000A_inv_nut",
    EquatorialTrueOfDate,
    EquatorialMeanOfDate
);
// Custom inv_bpn using pure_bpn_matrix().transpose() to avoid the UT1 lookup
// that frame_rotation_selected::<EquatorialTrueOfDate, ICRS> triggers even
// with NullEop. The BPN matrix is orthogonal so its inverse is its transpose.
pub fn run_inv_bpn(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    write!(
        out,
        "{{\"experiment\":\"inv_bpn\",\"library\":\"siderust\",\
         \"model\":\"IAU2006_inv_bpn+NullEop\",\"count\":{},\"cases\":[\n",
        n
    )
    .unwrap();
    for i in 0..n {
        let line = lines.next().unwrap();
        let p: Vec<f64> = line
            .trim()
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        let jd = JulianDate::new(p[0]);
        let vin = [p[1], p[2], p[3]];
        // Inverse BPN = transpose(BPN); no UT1/ERA needed.
        let inv_rot = pure_bpn_matrix(jd).transpose();
        let vout = normalize3(inv_rot.apply_array(vin));
        // Closure check: re-apply forward BPN and measure round-trip error.
        let fwd_rot = pure_bpn_matrix(jd);
        let vback = normalize3(fwd_rot.apply_array(vout));
        let cl = ang_sep(&vin, &vback);
        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"jd_tt\":{:.15},\"input\":[{:.17e},{:.17e},{:.17e}],\
             \"output\":[{:.17e},{:.17e},{:.17e}],\"closure_rad\":{:.17e}}}",
            p[0], vin[0], vin[1], vin[2], vout[0], vout[1], vout[2], cl,
        )
        .unwrap();
    }
    writeln!(out, "\n]}}").unwrap();
}

pub fn run_inv_bpn_perf(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let mut jds = Vec::with_capacity(n);
    let mut dirs: Vec<[f64; 3]> = Vec::with_capacity(n);
    for _ in 0..n {
        let line = lines.next().unwrap();
        let p: Vec<f64> = line
            .trim()
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        jds.push(p[0]);
        dirs.push([p[1], p[2], p[3]]);
    }
    for i in 0..n.min(100) {
        let jd = JulianDate::new(jds[i]);
        let inv_rot = pure_bpn_matrix(jd).transpose();
        let vout = normalize3(inv_rot.apply_array(dirs[i]));
        std::hint::black_box(vout);
    }
    let start = Instant::now();
    let mut sink = 0.0_f64;
    for i in 0..n {
        let jd = JulianDate::new(jds[i]);
        let inv_rot = pure_bpn_matrix(jd).transpose();
        let vout = normalize3(inv_rot.apply_array(dirs[i]));
        sink = vout[0];
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;
    println!(
        "{{\"experiment\":\"inv_bpn_perf\",\"library\":\"siderust\",\
         \"count\":{},\"total_ns\":{:.0},\"per_op_ns\":{:.1},\
         \"throughput_ops_s\":{:.0},\"_sink\":{:.17e}}}",
        n,
        total_ns,
        total_ns / n as f64,
        n as f64 / (total_ns * 1e-9),
        sink,
    );
}
dir_experiment!(
    run_bias_precession,
    run_bias_precession_perf,
    "bias_precession",
    "IAU2006_bias_prec",
    ICRS,
    EquatorialMeanOfDate
);
dir_experiment!(
    run_inv_bias_precession,
    run_inv_bias_precession_perf,
    "inv_bias_precession",
    "IAU2006_inv_bias_prec",
    EquatorialMeanOfDate,
    ICRS
);
dir_experiment!(
    run_precession_nutation,
    run_precession_nutation_perf,
    "precession_nutation",
    "IAU2006_prec_nut",
    EquatorialMeanJ2000,
    EquatorialTrueOfDate
);
dir_experiment!(
    run_inv_precession_nutation,
    run_inv_precession_nutation_perf,
    "inv_precession_nutation",
    "IAU2006_inv_prec_nut",
    EquatorialTrueOfDate,
    EquatorialMeanJ2000
);
