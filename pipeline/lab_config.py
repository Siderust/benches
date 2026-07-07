"""Pipeline configuration and suite definitions for Siderust Lab."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .baselines import BaselinePolicy, ConvergenceConfig, parse_baseline_policy, parse_convergence_config
except ImportError:  # pragma: no cover - direct script path
    from baselines import BaselinePolicy, ConvergenceConfig, parse_baseline_policy, parse_convergence_config

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]


# --- Ephemeris lanes -------------------------------------------------------
# Mirrors `pipeline.horizons_client.LANE_GEOMETRIC / LANE_APPARENT`; kept
# duplicated here so this module has no runtime dependency on the network
# client at import time.
EPHEMERIS_LANE_GEOMETRIC = "geometric_vector"
EPHEMERIS_LANE_APPARENT = "apparent_observer"

PLANET_CENTER_POSITION_EXPERIMENTS = [
    "mercury_position",
    "venus_position",
    "mars_position",
    "jupiter_position",
    "saturn_position",
    "uranus_position",
    "neptune_position",
]

PLANET_BARYCENTER_POSITION_EXPERIMENTS = [
    "mercury_barycenter_position",
    "venus_barycenter_position",
    "mars_barycenter_position",
    "jupiter_barycenter_position",
    "saturn_barycenter_position",
    "uranus_barycenter_position",
    "neptune_barycenter_position",
]

# Public planet-position benchmarks use planet system barycenters (NAIF IDs
# 1-8) so that DE440-capable adapters (siderust:de440, astropy:de440-local, anise)
# can all be compared without requiring satellite center SPK kernels.
PLANET_POSITION_EXPERIMENTS = list(PLANET_BARYCENTER_POSITION_EXPERIMENTS)

EPHEMERIS_EXPERIMENTS = [
    "solar_position",
    "lunar_position",
    *PLANET_BARYCENTER_POSITION_EXPERIMENTS,
]

# Apparent diagnostic lane mirrors the planet-center IDs only (geocentric
# observer apparent RA/Dec requires a physical-center target).
APPARENT_EPHEMERIS_EXPERIMENTS = [
    "solar_position_apparent",
    "lunar_position_apparent",
    *(f"{p}_apparent" for p in PLANET_CENTER_POSITION_EXPERIMENTS),
]

PUBLIC_EXPERIMENTS = [
    "gmst_era",
    "frame_rotation_bpn",
    "equ_ecl",
    "equ_horizontal",
    "solar_position",
    "lunar_position",
    *PLANET_POSITION_EXPERIMENTS,
    "kepler_solver",
]

CI_EXPERIMENTS = [
    "gmst_era",
    "frame_rotation_bpn",
    "equ_ecl",
    "equ_horizontal",
    "kepler_solver",
]

DIAGNOSTIC_EXPERIMENTS = [
    "horiz_to_equ",
    "frame_bias",
    "precession",
    "nutation",
    "icrs_ecl_j2000",
    "icrs_ecl_tod",
    "inv_frame_bias",
    "inv_precession",
    "inv_nutation",
    "inv_bpn",
    "inv_icrs_ecl_j2000",
    "obliquity",
    "inv_obliquity",
    "bias_precession",
    "inv_bias_precession",
    "precession_nutation",
    "inv_precession_nutation",
    "inv_icrs_ecl_tod",
    "inv_equ_ecl",
    *APPARENT_EPHEMERIS_EXPERIMENTS,
]

SUITES: dict[str, list[str]] = {
    "core": PUBLIC_EXPERIMENTS,
    "ci": CI_EXPERIMENTS,
    "ephemeris": EPHEMERIS_EXPERIMENTS,
    "diagnostic": DIAGNOSTIC_EXPERIMENTS,
    "all": [*PUBLIC_EXPERIMENTS, *DIAGNOSTIC_EXPERIMENTS],
}

VALID_ADAPTERS = {"siderust", "astropy", "libnova", "anise"}
VALID_SIDERUST_PROFILES = {"iau2006a", "iau2000a", "iau2000b", "precession_only"}


def _meta(family: str, tier: str, reference_model: str,
          reference_lane: str | None = None) -> dict[str, str]:
    out: dict[str, str] = {"family": family, "tier": tier, "reference_model": reference_model}
    if reference_lane:
        out["reference_lane"] = reference_lane
    return out


EXPERIMENT_METADATA: dict[str, dict[str, str]] = {
    "gmst_era": _meta("time_earth_rotation", "public", "SOFA IAU 2006 GMST / IAU 2000 ERA"),
    "frame_rotation_bpn": _meta("frame_transformations", "public", "SOFA pnm06a (IAU 2006/2000A)"),
    "equ_ecl": _meta("frame_transformations", "public", "SOFA IAU 2006 ecliptic of date"),
    "equ_horizontal": _meta("pointing", "public", "SOFA/IERS GAST + spherical trigonometry, no refraction"),
    "solar_position": _meta("solar_system_ephemerides", "public",
                            "JPL Horizons geometric vector (ICRF, VEC_CORR=NONE)",
                            reference_lane=EPHEMERIS_LANE_GEOMETRIC),
    "lunar_position": _meta("solar_system_ephemerides", "public",
                            "JPL Horizons geometric vector (ICRF, VEC_CORR=NONE)",
                            reference_lane=EPHEMERIS_LANE_GEOMETRIC),
    "kepler_solver": _meta("orbital_primitives", "public", "Kepler equation numerical invariant"),
    "horiz_to_equ": _meta("pointing", "diagnostic", "SOFA/IERS inverse horizontal transform"),
    "frame_bias": _meta("frame_transformations", "diagnostic", "SOFA IAU 2006 frame bias"),
    "precession": _meta("frame_transformations", "diagnostic", "SOFA IAU 2006 precession"),
    "nutation": _meta("frame_transformations", "diagnostic", "SOFA IAU 2006/2000A nutation"),
    "icrs_ecl_j2000": _meta("frame_transformations", "diagnostic", "SOFA IAU 2006 J2000 ecliptic"),
    "icrs_ecl_tod": _meta("frame_transformations", "deprecated", "Duplicate of ecliptic-of-date coverage"),
}

for _bary_exp in PLANET_BARYCENTER_POSITION_EXPERIMENTS:
    EXPERIMENT_METADATA[_bary_exp] = _meta(
        "solar_system_ephemerides", "public",
        "JPL Horizons geometric vector — planet system barycenter (ICRF, VEC_CORR=NONE)",
        reference_lane=EPHEMERIS_LANE_GEOMETRIC,
    )

for _apparent_exp in APPARENT_EPHEMERIS_EXPERIMENTS:
    EXPERIMENT_METADATA[_apparent_exp] = _meta(
        "solar_system_ephemerides", "diagnostic",
        "JPL Horizons astrometric observer RA/Dec (OBSERVER, geocenter)",
        reference_lane=EPHEMERIS_LANE_APPARENT,
    )

for _diag_exp in DIAGNOSTIC_EXPERIMENTS:
    EXPERIMENT_METADATA.setdefault(
        _diag_exp,
        _meta("frame_transformations", "diagnostic", "SOFA component/inverse diagnostic"),
    )


@dataclass(frozen=True)
class PipelineConfig:
    run_label: str | None
    run_phase: str | None
    run_tags: list[str]
    suite: str
    experiments: list[str]
    n: int
    seed: int
    adapters: list[str]
    siderust_profiles: list[str]
    performance_enabled: bool
    perf_rounds: int
    perf_scalar_n: int
    perf_batch_n: int
    perf_batch_rounds: int
    perf_warmup: int
    perf_timeout_s: int
    no_build: bool
    horizons_use_cache: bool
    horizons_allow_network: bool
    cache_root: str
    cache_auto_download: bool
    kernels_de440_enabled: bool
    kernels_de440_filename: str
    output_dir: str
    publish_latest: bool
    allow_dirty_publish: bool
    allow_partial_publish: bool
    baseline_policy: BaselinePolicy
    convergence: ConvergenceConfig
    refresh_baselines: bool


def _as_list(value: Any, *, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(f"Expected string or list, got {type(value).__name__}")


def _resolve_experiments(raw: dict[str, Any], suite: str) -> list[str]:
    explicit = raw.get("experiments")
    if explicit:
        experiments = _as_list(explicit, default=[])
    else:
        if suite not in SUITES:
            raise ValueError(f"Unknown suite '{suite}'. Known suites: {', '.join(sorted(SUITES))}")
        experiments = list(SUITES[suite])

    known = set(SUITES["all"])
    unknown = [exp for exp in experiments if exp not in known]
    if unknown:
        raise ValueError(f"Unknown experiment(s): {', '.join(unknown)}")
    return experiments


def load_pipeline_config(
    path: str | Path,
    *,
    lab_root: Path | None = None,
    refresh_baselines: bool = False,
) -> PipelineConfig:
    """Parse and validate a TOML pipeline config."""
    config_path = Path(path)
    if lab_root is None:
        lab_root = config_path.resolve().parent.parent
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    suite = str(raw.get("suite", "core"))
    experiments = _resolve_experiments(raw, suite)
    adapters = _as_list(raw.get("adapters"), default=["siderust", "astropy", "libnova", "anise"])
    profiles = _as_list(
        raw.get("siderust_profiles") or raw.get("profiles"),
        default=["iau2006a"],
    )

    unknown_adapters = [adapter for adapter in adapters if adapter not in VALID_ADAPTERS]
    if unknown_adapters:
        raise ValueError(f"Unknown adapter(s): {', '.join(unknown_adapters)}")

    unknown_profiles = [profile for profile in profiles if profile not in VALID_SIDERUST_PROFILES]
    if unknown_profiles:
        raise ValueError(f"Unknown Siderust profile(s): {', '.join(unknown_profiles)}")

    performance = raw.get("performance", {})
    horizons = raw.get("horizons", {})
    cache = raw.get("cache", {})
    kernels_de440 = raw.get("kernels", {}).get("de440", {})
    output = raw.get("output", {})
    baselines = raw.get("baselines", {})
    convergence = raw.get("convergence", {})
    refresh = refresh_baselines or bool(raw.get("refresh_baselines", False))

    return PipelineConfig(
        run_label=str(raw["run_label"]) if raw.get("run_label") else None,
        run_phase=str(raw.get("run_phase") or raw.get("phase")) if raw.get("run_phase") or raw.get("phase") else None,
        run_tags=_as_list(raw.get("run_tags") or raw.get("tags"), default=[]),
        suite=suite,
        experiments=experiments,
        n=int(raw.get("n", 1000)),
        seed=int(raw.get("seed", 42)),
        adapters=adapters,
        siderust_profiles=profiles,
        performance_enabled=bool(performance.get("enabled", True)),
        perf_rounds=int(performance.get("rounds", 10)),
        perf_scalar_n=int(performance.get("scalar_n", 5000)),
        perf_batch_n=int(performance.get("batch_n", 100000)),
        perf_batch_rounds=int(performance.get("batch_rounds", 5)),
        perf_warmup=int(performance.get("warmup", 100)),
        perf_timeout_s=int(performance.get("timeout_s", 120)),
        no_build=bool(raw.get("no_build", False)),
        horizons_use_cache=bool(horizons.get("use_cache", True)),
        horizons_allow_network=bool(horizons.get("allow_network", True)),
        cache_root=str(cache.get("root", ".benches_cache")),
        cache_auto_download=bool(cache.get("auto_download", True)),
        kernels_de440_enabled=bool(kernels_de440.get("enabled", True)),
        kernels_de440_filename=str(kernels_de440.get("filename", "de440.bsp")),
        output_dir=str(output.get("dir", "results")),
        publish_latest=bool(output.get("publish_latest", False)),
        allow_dirty_publish=bool(output.get("allow_dirty_publish", False)),
        allow_partial_publish=bool(output.get("allow_partial_publish", False)),
        baseline_policy=parse_baseline_policy(
            baselines,
            lab_root=lab_root,
            refresh_all=refresh,
        ),
        convergence=parse_convergence_config(convergence),
        refresh_baselines=refresh,
    )
