//! ANISE adapter for the benchmark lab.
//!
//! Reads experiment input from stdin and writes one JSON object to stdout.
//! Unsupported experiments return `{ "skipped": true }` responses.

mod common;
mod ephemerides;
mod frames;
mod pointing;
mod time_earth_rotation;

pub(crate) use common::perf_warmup;

use std::io::{self, BufRead};

fn main() {
    let stdin = io::stdin();
    let mut lines = stdin.lock().lines().map(|l| l.unwrap());

    let experiment = lines.next().expect("expected experiment name");
    let experiment = experiment.trim();

    if experiment.ends_with("_setup") {
        common::run_setup_metrics();
        return;
    }

    // SPK preflight: verify almanac is loadable before entering any ephemeris
    // experiment. Exits non-zero with an actionable message instead of emitting
    // per-experiment skipped rows that would pollute the result set.
    if ephemerides::is_ephemeris_experiment(experiment) {
        if let Err(reason) = common::load_ephemeris_almanac() {
            eprintln!(
                "anise-adapter: SPK preflight failed — {}\n\
                 Set ANISE_BSP_PATH or SIDERUST_DATASETS_DIR before running ephemeris experiments.",
                reason
            );
            std::process::exit(1);
        }
    }

    if ephemerides::dispatch(experiment, &mut lines)
        || frames::dispatch(experiment, &mut lines)
        || time_earth_rotation::dispatch(experiment, &mut lines)
        || pointing::dispatch(experiment, &mut lines)
    {
        return;
    }

    eprintln!("Unknown experiment: {}", experiment);
    std::process::exit(1);
}
