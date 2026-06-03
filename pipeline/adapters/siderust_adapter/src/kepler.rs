use std::io::{self, Write};
use std::time::Instant;

use keplerian::anomaly::{eccentric_from_mean, AnomalyOptions, MeanAnomaly};
use keplerian::Eccentricity;

fn solve_keplers_equation(m_rad: f64, e: f64) -> f64 {
    let options = AnomalyOptions::try_new(100, 1e-15).expect("hardcoded anomaly options are valid");
    eccentric_from_mean(
        MeanAnomaly::from_value(m_rad),
        Eccentricity::new_unchecked(e),
        options,
    )
    .expect("elliptic Kepler solve failed")
    .value()
}

pub(crate) fn run_kepler_solver(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();
    let stdout = io::stdout();
    let mut out = stdout.lock();

    write!(
        out,
        "{{\"experiment\":\"kepler_solver\",\"library\":\"siderust\",\
         \"model\":\"Newton_Raphson_bisection\",\
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
        let m_rad = parts[0];
        let e = parts[1];

        let e_rad = solve_keplers_equation(m_rad, e);

        // True anomaly
        let nu = 2.0
            * ((1.0 + e).sqrt() * (e_rad / 2.0).sin())
                .atan2((1.0 - e).sqrt() * (e_rad / 2.0).cos());

        // Self-consistency residual
        let residual = (e_rad - e * e_rad.sin() - m_rad).abs();

        if i > 0 {
            write!(out, ",\n").unwrap();
        }
        write!(
            out,
            "{{\"M_rad\":{:.17e},\"e\":{:.17e},\
             \"E_rad\":{:.17e},\"nu_rad\":{:.17e},\
             \"residual_rad\":{:.17e},\"iters\":-1,\"converged\":{}}}",
            m_rad,
            e,
            e_rad,
            nu,
            residual,
            if residual < 1e-12 { "true" } else { "false" },
        )
        .unwrap();
    }
    writeln!(out, "\n]}}").unwrap();
}

pub(crate) fn run_kepler_solver_perf(lines: &mut impl Iterator<Item = String>) {
    let n: usize = lines.next().unwrap().trim().parse().unwrap();

    let mut m_vals: Vec<f64> = Vec::with_capacity(n);
    let mut e_vals: Vec<f64> = Vec::with_capacity(n);

    for _ in 0..n {
        let line = lines.next().unwrap();
        let parts: Vec<f64> = line
            .trim()
            .split_whitespace()
            .map(|s| s.parse().unwrap())
            .collect();
        m_vals.push(parts[0]);
        e_vals.push(parts[1]);
    }

    // Warm-up
    for i in 0..n.min(100) {
        let e_anom = solve_keplers_equation(m_vals[i], e_vals[i]);
        std::hint::black_box(e_anom);
    }

    // Timed run
    let start = Instant::now();
    let mut sink: f64 = 0.0;
    for i in 0..n {
        let e_anom = solve_keplers_equation(m_vals[i], e_vals[i]);
        sink += e_anom;
    }
    let elapsed = start.elapsed();
    let total_ns = elapsed.as_nanos() as f64;
    let per_op_ns = total_ns / n as f64;

    println!(
        "{{\"experiment\":\"kepler_solver_perf\",\"library\":\"siderust\",\
         \"count\":{},\"total_ns\":{:.0},\"per_op_ns\":{:.1},\
         \"throughput_ops_s\":{:.0},\"_sink\":{:.17e}}}",
        n,
        total_ns,
        per_op_ns,
        n as f64 / (total_ns * 1e-9),
        sink,
    );
}
