#!/usr/bin/env python3
"""Barycenter TT→TDB sensitivity audit for the Siderust embedded DE440 lane.

This diagnostic supports Phase 1/2 of the "close Siderust barycenter accuracy
gap" plan. It does not change the lab scorecard or the published artifacts.

For each of the seven major-planet system-barycenter experiments (`*_barycenter_position`):

1. Load the JPL Horizons reference cache (`.cache/horizons/*.json`) that the
   latest lab run pinned via its `horizons_cache_key` (sourced from
   `latest_results/<exp>/siderust_de440_barycenter.json :: inputs`).
2. Re-evaluate the Siderust adapter at the exact same JD(TT) epochs to obtain
   the geocentric ICRS positions Siderust would publish (the "baseline" lane).
3. Attempt to re-evaluate the Siderust adapter at JD' = JD(TT) + (dtdb_erfa −
   dtdb_siderust). NOTE: this shift is ~6e-11 days, *below* the f64 ULP at
   JD ≈ 2.5e6 (~5e-10 days). The shifted JD therefore rounds back to the
   baseline JD and the two residuals come out identical — that is *not*
   evidence the TDB error is benign; it is evidence that a TDB precision fix
   cannot be simulated via the single-f64 `jd_tt` stdin interface. The
   `improvement_ratio_p99` field is reported but should be interpreted as
   "below adapter-interface precision" when equal to 1.0.
4. Compare both Siderust outputs against the Horizons reference using a
   Vincenty (`atan2(|cross|, dot)`) spherical separation so the metric does
   not saturate at the `arccos` floor near 1 mas.

Output: a single JSON document on stdout with per-planet residual statistics.

To actually validate the TDB precision hypothesis you need a Rust-side
diagnostic that constructs the SPK input time as a two-part `(et_int_s,
et_frac_s)` and calls `SegmentDescriptor::try_position` with the
higher-precision form; see `plan.md` Phase 2.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

try:
    import erfa
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "pyerfa is required for this diagnostic; activate the lab .venv first.\n"
    )
    sys.exit(2)


LAB_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = LAB_ROOT / ".cache" / "horizons"
DEFAULT_ADAPTER = (
    LAB_ROOT
    / "pipeline"
    / "adapters"
    / "siderust_adapter"
    / "target"
    / "release"
    / "siderust-adapter"
)


# Documented in `tempoch-core-0.6.0/src/model/scale/conversion.rs` —
# `tdb_minus_tt_seconds`. Truncated 7-term Fairhead-Bretagnon series.
# This is exactly the formula Siderust uses internally when calling
# `JulianDate::to_scale::<TDB>()` from the JPL evaluator.
def siderust_tdb_minus_tt(jd_tt: np.ndarray) -> np.ndarray:
    t = (jd_tt - 2_451_545.0) / 36_525.0
    return (
        0.001_657 * np.sin(628.3076 * t + 6.2401)
        + 0.000_022 * np.sin(575.3385 * t + 4.2970)
        + 0.000_014 * np.sin(1256.6152 * t + 6.1969)
        + 0.000_005 * np.sin(606.9777 * t + 4.0212)
        + 0.000_005 * np.sin(52.9691 * t + 0.4444)
        + 0.000_002 * np.sin(21.3299 * t + 5.5431)
        + 0.000_010 * t * np.sin(628.3076 * t + 4.2490)
    )


def erfa_tdb_minus_tt(jd_tt: np.ndarray) -> np.ndarray:
    """High-precision (Fairhead-Bretagnon full series) TDB−TT at the geocenter."""
    vec = np.vectorize(lambda jd: erfa.dtdb(jd, 0.0, 0.0, 0.0, 0.0, 0.0))
    return vec(jd_tt)


def ra_dec_dist_to_xyz(ra_rad: np.ndarray, dec_rad: np.ndarray, dist: np.ndarray):
    cd = np.cos(dec_rad)
    return (
        dist * cd * np.cos(ra_rad),
        dist * cd * np.sin(ra_rad),
        dist * np.sin(dec_rad),
    )


def angular_separation_arcsec(
    x1: np.ndarray,
    y1: np.ndarray,
    z1: np.ndarray,
    x2: np.ndarray,
    y2: np.ndarray,
    z2: np.ndarray,
) -> np.ndarray:
    """Spherical angle between two cartesian position vectors, in arcseconds.

    Uses the Vincenty `atan2(|cross|, dot)` form so the metric does not
    saturate at the arccos floor (~1 mas regime).
    """
    n1 = np.sqrt(x1 * x1 + y1 * y1 + z1 * z1)
    n2 = np.sqrt(x2 * x2 + y2 * y2 + z2 * z2)
    u1x, u1y, u1z = x1 / n1, y1 / n1, z1 / n1
    u2x, u2y, u2z = x2 / n2, y2 / n2, z2 / n2
    cx = u1y * u2z - u1z * u2y
    cy = u1z * u2x - u1x * u2z
    cz = u1x * u2y - u1y * u2x
    cross_norm = np.sqrt(cx * cx + cy * cy + cz * cz)
    dot = u1x * u2x + u1y * u2y + u1z * u2z
    return np.degrees(np.arctan2(cross_norm, dot)) * 3600.0


def run_siderust(adapter: Path, experiment: str, jds_tt: np.ndarray) -> np.ndarray:
    """Call the vendored siderust adapter with `SIDERUST_PLANET_MODEL=de440_barycenter`.

    Returns an (N, 4) array of (jd_tt, ra_rad, dec_rad, dist_au).
    """
    stdin_text = f"{len(jds_tt)}\n" + "\n".join(f"{jd:.15f}" for jd in jds_tt) + "\n"
    env = os.environ.copy()
    env["SIDERUST_PLANET_MODEL"] = "de440_barycenter"
    out = subprocess.run(
        [str(adapter), experiment],
        input=stdin_text,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(out.stdout)
    if payload.get("library") != "siderust":
        raise RuntimeError(f"unexpected adapter payload: {payload!r}")
    rows = payload["cases"]
    arr = np.array(
        [(c["jd_tt"], c["ra_rad"], c["dec_rad"], c["dist_au"]) for c in rows]
    )
    return arr


def load_cache(cache_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, str]:
    payload = json.loads(cache_path.read_text())
    rows = payload["rows"]
    jds = np.array([r["jd_tt"] for r in rows])
    xs = np.array([r["x_au"] for r in rows])
    ys = np.array([r["y_au"] for r in rows])
    zs = np.array([r["z_au"] for r in rows])
    return jds, xs, ys, zs, payload.get("source_tag", "unknown")


def summarise_residual(name: str, sep_arcsec: np.ndarray) -> Dict[str, float]:
    abs_sep = np.abs(sep_arcsec)
    return {
        "p50": float(np.percentile(abs_sep, 50)),
        "p90": float(np.percentile(abs_sep, 90)),
        "p99": float(np.percentile(abs_sep, 99)),
        "max": float(abs_sep.max()),
        "mean": float(abs_sep.mean()),
    }


def audit_planet(
    name: str,
    cache_path: Path,
    adapter: Path,
) -> Dict[str, object]:
    jds, ref_x, ref_y, ref_z, source_tag = load_cache(cache_path)

    base = run_siderust(adapter, f"{name}_barycenter_position", jds)
    base_x, base_y, base_z = ra_dec_dist_to_xyz(base[:, 1], base[:, 2], base[:, 3])
    base_sep = angular_separation_arcsec(base_x, base_y, base_z, ref_x, ref_y, ref_z)

    dtdb_sid = siderust_tdb_minus_tt(jds)
    dtdb_erfa = erfa_tdb_minus_tt(jds)
    delta_sec = dtdb_erfa - dtdb_sid

    # Time-scale shim: pass a JD that already absorbs the missing high-order
    # FB terms so that Siderust's internal 7-term re-application lands on the
    # ERFA-quality TDB. (Δ at this magnitude doesn't shift the 7-term value
    # measurably, so the residual converges to the ERFA-quality TDB lookup.)
    jds_shifted = jds + delta_sec / 86_400.0
    shifted = run_siderust(adapter, f"{name}_barycenter_position", jds_shifted)
    sh_x, sh_y, sh_z = ra_dec_dist_to_xyz(shifted[:, 1], shifted[:, 2], shifted[:, 3])
    shifted_sep = angular_separation_arcsec(sh_x, sh_y, sh_z, ref_x, ref_y, ref_z)

    return {
        "planet": name,
        "horizons_source_tag": source_tag,
        "n_epochs": int(len(jds)),
        "jd_tt_range": [float(jds.min()), float(jds.max())],
        "tdb_minus_tt_delta_seconds": {
            "p50": float(np.percentile(np.abs(delta_sec), 50)),
            "p99": float(np.percentile(np.abs(delta_sec), 99)),
            "max": float(np.abs(delta_sec).max()),
        },
        "residual_arcsec_baseline": summarise_residual("baseline", base_sep),
        "residual_arcsec_with_erfa_tdb": summarise_residual("shifted", shifted_sep),
        "improvement_ratio_p99": (
            float(np.percentile(np.abs(base_sep), 99))
            / max(float(np.percentile(np.abs(shifted_sep), 99)), 1e-30)
        ),
    }


def find_barycenter_caches(
    cache_dir: Path,
    n_required: int,
) -> Dict[str, Path]:
    """Return the canonical Horizons cache per barycenter experiment.

    Looks up `horizons_cache_key` from
    `latest_results/<exp>/siderust_de440_barycenter.json` so the diagnostic
    always selects the exact cache the scorecard used. Falls back to the
    most-recent matching cache only if no scorecard manifest is found.
    """
    chosen: Dict[str, Path] = {}
    lab_root = Path(__file__).resolve().parents[2]
    latest = lab_root / "latest_results"
    if latest.is_dir():
        for exp_dir in latest.iterdir():
            if not exp_dir.is_dir() or not exp_dir.name.endswith("_barycenter_position"):
                continue
            manifest = exp_dir / "siderust_de440_barycenter.json"
            if not manifest.is_file():
                continue
            try:
                payload = json.loads(manifest.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            key = (payload.get("inputs") or {}).get("horizons_cache_key")
            if not key:
                continue
            cache_path = cache_dir / f"{key}.json"
            if cache_path.is_file():
                planet = exp_dir.name.replace("_barycenter_position", "")
                chosen[planet] = cache_path
    if chosen:
        return chosen

    # Fallback: newest-by-mtime per experiment (legacy behaviour).
    fallback: Dict[str, Tuple[float, Path]] = {}
    for cache_path in cache_dir.glob("*.json"):
        try:
            payload = json.loads(cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        experiment = payload.get("experiment")
        if not experiment or not experiment.endswith("_barycenter_position"):
            continue
        rows = payload.get("rows") or []
        if len(rows) != n_required:
            continue
        mtime = cache_path.stat().st_mtime
        prev = fallback.get(experiment)
        if prev is None or mtime > prev[0]:
            fallback[experiment] = (mtime, cache_path)
    return {k.replace("_barycenter_position", ""): v[1] for k, v in fallback.items()}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--adapter", default=str(DEFAULT_ADAPTER))
    parser.add_argument("--n", type=int, default=100, help="Horizons cache row count to select")
    parser.add_argument("--planet", action="append", help="Restrict to specific planets (repeatable)")
    parser.add_argument(
        "--output",
        default="-",
        help="JSON output path (default: stdout)",
    )
    args = parser.parse_args(argv)

    cache_dir = Path(args.cache_dir)
    adapter = Path(args.adapter)
    if not adapter.is_file():
        sys.stderr.write(
            f"error: siderust adapter not found at {adapter}; "
            "build it via cargo or pass --adapter\n"
        )
        return 2

    caches = find_barycenter_caches(cache_dir, args.n)
    if args.planet:
        caches = {k: v for k, v in caches.items() if k in set(args.planet)}
    if not caches:
        sys.stderr.write("error: no matching Horizons caches found\n")
        return 2

    ordered = sorted(
        caches.items(),
        key=lambda kv: ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"].index(kv[0])
        if kv[0] in {"mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"}
        else 99,
    )

    findings = []
    for name, cache_path in ordered:
        sys.stderr.write(f"[audit] {name}: cache={cache_path.name}\n")
        findings.append(audit_planet(name, cache_path, adapter))

    doc = {
        "diagnostic": "siderust_barycenter_tdb_audit",
        "schema_version": 1,
        "adapter": str(adapter),
        "cache_dir": str(cache_dir),
        "siderust_tdb_model": "tempoch-core 0.6 (7-term Fairhead-Bretagnon)",
        "reference_tdb_model": "ERFA eraDtdb (full series, geocenter, ut=elong=u=v=0)",
        "findings": findings,
    }
    payload = json.dumps(doc, indent=2)
    if args.output == "-":
        print(payload)
    else:
        Path(args.output).write_text(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
