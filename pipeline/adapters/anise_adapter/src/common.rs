use anise::math::Vector3;
use anise::prelude::{Almanac, Epoch, TimeScale};

use std::path::Path;

pub(crate) const KM_PER_AU: f64 = 149_597_870.7;

pub(crate) fn parse_numbers(line: &str) -> Vec<f64> {
    line.split_whitespace()
        .map(|s| s.parse::<f64>().unwrap())
        .collect()
}

pub(crate) fn normalize(v: Vector3) -> Vector3 {
    let n = v.norm();
    if n > 0.0 {
        v / n
    } else {
        v
    }
}

pub(crate) fn ang_sep(a: Vector3, b: Vector3) -> f64 {
    let dot = a.dot(&b).clamp(-1.0, 1.0);
    dot.acos()
}

pub(crate) fn epoch_from_jd_tt(jd_tt: f64) -> Epoch {
    Epoch::from_jde_in_time_scale(jd_tt, TimeScale::TT)
}

pub(crate) fn read_n(lines: &mut impl Iterator<Item = String>) -> usize {
    lines.next().unwrap().trim().parse::<usize>().unwrap()
}

pub(crate) fn perf_warmup() -> usize {
    std::env::var("LAB_PERF_WARMUP")
        .ok()
        .and_then(|s| s.parse::<usize>().ok())
        .unwrap_or(100_usize)
}

pub(crate) fn skip_experiment(lines: &mut impl Iterator<Item = String>, exp: &str, reason: &str) {
    let n = read_n(lines);
    for _ in 0..n {
        let _ = lines.next();
    }
    println!(
        "{{\"experiment\":\"{}\",\"library\":\"anise\",\"skipped\":true,\"reason\":\"{}\"}}",
        exp, reason
    );
}

pub(crate) fn load_ephemeris_almanac() -> Result<Almanac, String> {
    // A2: Discovery order (rankability audit §5):
    //   1. $ANISE_BSP_PATH (file or directory)
    //   2. $SIDERUST_DATASETS_DIR/<de441|de440>_dataset/*.bsp
    //   3. Legacy fallback list
    let mut candidates: Vec<String> = Vec::new();

    if let Ok(env_path) = std::env::var("ANISE_BSP_PATH") {
        let p = Path::new(&env_path);
        if p.is_file() {
            candidates.push(env_path.clone());
        } else if p.is_dir() {
            if let Ok(entries) = std::fs::read_dir(p) {
                for entry in entries.flatten() {
                    let pb = entry.path();
                    if pb.extension().and_then(|e| e.to_str()) == Some("bsp") {
                        if let Some(s) = pb.to_str() {
                            candidates.push(s.to_string());
                        }
                    }
                }
            }
        }
    }

    if let Ok(datasets) = std::env::var("SIDERUST_DATASETS_DIR") {
        for sub in ["de441_dataset", "de440_dataset"] {
            let dir = Path::new(&datasets).join(sub);
            if dir.is_dir() {
                if let Ok(entries) = std::fs::read_dir(&dir) {
                    for entry in entries.flatten() {
                        let pb = entry.path();
                        if pb.extension().and_then(|e| e.to_str()) == Some("bsp") {
                            if let Some(s) = pb.to_str() {
                                candidates.push(s.to_string());
                            }
                        }
                    }
                }
            }
        }
    }

    for legacy in [
        ".siderust_datasets/de440_dataset/de440.bsp",
        "siderust/scripts/jpl/de440/dataset/de440.bsp",
        "anise/data/de440s.bsp",
        "anise/data/de440.bsp",
    ] {
        candidates.push(legacy.to_string());
    }

    for path in &candidates {
        if Path::new(path).is_file() {
            if let Ok(almanac) = Almanac::new(path) {
                return Ok(almanac);
            }
        }
    }

    Err("ANISE SPK not found. Set ANISE_BSP_PATH or SIDERUST_DATASETS_DIR, or place a BSP at one of: siderust/scripts/jpl/de440/dataset/de440.bsp, anise/data/de440s.bsp, anise/data/de440.bsp".to_string())
}

pub(crate) fn sanitized_reason(reason: &str) -> String {
    reason.replace('"', "'")
}

pub(crate) fn run_setup_metrics() {
    let start = std::time::Instant::now();
    match load_ephemeris_almanac() {
        Ok(almanac) => {
            std::hint::black_box(almanac);
            let setup_ms = start.elapsed().as_secs_f64() * 1000.0;
            println!("{{\"setup_ms\":{:.6},\"measured\":true}}", setup_ms);
        }
        Err(reason) => {
            println!(
                "{{\"setup_ms\":0.0,\"measured\":false,\"reason\":\"{}\"}}",
                sanitized_reason(&reason)
            );
        }
    }
}
