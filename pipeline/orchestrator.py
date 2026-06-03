#!/usr/bin/env python3
"""
Siderust Lab Orchestrator
=========================

Generates inputs, runs adapters (ERFA, Siderust, Astropy, libnova, ANISE), collects results,
computes accuracy & performance metrics, and writes structured output.

Usage:
    python3 pipeline/orchestrator.py [--experiment frame_rotation_bpn] [--n 1000] [--seed 42]

Experiments:
    frame_rotation_bpn  — Bias-Precession-Nutation direction transform (ICRS → TrueOfDate/CIRS)
    gmst_era            — Greenwich Mean Sidereal Time & Earth Rotation Angle
    equ_ecl             — Equatorial ↔ Ecliptic coordinate transform
    equ_horizontal      — Equatorial → Horizontal (AltAz)
    solar_position      — Sun geocentric RA/Dec
    lunar_position      — Moon geocentric RA/Dec
    kepler_solver       — Kepler equation M→E→ν self-consistency
"""

import argparse
import json
import math
import os
import platform
import subprocess
import sys
import hashlib
import time
import statistics
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Import Horizons client from same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
from horizons_client import fetch_horizons_reference, LANE_GEOMETRIC, LANE_APPARENT
from lab_config import (
    EXPERIMENT_METADATA,
    VALID_SIDERUST_PROFILES,
    EPHEMERIS_LANE_GEOMETRIC,
    EPHEMERIS_LANE_APPARENT,
    APPARENT_EPHEMERIS_EXPERIMENTS,
    PLANET_BARYCENTER_POSITION_EXPERIMENTS,
    PUBLIC_EXPERIMENTS,
    SUITES,
)
from catalog import default_registry as _default_catalog


# Candidate variants whose ":<suffix>" is a *Siderust nutation profile*
# (ranking gate behaves differently than for ephemeris model variants).
_SIDERUST_PROFILE_SUFFIXES = set(VALID_SIDERUST_PROFILES)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LAB_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = LAB_ROOT / "results"
ERFA_BIN = LAB_ROOT / "pipeline" / "adapters" / "erfa_adapter" / "build" / "erfa_adapter"
SIDERUST_BIN = LAB_ROOT / "pipeline" / "adapters" / "siderust_adapter" / "target" / "release" / "siderust-adapter"
ASTROPY_SCRIPT = LAB_ROOT / "pipeline" / "adapters" / "astropy_adapter" / "adapter.py"
LIBNOVA_BIN = LAB_ROOT / "pipeline" / "adapters" / "libnova_adapter" / "build" / "libnova_adapter"
ANISE_BIN = LAB_ROOT / "pipeline" / "adapters" / "anise_adapter" / "target" / "release" / "anise-adapter"

RAD_TO_MAS = 180.0 / math.pi * 3600.0 * 1000.0  # radians → milli-arcseconds
RAD_TO_ARCSEC = 180.0 / math.pi * 3600.0

# Performance benchmarking defaults
DEFAULT_PERF_ROUNDS = 10        # Number of separate timing rounds (more rounds = lower CV)
DEFAULT_PERF_WARMUP = 100       # Warmup iterations before each round (adapters use min(N, 100))
SCALAR_WARM_N = 5000            # Steady-state per-call latency workload size
BATCH_THROUGHPUT_N = 100000     # Bulk evaluation workload size
BATCH_THROUGHPUT_ROUNDS = 5     # Fewer rounds for large-N throughput workload
MIN_MEASURABLE_NS = 10.0        # Warn if per-op time is below this threshold
MIN_PERF_N = BATCH_THROUGHPUT_N # Back-compat alias for old callers/tests

ACTIVE_ADAPTERS: set[str] | None = None
SIDERUST_PROFILES = ["iau2006a"]
HORIZONS_USE_CACHE = True
HORIZONS_ALLOW_NETWORK = True


def configure_run(
    *,
    adapters: list[str] | None = None,
    siderust_profiles: list[str] | None = None,
    horizons_use_cache: bool = True,
    horizons_allow_network: bool = True,
    output_dir: str | Path | None = None,
) -> None:
    """Configure process-wide run settings used by experiment runners."""
    global ACTIVE_ADAPTERS, SIDERUST_PROFILES, HORIZONS_USE_CACHE, HORIZONS_ALLOW_NETWORK, RESULTS_DIR

    if adapters:
        valid_adapters = {"siderust", "astropy", "libnova", "anise"}
        unknown_adapters = [adapter for adapter in adapters if adapter not in valid_adapters]
        if unknown_adapters:
            raise ValueError(f"Unknown adapter(s): {', '.join(unknown_adapters)}")
    ACTIVE_ADAPTERS = set(adapters) if adapters else None
    if siderust_profiles:
        unknown = [p for p in siderust_profiles if p not in VALID_SIDERUST_PROFILES]
        if unknown:
            raise ValueError(f"Unknown Siderust profile(s): {', '.join(unknown)}")
        SIDERUST_PROFILES = list(siderust_profiles)
    else:
        SIDERUST_PROFILES = ["iau2006a"]

    HORIZONS_USE_CACHE = horizons_use_cache
    HORIZONS_ALLOW_NETWORK = horizons_allow_network

    if output_dir is not None:
        out = Path(output_dir)
        RESULTS_DIR = out if out.is_absolute() else LAB_ROOT / out


def _adapter_enabled(name: str) -> bool:
    return ACTIVE_ADAPTERS is None or name in ACTIVE_ADAPTERS


def adapter_base(label: str) -> str:
    return label.split(":", 1)[0]


def adapter_profile(label: str) -> str | None:
    """Return the variant suffix (after ':') of a candidate label.

    For ``siderust`` (no suffix) we return ``"iau2006a"`` for backwards
    compatibility with the IAU profile ranking gate.  For any other label
    the suffix is returned verbatim — *every* variant therefore keeps a
    distinct ``candidate_profile`` and never collapses with its sibling
    rows on disk or in the scorecard (audit-and-rework-plan §candidate
    identity).
    """
    if ":" not in label:
        return "iau2006a" if label == "siderust" else None
    _, suffix = label.split(":", 1)
    return suffix or None


def adapter_display(label: str) -> str:
    profile = adapter_profile(label)
    if not profile:
        return label
    if label == "siderust":
        return label
    if label.startswith("siderust:"):
        return f"siderust/{profile}"
    return label  # e.g. "astropy:jpl"


def candidate_id_for(label: str) -> str:
    """Return the canonical catalog candidate_id for an adapter label.

    Catalog IDs match the on-the-wire labels exactly except that the
    default Siderust profile (``iau2006a``) keeps the bare ``"siderust"``
    label.
    """
    if not label:
        return label
    base, _, suffix = label.partition(":")
    # Only Siderust nutation profiles collapse onto the bare "siderust" id.
    if base == "siderust" and suffix in _SIDERUST_PROFILE_SUFFIXES:
        return "siderust"
    return label


def candidate_adapters():
    """Return candidate adapter command definitions."""
    adapters = []
    if _adapter_enabled("siderust"):
        for profile in SIDERUST_PROFILES:
            label = "siderust" if len(SIDERUST_PROFILES) == 1 and profile == "iau2006a" else f"siderust:{profile}"
            adapters.append((
                label,
                ["env", f"SIDERUST_NUTATION_PROFILE={profile}", str(SIDERUST_BIN)],
            ))
        # ELP2000 and DE440 ephemeris variants
        adapters.append((
            "siderust:elp2000",
            ["env", "SIDERUST_NUTATION_PROFILE=iau2006a", "SIDERUST_LUNAR_MODEL=elp2000", str(SIDERUST_BIN)],
        ))
        adapters.append((
            "siderust:de440",
            ["env", "SIDERUST_NUTATION_PROFILE=iau2006a",
             "SIDERUST_SOLAR_MODEL=de440", "SIDERUST_LUNAR_MODEL=de440", str(SIDERUST_BIN)],
        ))
        adapters.append((
            "siderust:de440_barycenter",
            ["env", "SIDERUST_NUTATION_PROFILE=iau2006a",
             "SIDERUST_PLANET_MODEL=de440_barycenter", str(SIDERUST_BIN)],
        ))
        adapters.append((
            "siderust:spk_center",
            ["env", "SIDERUST_NUTATION_PROFILE=iau2006a",
             "SIDERUST_PLANET_MODEL=spk_center", str(SIDERUST_BIN)],
        ))
        adapters.append((
            "siderust:spk_barycenter",
            ["env", "SIDERUST_NUTATION_PROFILE=iau2006a",
             "SIDERUST_PLANET_MODEL=spk_barycenter", str(SIDERUST_BIN)],
        ))
    if _adapter_enabled("astropy"):
        adapters.append(("astropy", [sys.executable, str(ASTROPY_SCRIPT)]))
        if os.environ.get("SIDERUST_KERNEL_DE440_ENABLED", "1") != "0":
            adapters.append((
                "astropy:de440-local",
                ["env", "ASTROPY_EPHEMERIS=de440-local", sys.executable, str(ASTROPY_SCRIPT)],
            ))
    if _adapter_enabled("libnova"):
        adapters.append(("libnova", [str(LIBNOVA_BIN)]))
    if _adapter_enabled("anise"):
        adapters.append(("anise", [str(ANISE_BIN)]))
    return adapters


def candidate_adapters_for(experiment: str):
    """Catalog-filtered candidate list for a specific experiment.

    Drops candidates whose catalog ``support`` is ``unsupported`` for this
    experiment (e.g. astropy/erfa for ``kepler_solver``).  Candidates with
    ``support == "runtime-blocked"`` are dropped here; the manifest records
    them via :func:`runtime_blocked_for` as ``excluded_candidates``.

    Catalog lookup uses the canonical id from :func:`candidate_id_for`,
    which keeps Siderust nutation-profile variants under the bare
    ``"siderust"`` id while distinguishing model variants like
    ``siderust:elp2000`` and ``astropy:jpl``.
    """
    catalog = _default_catalog()
    out = []
    for label, cmd in candidate_adapters():
        cid = candidate_id_for(label)
        entry = catalog.get(cid, experiment)
        if entry is None:
            # No catalog declaration for this (candidate_id, experiment) →
            # drop.  Audit invariant: every published row is catalogued.
            # To add a new experiment for a candidate, declare it (or an
            # explicit ``support="unsupported"`` row) in catalog.toml.
            continue
        if entry.support in {"unsupported", "runtime-blocked"}:
            # Hard-drop: no real upstream API (unsupported), or upstream
            # bug means we cannot publish a correct number (runtime-blocked).
            # The catalog records why; runtime-blocked entries surface in
            # the manifest as excluded_candidates via runtime_blocked_for().
            continue
        out.append((label, cmd))
    return out


def runtime_blocked_for(experiment: str) -> list[tuple[str, str, str]]:
    """List of (label, candidate_id, reason) for runtime-blocked entries.

    These never reach the adapter.  The manifest records them as
    ``excluded_candidates`` in the per-experiment completeness block so
    the documented exclusion reason is preserved without adding synthetic
    skipped rows to the result files.
    """
    catalog = _default_catalog()
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for label, _cmd in candidate_adapters():
        cid = candidate_id_for(label)
        entry = catalog.get(cid, experiment)
        if entry is None or entry.support != "runtime-blocked":
            continue
        # Avoid double-listing the same candidate id.
        if cid in seen:
            continue
        seen.add(cid)
        out.append((label, cid, entry.exclusion_reason or "runtime-blocked"))
    return out


def reference_model_for(experiment: str, source_provenance: dict | None = None) -> str:
    meta = EXPERIMENT_METADATA.get(experiment, {})
    model = meta.get("reference_model", "SOFA/ERFA reference")
    if source_provenance and source_provenance.get("source") == "JPL Horizons":
        tag = source_provenance.get("source_tag")
        lane = source_provenance.get("lane")
        lane_suffix = {
            LANE_GEOMETRIC: " geometric vector",
            LANE_APPARENT: " apparent observer",
        }.get(lane, "")
        if tag:
            return f"JPL Horizons {tag}{lane_suffix}".strip()
        return f"JPL Horizons{lane_suffix}".strip()
    return model


# ---------------------------------------------------------------------------
# Ephemeris lane helpers
# ---------------------------------------------------------------------------

def is_apparent_experiment(experiment: str) -> bool:
    return experiment.endswith("_apparent")


def strip_apparent_suffix(experiment: str) -> str:
    if experiment.endswith("_apparent"):
        return experiment[: -len("_apparent")]
    return experiment


def ephemeris_lane_for(experiment: str) -> str | None:
    """Return the JPL lane for an ephemeris experiment, or None for non-ephemeris."""
    meta = EXPERIMENT_METADATA.get(experiment, {})
    return meta.get("reference_lane")


# Candidate parity per (lane, candidate_library) for ephemeris experiments.
#
# Geometric lane (JPL Horizons VECTORS, VEC_CORR=NONE, ICRF):
#   "analytic"  → analytic model (VSOP87 / EPV00 / ELP2000 / Meeus) that
#                 produces geometric-frame output with no aberration/light-time.
#                 Comparable as best-available; not the same JPL source.
#   "jpl-spk"   → same JPL source (ANISE with SPK kernel), comparable as exact-model.
#
# Apparent lane (JPL Horizons OBSERVER, astrometric RA/Dec):
#   "apparent"      → applies aberration / nutation internally (libnova equ_coords path).
#                     Comparable as best-available on the apparent lane.
#   "geometric-only" → no aberration / nutation.  Geocentric geometric direction
#                      compared against OBSERVER astrometric is not-comparable:
#                      the ~20 arcsec aberration delta dominates the model residual.
#   "jpl-spk"       → same JPL source.
#
# libnova ships rectangular helio/geo functions in addition to the apparent
# `*_equ_coords` helpers: on the geometric lane it switches to helio/geo
# (analytic parity), on the apparent lane it stays on equ_coords (apparent).
EPHEMERIS_CANDIDATE_PARITY: dict[tuple[str, str], str] = {
    # Geometric lane — analytic models vs JPL geometric vector reference
    (LANE_GEOMETRIC, "erfa"): "analytic",
    (LANE_GEOMETRIC, "siderust"): "analytic",
    (LANE_GEOMETRIC, "astropy"): "analytic",
    (LANE_GEOMETRIC, "anise"): "jpl-spk",    # DE440/441 SPK → exact-model
    (LANE_GEOMETRIC, "libnova"): "analytic",
    (LANE_GEOMETRIC, "siderust_de440"): "jpl-spk",  # JPL DE440 embedded SPK
    (LANE_GEOMETRIC, "siderust_de440_barycenter"): "jpl-spk",
    (LANE_GEOMETRIC, "siderust_spk_center"): "jpl-spk",
    (LANE_GEOMETRIC, "siderust_spk_barycenter"): "jpl-spk",
    (LANE_GEOMETRIC, "astropy_jpl"): "jpl-spk",     # Astropy JPL ephemeris resolver
    (LANE_GEOMETRIC, "astropy_de440_local"): "jpl-spk",
    (LANE_GEOMETRIC, "astropy_de440-local"): "jpl-spk",
    # Apparent lane — only libnova applies aberration/nutation; others are
    # geometric-only and not comparable to the OBSERVER-style reference.
    (LANE_APPARENT, "erfa"): "geometric-only",
    (LANE_APPARENT, "siderust"): "geometric-only",
    (LANE_APPARENT, "astropy"): "geometric-only",
    (LANE_APPARENT, "anise"): "jpl-spk",
    (LANE_APPARENT, "libnova"): "apparent",
    (LANE_APPARENT, "siderust_de440"): "jpl-spk",
    (LANE_APPARENT, "siderust_de440_barycenter"): "jpl-spk",
    (LANE_APPARENT, "siderust_spk_center"): "jpl-spk",
    (LANE_APPARENT, "siderust_spk_barycenter"): "jpl-spk",
    (LANE_APPARENT, "astropy_jpl"): "jpl-spk",
    (LANE_APPARENT, "astropy_de440_local"): "jpl-spk",
    (LANE_APPARENT, "astropy_de440-local"): "jpl-spk",
}


def _ephemeris_candidate_parity(
    candidate_library: str,
    lane: str | None = None,
    candidate_label: str | None = None,
) -> str:
    if lane is None:
        # Legacy fallback: assume apparent lane for back-compat with callers
        # that pre-date the lane split.
        lane = LANE_APPARENT
    # Variant-aware lookup: catalog labels like "siderust:de440" are keyed
    # in EPHEMERIS_CANDIDATE_PARITY as "siderust_de440" (underscore form).
    # Audit fix: prefer the variant key when a full label is supplied so a
    # JPL-backed variant cannot be collapsed to the base library's analytic
    # parity.
    if candidate_label and ":" in candidate_label:
        variant_key = candidate_label.replace(":", "_")
        if (lane, variant_key) in EPHEMERIS_CANDIDATE_PARITY:
            return EPHEMERIS_CANDIDATE_PARITY[(lane, variant_key)]
    return EPHEMERIS_CANDIDATE_PARITY.get((lane, candidate_library), "unknown")


# Non-ephemeris experiments where a candidate exposing the *same observable*
# but a different internal model can be ranked under the new
# rankability/model-capability policy (see
# reports/lab_rankability_and_model_capability_audit_2026-05-20.md §1, §4).
# Ephemeris experiments are handled separately via lane metadata.
BEST_AVAILABLE_ELIGIBLE = {
    "equ_horizontal",
    "horiz_to_equ",
    "gmst_era",
    "equ_ecliptic",
    "ecliptic_equ",
    "j2000_to_date",
}


def _comparability_class(
    experiment: str,
    parity: str | None,
    lane: str | None,
) -> str:
    """Classify how a candidate compares to the reference for ranking purposes.

    Returns one of:
      - ``exact-model``: candidate matches the reference's physical/model assumptions.
      - ``same-family-jpl``: a JPL DE kernel of a different version than the
        reference (DE440 vs the DE441 reference) — rankable in the broad view
        but excluded from the strict exact-model view.
      - ``best-available``: candidate uses a different model but the observable
        is conceptually the same and a disclosed comparison is scientifically
        defensible (audit policy).
      - ``diagnostic-profile``: an opt-in alternate profile that should be shown
        but not ranked alongside the public profile.
      - ``not-comparable``: different observable, missing parity info, or row
        is the reference itself.
    """
    if parity in (None, "unknown"):
        return "not-comparable"
    if parity == "reference":
        # The reference row itself — keep rankable for back-compat with code
        # that treats reference == exact-model, but the static export filters
        # these out of the candidate scoreboard anyway.
        return "exact-model"
    if parity == "model-parity":
        return "exact-model"
    if parity == "diagnostic":
        return "diagnostic-profile"
    # Ephemeris lane logic
    if lane in (EPHEMERIS_LANE_GEOMETRIC, EPHEMERIS_LANE_APPARENT):
        # A same-source JPL candidate (ANISE / siderust SPK) is DE440 against
        # the Horizons DE441 reference: same JPL family, different kernel
        # version → same-family-jpl (rankable, but not the strict exact-model
        # crown). Only an identical-kernel candidate would earn exact-model.
        if parity == "jpl-spk":
            return "same-family-jpl"
        # Analytic models (VSOP87 / EPV00 / ELP2000 / Meeus) on the geometric
        # lane compare geometric-to-geometric: best-available.
        if lane == EPHEMERIS_LANE_GEOMETRIC and parity in ("analytic", "geometric"):
            return "best-available"
        # On the apparent lane, only candidates that apply aberration / nutation
        # are truly comparable to the OBSERVER-style Horizons reference.
        if lane == EPHEMERIS_LANE_APPARENT and parity in ("apparent", "observer"):
            return "best-available"
        # Geometric-only candidates on the apparent lane: aberration (~20 arcsec)
        # dominates the model residual → not a fair model-accuracy comparison.
        return "not-comparable"
    # Non-ephemeris transforms
    if parity == "model-mismatch":
        if experiment in BEST_AVAILABLE_ELIGIBLE:
            return "best-available"
        return "not-comparable"
    return "not-comparable"


_MODEL_SOURCE_TOKENS = (
    ("de441", "JPL DE441"),
    ("de440", "JPL DE440"),
    ("vsop87", "VSOP87"),
    ("elp2000", "ELP2000-82B"),
    ("elp", "ELP2000-82B"),
    ("plan94", "PLAN94"),
    ("epv00", "EPV00"),
    ("moon98", "Moon98"),
    ("meeus", "Meeus Ch.47"),
    ("pnm06", "SOFA"),
    ("iau", "SOFA"),
    ("sofa", "SOFA"),
)


def _derive_model_source(library: str | None, model: str | None) -> str:
    if model:
        ml = model.lower()
        for tok, src in _MODEL_SOURCE_TOKENS:
            if tok in ml:
                return src
    lib = (library or "").lower()
    if lib == "erfa":
        return "ERFA"
    if lib == "jpl_horizons":
        return "JPL Horizons"
    return (library or "unknown").upper() if library else "unknown"


def _rankability(
    result: dict,
    profile: str | None,
    experiment: str | None = None,
    catalog_entry=None,
) -> tuple[bool, str | None]:
    """Decide whether this result should count toward accuracy rankings.

    The catalog (``pipeline/catalog.toml``) is authoritative whenever the
    ``(candidate_id, experiment)`` tuple is registered: an entry with
    ``support != "supported"`` is never rankable, and reference-only rows
    (``api_surface == "reference"``, e.g. ERFA) are excluded from the
    public scoreboard.  For tuples that aren't yet in the catalog the
    legacy lane / parity classification is preserved.
    """
    candidate = result.get("candidate_library")
    alignment = result.get("alignment") or {}
    lane = alignment.get("lane")
    parity = alignment.get("candidate_parity")
    if experiment is None:
        experiment = result.get("experiment") or alignment.get("experiment") or ""

    # Catalog-driven gate (audit-and-rework-plan §truth invariants).
    if catalog_entry is not None:
        if catalog_entry.api_surface == "reference":
            result["comparability_class"] = "not-comparable"
            return False, "reference adapter — never appears as a public candidate row"
        if catalog_entry.support == "unsupported":
            result["comparability_class"] = "not-comparable"
            return False, (
                catalog_entry.exclusion_reason
                or f"{catalog_entry.id}/{experiment}: unsupported in upstream library"
            )
        if catalog_entry.support == "runtime-blocked":
            result["comparability_class"] = "not-comparable"
            return False, (
                catalog_entry.exclusion_reason
                or f"{catalog_entry.id}/{experiment}: runtime-blocked"
            )
        if catalog_entry.api_surface != "public":
            result["comparability_class"] = (
                "diagnostic-profile" if catalog_entry.api_surface == "diagnostic"
                else "not-comparable"
            )
            return False, (
                f"{catalog_entry.id}/{experiment}: api_surface={catalog_entry.api_surface} "
                f"(not a public ranked candidate)"
            )
        if (
            lane in {EPHEMERIS_LANE_GEOMETRIC, EPHEMERIS_LANE_APPARENT}
            and catalog_entry.parity in {"exact-same-kernel", "same-family-jpl", "best-available"}
        ):
            # exact-same-kernel is the strict exact-model class; same-family-jpl
            # (DE440 vs the DE441 reference) and best-available are rankable in
            # the broad view but excluded from the strict exact-model crown.
            cc = (
                "exact-model"
                if catalog_entry.parity == "exact-same-kernel"
                else catalog_entry.parity
            )
            result["comparability_class"] = cc
        elif (
            lane in {EPHEMERIS_LANE_GEOMETRIC, EPHEMERIS_LANE_APPARENT}
            and catalog_entry.parity == "diagnostic-only"
        ):
            result["comparability_class"] = "diagnostic-profile"
            cc = "diagnostic-profile"
        elif (
            lane in {EPHEMERIS_LANE_GEOMETRIC, EPHEMERIS_LANE_APPARENT}
            and catalog_entry.parity == "model-mismatch"
        ):
            result["comparability_class"] = "not-comparable"
            cc = "not-comparable"
        else:
            cc = _comparability_class(experiment, parity, lane)
            result["comparability_class"] = cc
    else:
        cc = _comparability_class(experiment, parity, lane)
        result["comparability_class"] = cc

    # Siderust IAU profile gating is preserved as a *profile* check, independent
    # of comparability_class.  Only applies to nutation-profile variants
    # (iau2000a / iau2000b / precession_only) — *model* variants like
    # siderust:elp2000 or siderust:de440 inherit ``profile = None`` here
    # because they are not nutation-profile selections.
    if (
        result.get("candidate_library") == "siderust"
        and profile in VALID_SIDERUST_PROFILES
        and profile != "iau2006a"
    ):
        return False, (
            f"siderust profile '{profile}' does not match the SOFA IAU 2006/2000A reference"
        )

    if cc in ("exact-model", "same-family-jpl", "best-available"):
        return True, None

    if cc == "diagnostic-profile":
        return False, f"diagnostic profile (not ranked alongside public profile)"
    if parity == "model-mismatch":
        return False, (
            f"{candidate} uses a different physical model than the reference for this observable"
        )
    if parity in (None, "unknown"):
        return False, f"candidate parity is {parity or 'unknown'}"
    return False, (
        f"{candidate} parity '{parity}' on lane '{lane or 'n/a'}' is not comparable to the reference"
    )


def enrich_result(
    result: dict,
    experiment: str,
    candidate_label: str,
    *,
    source_provenance: dict | None = None,
) -> dict:
    """Add public-dashboard metadata while preserving existing result schema."""
    meta = EXPERIMENT_METADATA.get(experiment, {})
    profile = adapter_profile(candidate_label)
    cid = candidate_id_for(candidate_label)
    catalog = _default_catalog()
    catalog_entry = catalog.get(cid, experiment)

    rankable, reason = _rankability(
        result, profile, experiment=experiment, catalog_entry=catalog_entry,
    )
    result["family"] = meta.get("family", "uncategorized")
    result["tier"] = meta.get("tier", "diagnostic")
    result["candidate_profile"] = profile
    # candidate_id is the canonical row key; never collapses variants.
    result["candidate_id"] = cid
    if catalog_entry is not None:
        result["api_surface"] = catalog_entry.api_surface
        result["api_method"] = catalog_entry.api_method
        result["support_status"] = catalog_entry.support
        result["catalog_model"] = catalog_entry.model
        result["catalog_source"] = catalog_entry.source
        result["catalog_lane"] = catalog_entry.lane
        result["catalog_parity"] = catalog_entry.parity
        if catalog_entry.exclusion_reason:
            result["catalog_exclusion_reason"] = catalog_entry.exclusion_reason
    result["reference_model"] = reference_model_for(experiment, source_provenance)
    # Surface the adapter-reported model (when available) as `selected_model`
    # and derive a short `model_source` tag for badges in the scorecard / UI.
    # Do NOT fall back to the reference model: that would misrepresent the
    # candidate as using the JPL source when it is using VSOP87/Meeus/etc.
    adapter_model = result.get("model") or result.get("model_selected")
    result["selected_model"] = adapter_model or None
    result["model_source"] = _derive_model_source(
        result.get("candidate_library"), adapter_model
    )
    # Surface the lane (set on alignment for ephemeris experiments) on the
    # top-level row so the UI can badge geometric/apparent without digging.
    alignment = result.get("alignment") or {}
    if alignment.get("lane"):
        result.setdefault("lane", alignment["lane"])
    result["rankable_accuracy"] = rankable
    result["rank_exclusion_reason"] = reason
    result["source_provenance"] = source_provenance or {
        "source": "SOFA",
        "adapter": result.get("reference_library", "erfa"),
        "model": result["reference_model"],
    }
    return result


PLANET_POSITION_EXPERIMENTS = {
    # Public planet-system barycenter experiments (DE440-capable; listed first
    # so iteration picks up the canonical public lane entries before diagnostics).
    "mercury_barycenter_position": {"body": "Mercury system barycenter", "distance_key": "dist_au"},
    "venus_barycenter_position": {"body": "Venus system barycenter", "distance_key": "dist_au"},
    "mars_barycenter_position": {"body": "Mars system barycenter", "distance_key": "dist_au"},
    "jupiter_barycenter_position": {"body": "Jupiter system barycenter", "distance_key": "dist_au"},
    "saturn_barycenter_position": {"body": "Saturn system barycenter", "distance_key": "dist_au"},
    "uranus_barycenter_position": {"body": "Uranus system barycenter", "distance_key": "dist_au"},
    "neptune_barycenter_position": {"body": "Neptune system barycenter", "distance_key": "dist_au"},
    # Diagnostic geocentric planet-center experiments (retained for historical
    # coverage but no longer part of the public suite).
    "mercury_position": {"body": "Mercury", "distance_key": "dist_au"},
    "venus_position": {"body": "Venus", "distance_key": "dist_au"},
    "mars_position": {"body": "Mars", "distance_key": "dist_au"},
    "jupiter_position": {"body": "Jupiter", "distance_key": "dist_au"},
    "saturn_position": {"body": "Saturn", "distance_key": "dist_au"},
    "uranus_position": {"body": "Uranus", "distance_key": "dist_au"},
    "neptune_position": {"body": "Neptune", "distance_key": "dist_au"},
}

# Apparent-lane diagnostic mirrors share the same body/distance metadata as
# the public geometric IDs; they differ only in the JPL query lane and the
# candidate parity used by ranking.
_PLANET_POSITION_APPARENT = {
    f"{name}_apparent": dict(cfg)
    for name, cfg in PLANET_POSITION_EXPERIMENTS.items()
    if "_barycenter_" not in name
}
PLANET_POSITION_EXPERIMENTS.update(_PLANET_POSITION_APPARENT)

# ---------------------------------------------------------------------------
# Experiment descriptions (for non-expert users)
# ---------------------------------------------------------------------------
EXPERIMENT_DESCRIPTIONS = {
    "frame_rotation_bpn": {
        "title": "Frame Rotation (Bias-Precession-Nutation)",
        "what": "Rotates a direction vector from the ICRS celestial reference frame to the "
                "True-of-Date frame using the Bias-Precession-Nutation (BPN) matrix.",
        "why": "This is the fundamental coordinate transformation used in astrometry. "
               "Differences indicate how well each library models Earth's axis wobble.",
        "units": "Angular error in milli-arcseconds (mas). 1 mas = 1/3,600,000 of a degree.",
        "interpret": "Lower error = closer to ERFA's IAU 2006/2000A model. Siderust uses "
                     "simpler Meeus precession + IAU 1980 nutation, so some offset is expected.",
        "performance_contract": "Timed scope: matrix construction + single matrix-vector multiply "
                                "per epoch. Input JD conversion and output formatting are outside "
                                "the timed loop. All adapters construct the full BPN matrix from scratch.",
    },
    "gmst_era": {
        "title": "Greenwich Mean Sidereal Time & Earth Rotation Angle",
        "what": "Computes GMST (how far the Earth has rotated relative to the stars) and ERA "
                "(the raw rotation angle) at given epochs.",
        "why": "Time-scale conversions underpin all ground-based astronomical observations. "
               "Small errors here compound in coordinate transforms.",
        "units": "GMST error in arcseconds; ERA error in radians.",
        "interpret": "Lower error = better agreement with ERFA's IAU 2006 polynomial. "
                     "Libnova uses Meeus formula which differs at the arcsecond level.",
        "performance_contract": "Timed scope: GMST/ERA evaluation per epoch pair (JD_UT1, JD_TT). "
                                "Input parsing and output serialisation are outside the timed loop. "
                                "Astropy adapter uses public astropy.time APIs with an explicit "
                                "UT1 override derived from the benchmark input pair.",
    },
    "equ_ecl": {
        "title": "Equatorial to Ecliptic Coordinate Transform",
        "what": "Converts sky positions from RA/Dec (equatorial) to ecliptic longitude/latitude, "
                "using the obliquity of the ecliptic.",
        "why": "Ecliptic coordinates are natural for solar system objects. The transform "
               "depends on the obliquity model used.",
        "units": "Angular separation in arcseconds between reference and candidate ecliptic positions.",
        "interpret": "Lower separation = better agreement with ERFA's IAU 2006 obliquity model.",
        "performance_contract": "Timed scope: obliquity evaluation + rotation per epoch. "
                                "Input parsing is outside the timed loop.",
    },
    "equ_horizontal": {
        "title": "Equatorial to Horizontal (Alt-Az) Transform",
        "what": "Converts celestial RA/Dec to local azimuth/altitude for a ground observer, "
                "using sidereal time and spherical trigonometry.",
        "why": "This is the 'where do I point my telescope?' calculation. Accuracy depends "
               "on the GAST (sidereal time) model used.",
        "units": "Angular separation in arcseconds between reference and candidate az/alt positions.",
        "interpret": "Lower separation = better. Differences mainly arise from GAST model choice. "
                     "libnova uses a different sidereal-time model from SOFA/IERS and is not rankable "
                     "for accuracy in this experiment.",
        "performance_contract": "Timed scope: GAST computation + spherical trig per epoch+location. "
                                "Input parsing (JD, RA/Dec, lon/lat) is outside the timed loop.",
    },
    "solar_position": {
        "title": "Sun Geocentric Position",
        "what": "Computes astrometric geocentric RA/Dec of the Sun at given epochs. "
                "Accuracy reference is JPL Horizons (astrometric geocentric, ICRF, Earth geocenter, TT).",
        "why": "Sun position is needed for solar observations, shadow calculations, and "
               "as input to other transforms.",
        "units": "Angular separation in arcseconds between JPL Horizons reference and candidate Sun positions.",
        "interpret": "Lower error = closer to JPL Horizons DE441 ephemeris. "
                     "All libraries are compared as candidates against the Horizons reference.",
        "performance_contract": "Timed scope: ephemeris evaluation per epoch (no I/O). "
                                "Input JD parsing and output formatting are outside the timed loop. "
                                "libnova pre-computes VSOP87 helio position outside the timed loop; "
                                "siderust constructs frame objects inside the timed loop.",
    },
    "lunar_position": {
        "title": "Moon Geocentric Position",
        "what": "Computes astrometric geocentric RA/Dec of the Moon at given epochs. "
                "Accuracy reference is JPL Horizons (astrometric geocentric, ICRF, Earth geocenter, TT).",
        "why": "Moon position accuracy varies significantly between libraries. "
               "JPL Horizons (DE441) provides a high-accuracy external reference.",
        "units": "Angular separation in arcseconds between JPL Horizons reference and candidate positions.",
        "interpret": "Lower error = closer to JPL Horizons DE441 ephemeris. "
                     "Differences measure absolute ephemeris accuracy, not cross-library agreement.",
        "performance_contract": "Timed scope: lunar ephemeris evaluation per epoch. "
                                "Input parsing and output serialisation are outside the timed loop.",
    },
    "kepler_solver": {
        "title": "Kepler Equation Solver (M → E → ν)",
        "what": "Solves Kepler's equation M = E - e·sin(E) for the eccentric anomaly E, "
                "then computes the true anomaly ν. Tests convergence across eccentricities.",
        "why": "Kepler's equation is fundamental to orbital mechanics. Different solvers "
               "(Newton-Raphson vs bisection) have different convergence properties.",
        "units": "E and ν errors in radians. Self-consistency residual in radians.",
        "interpret": "Lower residual = better convergence. Libnova's bisection method converges "
                     "to ~1e-6 deg, while Newton-Raphson methods reach ~1e-15 rad.",
        "performance_contract": "Timed scope: iterative solver per (M, e) pair. "
                                "Input parsing is outside the timed loop. "
                                "This is a numerical convergence benchmark, not an ephemeris accuracy claim.",
    },
    "frame_bias": {
        "title": "Frame Bias (ICRS → Mean J2000)",
        "what": "Applies the ICRS-to-mean-J2000 frame bias rotation to a direction vector. "
                "This isolates the ~17 mas frame bias from precession/nutation.",
        "why": "Frame bias is a small but constant rotation. Testing it separately verifies "
               "the bias component of the full BPN matrix.",
        "units": "Angular error in mas (milliarcseconds).",
        "interpret": "All libraries implementing IAU frame bias should agree to sub-mas level.",
    },
    "precession": {
        "title": "Precession (Mean J2000 → Mean of Date)",
        "what": "Applies the IAU precession matrix to rotate from mean J2000 to mean equator "
                "and equinox of date.",
        "why": "Precession is the largest component of the BPN matrix. This isolates it from "
               "nutation and frame bias to pinpoint model accuracy.",
        "units": "Angular error in mas (milliarcseconds).",
        "interpret": "ERFA/Astropy use IAU 2006 precession. Siderust uses the same model. "
                     "libnova uses Meeus — expect arcsec-level differences.",
    },
    "nutation": {
        "title": "Nutation (Mean of Date → True of Date)",
        "what": "Applies the nutation matrix to rotate from mean equator/equinox of date "
                "to true equator/equinox of date.",
        "why": "Nutation oscillates ±9 arcsec. Isolating it reveals agreement with the SOFA IAU 2006/2000A reference.",
        "units": "Angular error in mas (milliarcseconds).",
        "interpret": "ERFA/Astropy/Siderust use IAU 2006/2000A nutation. "
                     "libnova uses IAU 1980 (69 terms), so arcsecond-scale differences are expected there.",
    },
    "icrs_ecl_j2000": {
        "title": "ICRS → Ecliptic J2000",
        "what": "Transforms an ICRS direction vector to ecliptic coordinates at the J2000 epoch. "
                "This is a time-independent rotation by the mean obliquity at J2000.",
        "why": "Tests the obliquity constant and ecliptic frame rotation without time-dependent terms.",
        "units": "Angular error in mas (milliarcseconds).",
        "interpret": "Time-independent transform — all IAU-based libraries should agree to µas level.",
    },
    "icrs_ecl_tod": {
        "title": "ICRS → Ecliptic of Date",
        "what": "Transforms equatorial RA/Dec to ecliptic longitude/latitude at the date of observation. "
                "Combines precession, nutation, and obliquity.",
        "why": "End-to-end ecliptic transform that exercises the full precession-nutation chain plus obliquity.",
        "units": "Angular separation in arcseconds.",
        "interpret": "ERFA/Astropy share IAU 2006 obliquity. libnova uses Meeus — expect arcsec differences.",
    },
    "horiz_to_equ": {
        "title": "Horizontal → Equatorial (AltAz → RA/Dec)",
        "what": "Converts horizontal (azimuth, altitude) coordinates to equatorial RA/Dec via hour angle "
                "and GAST computation.",
        "why": "Reverse of equ_horizontal. Tests the inverse spherical trig path and GAST model.",
        "units": "Angular separation in arcseconds.",
        "interpret": "Same spherical trig across all libraries. Differences arise from GAST model only.",
    },
    # 13 new matrix experiments (inverse / composed / obliquity transforms)
    "inv_frame_bias": {
        "title": "Inverse Frame Bias (Mean J2000 → ICRS)",
        "what": "Reverses the ICRS-to-J2000 frame bias by applying the transposed bias matrix.",
        "units": "Angular error in mas.", "interpret": "All IAU-based libraries agree to sub-mas.",
    },
    "inv_precession": {
        "title": "Inverse Precession (Mean of Date → Mean J2000)",
        "what": "Reverses IAU precession by applying the transposed precession matrix.",
        "units": "Angular error in mas.", "interpret": "libnova uses Meeus — arcsec differences expected.",
    },
    "inv_nutation": {
        "title": "Inverse Nutation (True of Date → Mean of Date)",
        "what": "Reverses nutation by transposing the nutation matrix (or by approximate correction in libnova).",
        "units": "Angular error in mas.", "interpret": "libnova uses approximate ΔRA/ΔDec subtraction.",
    },
    "inv_bpn": {
        "title": "Inverse BPN (True of Date → ICRS)",
        "what": "Reverses the full BPN chain (transpose of eraPnm06a matrix).",
        "units": "Angular error in mas.", "interpret": "libnova skipped (no frame bias concept).",
    },
    "inv_icrs_ecl_j2000": {
        "title": "Ecliptic J2000 → ICRS",
        "what": "Reverse of ICRS → EclipticMeanJ2000 via transposed ecliptic rotation matrix.",
        "units": "Angular error in mas.", "interpret": "Time-independent — µas agreement expected.",
    },
    "obliquity": {
        "title": "Obliquity (Ecliptic J2000 → Eq Mean J2000)",
        "what": "Pure obliquity rotation from ecliptic to equatorial at J2000 (Rx(+ε₀)).",
        "units": "Angular error in mas.", "interpret": "Time-independent obliquity constant.",
    },
    "inv_obliquity": {
        "title": "Inverse Obliquity (Eq Mean J2000 → Ecliptic J2000)",
        "what": "Pure obliquity rotation from equatorial to ecliptic at J2000 (Rx(−ε₀)).",
        "units": "Angular error in mas.", "interpret": "Time-independent obliquity constant.",
    },
    "bias_precession": {
        "title": "Bias + Precession (ICRS → Mean of Date)",
        "what": "Combined frame bias + precession: ICRS → EquatorialMeanOfDate.",
        "units": "Angular error in mas.", "interpret": "libnova skipped (no frame bias).",
    },
    "inv_bias_precession": {
        "title": "Inverse Bias+Precession (Mean of Date → ICRS)",
        "what": "Reverse of ICRS → MeanOfDate via transposed RBP matrix.",
        "units": "Angular error in mas.", "interpret": "libnova skipped (no frame bias).",
    },
    "precession_nutation": {
        "title": "Precession + Nutation (Mean J2000 → True of Date)",
        "what": "Combined precession + nutation: EquatorialMeanJ2000 → EquatorialTrueOfDate.",
        "units": "Angular error in mas.", "interpret": "libnova uses Meeus prec + IAU 1980 nut.",
    },
    "inv_precession_nutation": {
        "title": "Inverse Prec+Nut (True of Date → Mean J2000)",
        "what": "Reverse of EqMeanJ2000 → EqTrueOfDate via transposed composed matrix.",
        "units": "Angular error in mas.", "interpret": "libnova uses approximate inverses.",
    },
    "inv_icrs_ecl_tod": {
        "title": "Ecliptic of Date → ICRS",
        "what": "Reverse of ICRS → EclipticTrueOfDate (transpose of eraEcm06).",
        "units": "Angular error in mas.", "interpret": "libnova chains ecl→eq(date)→prec→J2000.",
    },
    "inv_equ_ecl": {
        "title": "Ecliptic of Date → Eq Mean of Date",
        "what": "Reverse of EqMeanOfDate → EclipticTrueOfDate.",
        "units": "Angular error in mas.", "interpret": "libnova uses ln_get_equ_from_ecl at date.",
    },
}

for exp_name, cfg in PLANET_POSITION_EXPERIMENTS.items():
    body = cfg["body"]
    is_apparent_id = exp_name.endswith("_apparent")
    lane_suffix = " (apparent observer lane)" if is_apparent_id else " (geometric vector lane)"
    ref_descr = (
        "JPL Horizons OBSERVER astrometric RA/Dec (geocenter, TT)"
        if is_apparent_id
        else "JPL Horizons geometric VECTORS (ICRF, VEC_CORR=NONE, Earth geocenter, TT)"
    )
    EXPERIMENT_DESCRIPTIONS[exp_name] = {
        "title": f"{body} Geocentric Position{lane_suffix}",
        "what": (
            f"Computes geocentric position of {body} at given epochs. "
            f"Accuracy reference is {ref_descr}."
        ),
        "why": (
            f"{body} position is needed for planetary observation planning, guiding, and "
            "cross-checking analytic ephemerides against JPL kernels."
        ),
        "units": (
            f"Angular separation in arcseconds between JPL Horizons reference and candidate {body} positions."
        ),
        "interpret": (
            "Lower error = closer to JPL Horizons DE441 ephemeris on the selected lane. "
            "Geometric and apparent lanes are reported separately because their model "
            "assumptions (aberration / light-time / nutation) differ."
        ),
    }

# Apparent variants of Sun and Moon mirror the public IDs but compare against
# the OBSERVER lane rather than the geometric VECTORS lane.
for _body_id, _body_name in (("solar_position", "Sun"), ("lunar_position", "Moon")):
    EXPERIMENT_DESCRIPTIONS[f"{_body_id}_apparent"] = {
        "title": f"{_body_name} Geocentric Position (apparent observer lane)",
        "what": (
            f"Computes geocentric RA/Dec of the {_body_name} at given epochs and compares against "
            "JPL Horizons OBSERVER astrometric RA/Dec (geocenter, TT)."
        ),
        "why": (
            "Diagnostic lane for candidates that internally apply aberration / light-time / "
            "nutation. Not mixed into the public geometric rankings."
        ),
        "units": "Angular separation in arcseconds.",
        "interpret": (
            "Lower error = closer to JPL Horizons OBSERVER astrometric solution. "
            "Use the geometric lane (no '_apparent' suffix) for cross-library geometric comparison."
        ),
    }

# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

def progress(msg: str, experiment: str = "", step: str = "", total_steps: int = 0, current_step: int = 0):
    """Print a structured progress message that the web app can parse.
    
    Format: [PROGRESS] experiment=<name> step=<step> current=<n> total=<m> | <message>
    """
    parts = ["[PROGRESS]"]
    if experiment:
        parts.append(f"experiment={experiment}")
    if step:
        parts.append(f"step={step}")
    if total_steps > 0:
        parts.append(f"current={current_step}")
        parts.append(f"total={total_steps}")
    parts.append(f"| {msg}")
    print(" ".join(parts), flush=True)


def dataset_fingerprint(data: dict) -> str:
    """Compute a SHA-256 fingerprint of the input dataset for reproducibility."""
    canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _build_rust_adapter(manifest: Path, name: str) -> None:
    """Build a Rust adapter so benchmark runs use current local sources."""
    cmd = ["cargo", "build", "--release", "--manifest-path", str(manifest)]
    print(f"Ensuring {name} adapter is up to date...")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(LAB_ROOT),
    )
    if result.returncode != 0:
        print(f"✗ Failed to build {name} adapter.", file=sys.stderr)
        if result.stderr:
            print(result.stderr[-1000:], file=sys.stderr)
        raise SystemExit(2)
    print(f"✓ {name.capitalize()} adapter build complete.")


def ensure_rust_adapters_built() -> None:
    """Build Rust adapters used by this lab."""
    _build_rust_adapter(
        LAB_ROOT / "pipeline" / "adapters" / "siderust_adapter" / "Cargo.toml",
        "siderust",
    )
    _build_rust_adapter(
        LAB_ROOT / "pipeline" / "adapters" / "anise_adapter" / "Cargo.toml",
        "anise",
    )

# ---------------------------------------------------------------------------
# Input generation
# ---------------------------------------------------------------------------

def generate_frame_rotation_inputs(n: int, seed: int):
    """
    Generate test inputs for the frame_rotation_bpn experiment.

    Returns:
        epochs: array of JD(TT) values
        directions: Nx3 array of unit vectors in ICRS
        case_labels: list of human-readable case labels
    """
    rng = np.random.default_rng(seed)

    # --- Epochs ---
    # Typical dates: 2000–2030
    typical_epochs = 2451545.0 + rng.uniform(0, 30 * 365.25, size=max(1, n - 10))

    # Edge-case epochs
    edge_epochs = np.array([
        2451545.0,            # J2000.0 exactly
        2451545.5,            # J2000.0 + 0.5 day
        2451179.5,            # 1999-01-01 (near J2000)
        2415020.0,            # ~1900 (wide range)
        2488069.5,            # ~2100 (wide range)
        2457754.5,            # 2017-01-01 (leap second on 2016-12-31)
        2453736.5,            # 2006-01-01 (IAU 2006 precession epoch)
        2459580.5,            # 2022-02-01 (recent)
        2460310.5,            # 2024-01-01
        2460676.5,            # 2025-01-01
    ])

    epochs = np.concatenate([typical_epochs, edge_epochs])[:n]
    np.random.default_rng(seed).shuffle(epochs)

    # --- Directions ---
    # Random unit vectors on the sphere
    random_dirs = rng.standard_normal((max(1, n - 6), 3))
    random_dirs /= np.linalg.norm(random_dirs, axis=1, keepdims=True)

    # Named directions (edge cases)
    edge_dirs = np.array([
        [1.0, 0.0, 0.0],            # +X (vernal equinox direction)
        [0.0, 1.0, 0.0],            # +Y
        [0.0, 0.0, 1.0],            # +Z (north celestial pole)
        [0.0, 0.0, -1.0],           # -Z (south celestial pole)
        [1.0/math.sqrt(3)] * 3,     # diagonal
        [-1.0/math.sqrt(3)] * 3,    # anti-diagonal
    ])

    directions = np.vstack([random_dirs, edge_dirs])[:n]

    # Labels
    labels = [f"random_{i}" for i in range(max(0, n - 6))]
    labels += ["equinox_+X", "+Y", "north_pole_+Z", "south_pole_-Z", "diagonal", "anti_diagonal"]
    labels = labels[:n]

    return epochs, directions, labels


def generate_gmst_era_inputs(n: int, seed: int):
    """Generate test inputs for the gmst_era experiment."""
    rng = np.random.default_rng(seed)

    # JD(UT1) values: spread over 2000–2030
    typical_ut1 = 2451545.0 + rng.uniform(0, 30 * 365.25, size=max(1, n - 5))

    edge_ut1 = np.array([
        2451545.0,   # J2000.0
        2451179.5,   # 1999-01-01
        2415020.0,   # ~1900
        2488069.5,   # ~2100
        2457754.5,   # 2017-01-01
    ])

    jd_ut1 = np.concatenate([typical_ut1, edge_ut1])[:n]

    # TT ≈ UT1 + ΔT; for simplicity use ΔT ≈ 69.184s / 86400 ≈ 0.0008 days
    delta_t_days = 69.184 / 86400.0
    jd_tt = jd_ut1 + delta_t_days

    return jd_ut1, jd_tt


def generate_equ_ecl_inputs(n: int, seed: int):
    """Generate inputs for equatorial ↔ ecliptic transform experiment.

    Returns (epochs, ra, dec) — all in radians.
    """
    rng = np.random.default_rng(seed)

    # Epochs: 2000–2100
    typical = 2451545.0 + rng.uniform(0, 100 * 365.25, size=max(1, n - 6))
    edge = np.array([
        2451545.0,    # J2000
        2415020.0,    # ~1900
        2488069.5,    # ~2100
        2460676.5,    # 2025
        2453736.5,    # 2006 (IAU 2006 epoch)
        2460310.5,    # 2024
    ])
    epochs = np.concatenate([typical, edge])[:n]

    # RA ∈ [0, 2π), Dec ∈ [-π/2, π/2]
    ra = rng.uniform(0, 2 * np.pi, size=n)
    dec = np.arcsin(rng.uniform(-1, 1, size=n))  # uniform on sphere

    # Inject edge cases in the first few slots
    if n >= 4:
        ra[0], dec[0] = 0.0, 0.0        # vernal equinox
        ra[1], dec[1] = np.pi, 0.0       # autumnal equinox
        ra[2], dec[2] = 0.0, np.pi / 2   # north pole
        ra[3], dec[3] = 0.0, -np.pi / 2  # south pole

    return epochs, ra, dec


def generate_equ_horizontal_inputs(n: int, seed: int):
    """Generate inputs for equatorial → horizontal coordinate transform.

    Returns (jd_ut1, jd_tt, ra, dec, observer_lon, observer_lat) — all radians.
    """
    rng = np.random.default_rng(seed)

    jd_ut1 = 2451545.0 + rng.uniform(0, 30 * 365.25, size=n)
    delta_t_days = 69.184 / 86400.0
    jd_tt = jd_ut1 + delta_t_days

    ra = rng.uniform(0, 2 * np.pi, size=n)
    dec = np.arcsin(rng.uniform(-1, 1, size=n))

    # Observer locations: lon ∈ [-π, π], lat ∈ [-π/2, π/2]
    lon = rng.uniform(-np.pi, np.pi, size=n)
    lat = np.arcsin(rng.uniform(-1, 1, size=n))

    # Inject known observatory locations (radians)
    if n >= 3:
        # Greenwich: lon=0, lat=51.4769°
        lon[0], lat[0] = 0.0, np.deg2rad(51.4769)
        # Cerro Paranal: lon=-70.4042°, lat=-24.6272°
        lon[1], lat[1] = np.deg2rad(-70.4042), np.deg2rad(-24.6272)
        # North pole observer
        lon[2], lat[2] = 0.0, np.pi / 2

    return jd_ut1, jd_tt, ra, dec, lon, lat


def generate_solar_position_inputs(n: int, seed: int):
    """Generate epoch inputs for Sun position experiment.

    Returns array of JD(TT) values spanning 1900–2100.
    """
    rng = np.random.default_rng(seed)

    # JD range: ~1900 (2415020) to ~2100 (2488069)
    typical = rng.uniform(2415020.0, 2488069.5, size=max(1, n - 6))
    edge = np.array([
        2451545.0,    # J2000
        2451179.5,    # 1999-01-01
        2460310.5,    # 2024-01-01
        2451625.0,    # ~2000 March equinox
        2451716.0,    # ~2000 June solstice
        2451900.0,    # ~2000 Dec solstice
    ])
    return np.concatenate([typical, edge])[:n]


def generate_lunar_position_inputs(n: int, seed: int):
    """Generate epoch inputs for Moon position experiment.

    Returns array of JD(TT) values spanning 1900–2100.
    """
    rng = np.random.default_rng(seed)

    typical = rng.uniform(2415020.0, 2488069.5, size=max(1, n - 6))
    edge = np.array([
        2451545.0,    # J2000
        2451550.0,    # near J2000
        2460310.5,    # 2024-01-01
        2459580.5,    # 2022-02-01
        2451179.5,    # 1999-01-01
        2488069.5,    # ~2100
    ])
    return np.concatenate([typical, edge])[:n]


def generate_planet_position_inputs(n: int, seed: int):
    """Generate epoch inputs for planetary position experiments."""
    return generate_solar_position_inputs(n, seed)


def generate_kepler_inputs(n: int, seed: int):
    """Generate inputs for Kepler's equation experiment.

    Returns (M_array, e_array) — M in radians, e in [0, 1).
    """
    rng = np.random.default_rng(seed)

    # Specific eccentricities to probe accuracy across the range
    fixed_ecc = np.array([0.0, 1e-6, 0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.95, 0.99, 0.999, 0.999999])

    M_list = []
    e_list = []

    # For each fixed eccentricity, generate several M values
    per_ecc = max(1, (n - 10) // len(fixed_ecc))
    for ecc in fixed_ecc:
        M_vals = rng.uniform(0, 2 * np.pi, size=per_ecc)
        M_list.extend(M_vals)
        e_list.extend([ecc] * per_ecc)

    # Fill remaining with random e ∈ [0, 1)
    remaining = max(0, n - len(M_list))
    if remaining > 0:
        M_list.extend(rng.uniform(0, 2 * np.pi, size=remaining))
        e_list.extend(rng.uniform(0, 0.999, size=remaining))

    M_arr = np.array(M_list[:n])
    e_arr = np.array(e_list[:n])

    # Edge cases: M = 0, M = π
    if n >= 2:
        M_arr[0], e_arr[0] = 0.0, 0.5
        M_arr[1], e_arr[1] = np.pi, 0.5

    return M_arr, e_arr


def generate_direction_vector_inputs(n: int, seed: int):
    """Generate random JD TT epochs + unit direction vectors for frame transform tests."""
    rng = np.random.default_rng(seed)
    # 100-year range centered on J2000 (JD 2451545.0 = 2000-01-01.5 TT)
    jd_tt = rng.uniform(2451545.0, 2488070.0, size=n)
    # Random unit vectors on the sphere
    phi = rng.uniform(0, 2 * np.pi, size=n)
    cos_theta = rng.uniform(-1, 1, size=n)
    sin_theta = np.sqrt(1 - cos_theta**2)
    directions = np.column_stack([
        sin_theta * np.cos(phi),
        sin_theta * np.sin(phi),
        cos_theta,
    ])
    return jd_tt, directions


def generate_horiz_to_equ_inputs(n: int, seed: int):
    """Generate random horizontal coordinates + observer locations for horiz_to_equ tests."""
    rng = np.random.default_rng(seed + 7)  # offset seed to avoid duplicate data
    jd_tt = rng.uniform(2451545.0, 2488070.0, size=n)
    jd_ut1 = jd_tt - 69.184 / 86400.0  # simplified UT1 ≈ TT - 69.184s
    # Azimuth 0..2π, altitude 5°..89° (avoid horizon and zenith singularities)
    az = rng.uniform(0, 2 * np.pi, size=n)
    alt = rng.uniform(np.radians(5), np.radians(89), size=n)
    # Random observer locations
    obs_lon = rng.uniform(-np.pi, np.pi, size=n)
    obs_lat = np.arcsin(rng.uniform(-1.0, 1.0, size=n))
    return jd_ut1, jd_tt, az, alt, obs_lon, obs_lat


# ---------------------------------------------------------------------------
# Adapter runners
# ---------------------------------------------------------------------------


def empty_performance_workloads() -> dict:
    """Return the additive Phase-6 performance schema with all workloads absent."""
    return {"scalar_warm": None, "batch_throughput": None, "setup_metrics": None}


def _adapter_experiment_name(experiment: str) -> str:
    return strip_apparent_suffix(experiment)

def run_adapter(cmd, input_text: str, label: str, *, extra_env: dict | None = None, timeout: int = 120) -> dict:
    """Run an adapter process, return parsed JSON output.

    ``extra_env`` is merged into the child environment (e.g. ``LAB_LANE``
    so an adapter that implements both lanes can pick the right path).
    """
    env = None
    if extra_env:
        env = os.environ.copy()
        env.update({k: str(v) for k, v in extra_env.items()})
    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        print(f"  ⚠ {label}: binary not found ({cmd[0]}), skipping.", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"  ⚠ {label}: timed out after {timeout}s, skipping.", file=sys.stderr)
        return None

    if result.returncode != 0:
        print(f"  ⚠ {label}: exit code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"     stderr: {result.stderr[:500]}", file=sys.stderr)
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  ⚠ {label}: JSON parse error: {e}", file=sys.stderr)
        print(f"     stdout[:500]: {result.stdout[:500]}", file=sys.stderr)
        return None


def format_bpn_input(epochs, directions):
    """Format input for the frame_rotation_bpn experiment."""
    lines = ["frame_rotation_bpn", str(len(epochs))]
    for jd, d in zip(epochs, directions):
        lines.append(f"{jd:.15f} {d[0]:.17e} {d[1]:.17e} {d[2]:.17e}")
    return "\n".join(lines) + "\n"


def format_gmst_input(jd_ut1, jd_tt):
    """Format input for the gmst_era experiment."""
    lines = ["gmst_era", str(len(jd_ut1))]
    for u, t in zip(jd_ut1, jd_tt):
        lines.append(f"{u:.15f} {t:.15f}")
    return "\n".join(lines) + "\n"


def _adapter_perf_round_issues(result: dict | None) -> list[str]:
    """Reasons a single adapter perf JSON round must not contribute to ranking."""
    if result is None:
        return ["adapter returned no result"]
    issues: list[str] = []
    if result.get("skipped"):
        issues.append(str(result.get("reason") or "adapter skipped performance"))
    if result.get("valid") is False:
        issues.append(str(result.get("reason") or "adapter marked performance invalid"))
    status = result.get("status")
    if status in ("partial", "failed", "skipped"):
        issues.append(f"adapter performance status={status}")
    count_requested = result.get("count_requested")
    if count_requested is None:
        count_requested = result.get("count")
    count_valid = result.get("count_valid")
    if count_requested is not None and count_valid is not None:
        if int(count_valid) < int(count_requested):
            issues.append(f"only {count_valid}/{count_requested} perf cases succeeded")
    error_count = result.get("error_count")
    if error_count is not None and int(error_count) > 0:
        issues.append(f"error_count={error_count}")
    for key in ("nan_count", "inf_count"):
        val = result.get(key)
        if val is not None and int(val) > 0:
            issues.append(f"{key}={val}")
    return issues


def run_multi_sample_perf(cmd, input_text: str, label: str,
                          rounds: int = DEFAULT_PERF_ROUNDS,
                          *,
                          extra_env: dict | None = None,
                          timeout: int = 120) -> dict | None:
    """Run performance adapter multiple rounds, compute statistical summary.

    A5 / fairness-audit F1: ``extra_env`` (e.g. ``{"LAB_LANE": "geometric_vector"}``)
    is propagated to every per-round invocation so perf measurements run under
    the same lane as the accuracy measurements they accompany. Callers that
    forget to pass ``extra_env`` will silently run the adapter's default lane,
    which is detectable by the perf-lane regression test.

    Returns a dict with per_op_ns stats: mean, median, std_dev, min, max, ci95, samples.
    """
    samples_per_op = []
    samples_total = []
    last_result: dict | None = None

    for r in range(rounds):
        result = run_adapter(cmd, input_text, f"{label}_round{r}", extra_env=extra_env, timeout=timeout)
        last_result = result
        issues = _adapter_perf_round_issues(result)
        if issues:
            count_requested = None
            count_valid = None
            error_count = None
            if isinstance(result, dict):
                count_requested = result.get("count_requested", result.get("count"))
                count_valid = result.get("count_valid")
                error_count = result.get("error_count")
            return {
                "per_op_ns": None,
                "valid": False,
                "skipped": bool(isinstance(result, dict) and result.get("skipped")),
                "warnings": issues,
                "count_requested": count_requested,
                "count_valid": count_valid,
                "error_count": error_count,
                "batch_size": count_requested,
                "rounds": rounds,
                "samples": [],
            }

        per_op = result.get("per_op_ns")
        total = result.get("total_ns")

        if per_op is not None:
            samples_per_op.append(per_op)
        if total is not None:
            samples_total.append(total)

    if not samples_per_op or last_result is None:
        return None

    final_issues = _adapter_perf_round_issues(last_result)
    if final_issues:
        count_requested = None
        count_valid = None
        error_count = None
        if isinstance(last_result, dict):
            count_requested = last_result.get("count_requested", last_result.get("count"))
            count_valid = last_result.get("count_valid")
            error_count = last_result.get("error_count")
        return {
            "per_op_ns": None,
            "valid": False,
            "skipped": bool(isinstance(last_result, dict) and last_result.get("skipped")),
            "warnings": final_issues,
            "count_requested": count_requested,
            "count_valid": count_valid,
            "error_count": error_count,
            "batch_size": count_requested,
            "rounds": rounds,
            "samples": samples_per_op,
        }

    mean_ns = statistics.mean(samples_per_op)
    median_ns = statistics.median(samples_per_op)
    std_dev = statistics.stdev(samples_per_op) if len(samples_per_op) > 1 else 0.0
    min_ns = min(samples_per_op)
    max_ns = max(samples_per_op)

    # 95% confidence interval (assumes normal distribution)
    n = len(samples_per_op)
    ci95_half = 1.96 * std_dev / math.sqrt(n) if n > 1 else 0.0

    # Coefficient of variation (stability indicator)
    cv = (std_dev / mean_ns * 100) if mean_ns > 0 else 0.0

    # "Too fast to measure" warning
    warnings = []
    if median_ns < MIN_MEASURABLE_NS:
        warnings.append(
            f"Per-op time ({median_ns:.1f} ns) is below measurable threshold "
            f"({MIN_MEASURABLE_NS} ns). Results may be dominated by measurement overhead."
        )
    if cv > 20:
        warnings.append(
            f"High coefficient of variation ({cv:.1f}%). Results are unstable. "
            "Consider increasing sample count or reducing system load."
        )

    count_requested = last_result.get("count_requested", last_result.get("count"))
    count_valid = last_result.get("count_valid")
    error_count = last_result.get("error_count", 0)
    coverage_ok = (
        count_requested is None
        or (
            count_valid is not None
            and int(count_valid) >= int(count_requested)
            and int(error_count or 0) == 0
        )
    )
    stat_valid = coverage_ok and median_ns >= MIN_MEASURABLE_NS and cv <= 20
    if not coverage_ok:
        warnings.append(
            f"Incomplete perf coverage: count_valid={count_valid}, "
            f"count_requested={count_requested}, error_count={error_count}"
        )

    return {
        "per_op_ns": median_ns,  # Use median as primary (robust to outliers)
        "per_op_ns_mean": mean_ns,
        "per_op_ns_median": median_ns,
        "per_op_ns_std_dev": std_dev,
        "per_op_ns_min": min_ns,
        "per_op_ns_max": max_ns,
        "per_op_ns_ci95": [mean_ns - ci95_half, mean_ns + ci95_half],
        "per_op_ns_cv_pct": cv,
        "throughput_ops_s": 1e9 / median_ns if median_ns > 0 else 0,
        "total_ns_median": statistics.median(samples_total) if samples_total else None,
        "batch_size": count_requested,
        "count_requested": count_requested,
        "count_valid": count_valid,
        "error_count": error_count,
        "rounds": rounds,
        "samples": samples_per_op,
        "valid": stat_valid,
        "warnings": warnings,
    }


def _scalar_warm_summary(perf: dict | None, *, rounds: int, n_per_round: int, warmup: int = DEFAULT_PERF_WARMUP) -> dict | None:
    if not perf:
        return None
    count_requested = perf.get("count_requested", perf.get("batch_size") or n_per_round)
    count_valid = perf.get("count_valid")
    block = {
        "ns_per_op": perf.get("per_op_ns"),
        "cv": perf.get("per_op_ns_cv_pct"),
        "rounds": rounds,
        "n_per_round": perf.get("batch_size") or n_per_round,
        "count_requested": count_requested,
        "count_valid": count_valid,
        "error_count": perf.get("error_count", 0),
        "warmup": warmup,
        "valid": perf.get("valid"),
        "warnings": perf.get("warnings") or [],
        "skipped": perf.get("skipped"),
        "status": perf.get("status"),
    }
    issues = _perf_block_issues(block, expected_n=n_per_round)
    if issues:
        return _mark_perf_block_invalid(block, issues)
    return block


def _batch_throughput_summary(perf: dict | None, *, rounds: int, n: int, warmup: int = DEFAULT_PERF_WARMUP) -> dict | None:
    if not perf:
        return None
    ns = perf.get("per_op_ns")
    items_per_sec = perf.get("throughput_ops_s")
    if items_per_sec is None and isinstance(ns, (int, float)) and ns > 0:
        items_per_sec = 1e9 / ns
    count_requested = perf.get("count_requested", perf.get("batch_size") or n)
    count_valid = perf.get("count_valid")
    block = {
        "ns_per_op": ns,
        "items_per_sec": items_per_sec,
        "cv": perf.get("per_op_ns_cv_pct"),
        "rounds": rounds,
        "n": perf.get("batch_size") or n,
        "count_requested": count_requested,
        "count_valid": count_valid,
        "error_count": perf.get("error_count", 0),
        "warmup": warmup,
        "valid": perf.get("valid"),
        "warnings": perf.get("warnings") or [],
        "skipped": perf.get("skipped"),
        "status": perf.get("status"),
    }
    issues = _perf_block_issues(block, expected_n=n)
    if issues:
        return _mark_perf_block_invalid(block, issues)
    return block


def _setup_metrics_summary(result: dict | None) -> dict | None:
    if not isinstance(result, dict):
        return None
    setup_ms = result.get("setup_ms")
    if setup_ms is None:
        return None
    try:
        setup_ms = float(setup_ms)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(setup_ms) or setup_ms < 0:
        return None
    return {"setup_ms": setup_ms, "measured": bool(result.get("measured", True))}


def run_perf_workloads(cmd, exp_name: str, input_gen_fn, perf_fmt_fn, seed: int,
                       *, scalar_rounds: int = DEFAULT_PERF_ROUNDS,
                       scalar_n: int = SCALAR_WARM_N,
                       batch_rounds: int = BATCH_THROUGHPUT_ROUNDS,
                       batch_n: int = BATCH_THROUGHPUT_N,
                       warmup: int = DEFAULT_PERF_WARMUP,
                       timeout_s: int = 120,
                       extra_env: dict | None = None) -> dict:
    """Run Phase-6 performance workloads for one adapter candidate."""
    workloads = empty_performance_workloads()
    adapter_exp = _adapter_experiment_name(exp_name)

    scalar_inputs = input_gen_fn(scalar_n, seed)
    scalar_input = perf_fmt_fn(*scalar_inputs) if not isinstance(scalar_inputs, str) else scalar_inputs
    # Ensure adapters receive configured warmup via environment variable
    merged_env = dict(extra_env or {})
    merged_env["LAB_PERF_WARMUP"] = str(warmup)

    scalar_perf = run_multi_sample_perf(
        cmd, scalar_input, f"{adapter_exp}_scalar_warm",
        rounds=scalar_rounds, extra_env=merged_env, timeout=timeout_s,
    )
    workloads["scalar_warm"] = _scalar_warm_summary(
        scalar_perf, rounds=scalar_rounds, n_per_round=scalar_n, warmup=warmup,
    )

    batch_inputs = input_gen_fn(batch_n, seed)
    batch_input = perf_fmt_fn(*batch_inputs) if not isinstance(batch_inputs, str) else batch_inputs
    batch_perf = run_multi_sample_perf(
        cmd, batch_input, f"{adapter_exp}_batch_throughput",
        rounds=batch_rounds, extra_env=merged_env, timeout=timeout_s,
    )
    workloads["batch_throughput"] = _batch_throughput_summary(
        batch_perf, rounds=batch_rounds, n=batch_n, warmup=warmup,
    )

    setup_result = run_adapter(
        cmd, f"{adapter_exp}_setup\n", f"{adapter_exp}_setup", extra_env=merged_env, timeout=timeout_s,
    )
    workloads["setup_metrics"] = _setup_metrics_summary(setup_result)
    return workloads


def format_bpn_perf_input(epochs, directions):
    """Format input for the BPN performance experiment."""
    lines = ["frame_rotation_bpn_perf", str(len(epochs))]
    for jd, d in zip(epochs, directions):
        lines.append(f"{jd:.15f} {d[0]:.17e} {d[1]:.17e} {d[2]:.17e}")
    return "\n".join(lines) + "\n"


def format_gmst_perf_input(jd_ut1, jd_tt):
    """Format input for the GMST/ERA performance experiment."""
    lines = ["gmst_era_perf", str(len(jd_ut1))]
    for u, t in zip(jd_ut1, jd_tt):
        lines.append(f"{u:.15f} {t:.15f}")
    return "\n".join(lines) + "\n"


def format_equ_ecl_perf_input(epochs, ra, dec):
    """Format input for equatorial-ecliptic performance experiment."""
    lines = ["equ_ecl_perf", str(len(epochs))]
    for jd, r, d in zip(epochs, ra, dec):
        lines.append(f"{jd:.15f} {r:.17e} {d:.17e}")
    return "\n".join(lines) + "\n"


def format_equ_horizontal_perf_input(jd_ut1, jd_tt, ra, dec, lon, lat):
    """Format input for equatorial-horizontal performance experiment."""
    lines = ["equ_horizontal_perf", str(len(jd_ut1))]
    for u, t, r, d, lo, la in zip(jd_ut1, jd_tt, ra, dec, lon, lat):
        lines.append(f"{u:.15f} {t:.15f} {r:.17e} {d:.17e} {lo:.17e} {la:.17e}")
    return "\n".join(lines) + "\n"


def _format_external_position_perf_input(experiment, epochs):
    """Format input for solar/lunar/planetary position performance experiments."""
    adapter_exp = experiment[:-len("_apparent")] if experiment.endswith("_apparent") else experiment
    lines = [f"{adapter_exp}_perf", str(len(epochs))]
    for jd in epochs:
        lines.append(f"{jd:.15f}")
    return "\n".join(lines) + "\n"


def format_solar_position_perf_input(epochs):
    """Format input for solar position performance experiment."""
    return _format_external_position_perf_input("solar_position", epochs)


def format_lunar_position_perf_input(epochs):
    """Format input for lunar position performance experiment."""
    return _format_external_position_perf_input("lunar_position", epochs)


def format_kepler_perf_input(M_arr, e_arr):
    """Format input for Kepler solver performance experiment."""
    lines = ["kepler_solver_perf", str(len(M_arr))]
    for m, e in zip(M_arr, e_arr):
        lines.append(f"{m:.17e} {e:.17e}")
    return "\n".join(lines) + "\n"


def format_equ_ecl_input(epochs, ra, dec):
    """Format input for equ_ecl experiment: jd_tt ra dec per line."""
    lines = ["equ_ecl", str(len(epochs))]
    for jd, r, d in zip(epochs, ra, dec):
        lines.append(f"{jd:.15f} {r:.17e} {d:.17e}")
    return "\n".join(lines) + "\n"


def format_equ_horizontal_input(jd_ut1, jd_tt, ra, dec, lon, lat):
    """Format input for equ_horizontal experiment: jd_ut1 jd_tt ra dec lon lat per line."""
    lines = ["equ_horizontal", str(len(jd_ut1))]
    for u, t, r, d, lo, la in zip(jd_ut1, jd_tt, ra, dec, lon, lat):
        lines.append(f"{u:.15f} {t:.15f} {r:.17e} {d:.17e} {lo:.17e} {la:.17e}")
    return "\n".join(lines) + "\n"


def _format_external_position_input(experiment, epochs):
    """Format input for solar/lunar/planetary position experiments.

    Lane-aware: ``*_apparent`` IDs share the *same* adapter input as their
    geometric counterparts (the adapter doesn't know about JPL lanes), so we
    strip the suffix before writing the experiment header.
    """
    adapter_exp = experiment[:-len("_apparent")] if experiment.endswith("_apparent") else experiment
    lines = [adapter_exp, str(len(epochs))]
    for jd in epochs:
        lines.append(f"{jd:.15f}")
    return "\n".join(lines) + "\n"


def format_solar_position_input(epochs):
    """Format input for solar_position experiment: jd_tt per line."""
    return _format_external_position_input("solar_position", epochs)


def format_lunar_position_input(epochs):
    """Format input for lunar_position experiment: jd_tt per line."""
    return _format_external_position_input("lunar_position", epochs)


def format_kepler_input(M_arr, e_arr):
    """Format input for kepler_solver experiment: M e per line."""
    lines = ["kepler_solver", str(len(M_arr))]
    for m, e in zip(M_arr, e_arr):
        lines.append(f"{m:.17e} {e:.17e}")
    return "\n".join(lines) + "\n"


# --- Direction-vector format helpers (frame_bias, precession, nutation, icrs_ecl_j2000) ---

def _format_direction_vector_input(exp_name, epochs, directions):
    """Generic formatter for direction-vector experiments."""
    lines = [exp_name, str(len(epochs))]
    for jd, d in zip(epochs, directions):
        lines.append(f"{jd:.15f} {d[0]:.17e} {d[1]:.17e} {d[2]:.17e}")
    return "\n".join(lines) + "\n"


def format_frame_bias_input(epochs, directions):
    return _format_direction_vector_input("frame_bias", epochs, directions)

def format_frame_bias_perf_input(epochs, directions):
    return _format_direction_vector_input("frame_bias_perf", epochs, directions)

def format_precession_input(epochs, directions):
    return _format_direction_vector_input("precession", epochs, directions)

def format_precession_perf_input(epochs, directions):
    return _format_direction_vector_input("precession_perf", epochs, directions)

def format_nutation_input(epochs, directions):
    return _format_direction_vector_input("nutation", epochs, directions)

def format_nutation_perf_input(epochs, directions):
    return _format_direction_vector_input("nutation_perf", epochs, directions)

def format_icrs_ecl_j2000_input(epochs, directions):
    return _format_direction_vector_input("icrs_ecl_j2000", epochs, directions)

def format_icrs_ecl_j2000_perf_input(epochs, directions):
    return _format_direction_vector_input("icrs_ecl_j2000_perf", epochs, directions)

# 13 new experiments — all use direction-vector format
def _make_dir_format_pair(exp_name):
    """Factory for format functions for direction-vector experiments."""
    def fmt(epochs, directions):
        return _format_direction_vector_input(exp_name, epochs, directions)
    def fmt_perf(epochs, directions):
        return _format_direction_vector_input(f"{exp_name}_perf", epochs, directions)
    return fmt, fmt_perf

format_inv_frame_bias_input, format_inv_frame_bias_perf_input = _make_dir_format_pair("inv_frame_bias")
format_inv_precession_input, format_inv_precession_perf_input = _make_dir_format_pair("inv_precession")
format_inv_nutation_input, format_inv_nutation_perf_input = _make_dir_format_pair("inv_nutation")
format_inv_bpn_input, format_inv_bpn_perf_input = _make_dir_format_pair("inv_bpn")
format_inv_icrs_ecl_j2000_input, format_inv_icrs_ecl_j2000_perf_input = _make_dir_format_pair("inv_icrs_ecl_j2000")
format_obliquity_input, format_obliquity_perf_input = _make_dir_format_pair("obliquity")
format_inv_obliquity_input, format_inv_obliquity_perf_input = _make_dir_format_pair("inv_obliquity")
format_bias_precession_input, format_bias_precession_perf_input = _make_dir_format_pair("bias_precession")
format_inv_bias_precession_input, format_inv_bias_precession_perf_input = _make_dir_format_pair("inv_bias_precession")
format_precession_nutation_input, format_precession_nutation_perf_input = _make_dir_format_pair("precession_nutation")
format_inv_precession_nutation_input, format_inv_precession_nutation_perf_input = _make_dir_format_pair("inv_precession_nutation")
format_inv_icrs_ecl_tod_dir_input, format_inv_icrs_ecl_tod_dir_perf_input = _make_dir_format_pair("inv_icrs_ecl_tod")
format_inv_equ_ecl_dir_input, format_inv_equ_ecl_dir_perf_input = _make_dir_format_pair("inv_equ_ecl")


def format_icrs_ecl_tod_input(epochs, ra, dec):
    """Format input for icrs_ecl_tod experiment: jd_tt ra dec per line."""
    lines = ["icrs_ecl_tod", str(len(epochs))]
    for jd, r, d in zip(epochs, ra, dec):
        lines.append(f"{jd:.15f} {r:.17e} {d:.17e}")
    return "\n".join(lines) + "\n"


def format_icrs_ecl_tod_perf_input(epochs, ra, dec):
    """Format input for icrs_ecl_tod performance experiment."""
    lines = ["icrs_ecl_tod_perf", str(len(epochs))]
    for jd, r, d in zip(epochs, ra, dec):
        lines.append(f"{jd:.15f} {r:.17e} {d:.17e}")
    return "\n".join(lines) + "\n"


def format_horiz_to_equ_input(jd_ut1, jd_tt, az, alt, lon, lat):
    """Format input for horiz_to_equ experiment: jd_ut1 jd_tt az alt lon lat per line."""
    lines = ["horiz_to_equ", str(len(jd_ut1))]
    for u, t, a, al, lo, la in zip(jd_ut1, jd_tt, az, alt, lon, lat):
        lines.append(f"{u:.15f} {t:.15f} {a:.17e} {al:.17e} {lo:.17e} {la:.17e}")
    return "\n".join(lines) + "\n"


def format_horiz_to_equ_perf_input(jd_ut1, jd_tt, az, alt, lon, lat):
    """Format input for horiz_to_equ performance experiment."""
    lines = ["horiz_to_equ_perf", str(len(jd_ut1))]
    for u, t, a, al, lo, la in zip(jd_ut1, jd_tt, az, alt, lon, lat):
        lines.append(f"{u:.15f} {t:.15f} {a:.17e} {al:.17e} {lo:.17e} {la:.17e}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _check_case_counts(ref_cases, cand_cases, ref_label, cand_label):
    """Return an error dict when case lengths mismatch, else None."""
    if len(ref_cases) != len(cand_cases):
        return {
            "error": "case count mismatch",
            "reference": ref_label,
            "candidate": cand_label,
            "ref_count": len(ref_cases),
            "cand_count": len(cand_cases),
        }
    return None


def compute_accuracy_metrics(ref_cases, cand_cases, ref_label, cand_label):
    """
    Compare candidate adapter results to reference adapter results.

    Metrics:
        angular_error_mas: angular separation between output directions
        closure_error_rad: self-consistency (A→B→A) error
        matrix_frobenius:  Frobenius norm of matrix difference

    Returns a dict of computed metrics.
    """
    mismatch = _check_case_counts(ref_cases, cand_cases, ref_label, cand_label)
    if mismatch:
        return mismatch
    angular_errors_mas = []
    closure_errors_rad = []
    matrix_frob_norms = []
    nan_count = 0
    inf_count = 0
    worst_cases = []

    for ref_c, cand_c in zip(ref_cases, cand_cases):
        ref_out = np.array(ref_c["output"])
        cand_out = np.array(cand_c["output"])

        # Check for NaN/Inf
        if np.any(np.isnan(cand_out)):
            nan_count += 1
            continue
        if np.any(np.isinf(cand_out)):
            inf_count += 1
            continue

        # Angular error — stable atan2(|cross|, dot) formulation. The
        # legacy acos(dot) clamp introduces a floor at ~1e-8 rad due to
        # the derivative singularity of acos near 1; audit fix (issue F5).
        cross = np.cross(ref_out, cand_out)
        ang_err_rad = math.atan2(float(np.linalg.norm(cross)), float(np.dot(ref_out, cand_out)))
        ang_err_mas = ang_err_rad * RAD_TO_MAS
        angular_errors_mas.append(ang_err_mas)

        # Closure error from candidate
        closure_errors_rad.append(cand_c.get("closure_rad", 0.0))

        # Matrix difference (if both have non-null matrices)
        if ref_c.get("matrix") is not None and cand_c.get("matrix") is not None:
            ref_m = np.array(ref_c["matrix"])
            cand_m = np.array(cand_c["matrix"])
            frob = np.linalg.norm(ref_m - cand_m)
            matrix_frob_norms.append(frob)

        worst_cases.append({
            "jd_tt": cand_c["jd_tt"],
            "angular_error_mas": ang_err_mas,
        })

    angular_errors_mas = np.array(angular_errors_mas)
    closure_errors_rad = np.array(closure_errors_rad)

    # Sort worst cases
    worst_cases.sort(key=lambda x: x["angular_error_mas"], reverse=True)

    def percentiles(arr):
        if len(arr) == 0:
            return {"p50": None, "p90": None, "p95": None, "p99": None, "max": None, "min": None, "mean": None, "rms": None}
        return {
            "p50": float(np.percentile(arr, 50)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "max": float(np.max(arr)),
            "min": float(np.min(arr)),
            "mean": float(np.mean(arr)),
            "rms": float(np.sqrt(np.mean(arr**2))),
        }

    n_requested = len(ref_cases)
    count_valid = len(angular_errors_mas)
    error_count = n_requested - count_valid
    return {
        "reference": ref_label,
        "candidate": cand_label,
        "count_requested": n_requested,
        "count_valid": count_valid,
        "error_count": error_count,
        "angular_error_mas": percentiles(angular_errors_mas),
        "closure_error_rad": percentiles(closure_errors_rad),
        "matrix_frobenius": percentiles(np.array(matrix_frob_norms)) if matrix_frob_norms else None,
        "nan_count": nan_count,
        "inf_count": inf_count,
        "worst_cases": worst_cases[:10],
    }


def compute_gmst_accuracy(ref_cases, cand_cases, ref_label, cand_label):
    """Compare GMST/ERA values between reference and candidate."""
    mismatch = _check_case_counts(ref_cases, cand_cases, ref_label, cand_label)
    if mismatch:
        return mismatch
    gmst_errors_rad = []
    era_errors_rad = []

    _TWO_PI = 2.0 * math.pi

    for ref_c, cand_c in zip(ref_cases, cand_cases):
        if "gmst_rad" in ref_c and "gmst_rad" in cand_c:
            diff = abs(ref_c["gmst_rad"] - cand_c["gmst_rad"])
            gmst_errors_rad.append(min(diff, _TWO_PI - diff))

        if "era_rad" in ref_c and "era_rad" in cand_c:
            diff = abs(ref_c["era_rad"] - cand_c["era_rad"])
            era_errors_rad.append(min(diff, _TWO_PI - diff))

    def percentiles(arr):
        if len(arr) == 0:
            return {"p50": None, "p90": None, "p99": None, "max": None}
        a = np.array(arr)
        return {
            "p50": float(np.percentile(a, 50)),
            "p90": float(np.percentile(a, 90)),
            "p99": float(np.percentile(a, 99)),
            "max": float(np.max(a)),
            "mean": float(np.mean(a)),
            "rms": float(np.sqrt(np.mean(a**2))),
        }

    return {
        "reference": ref_label,
        "candidate": cand_label,
        "gmst_error_rad": percentiles(gmst_errors_rad),
        "gmst_error_arcsec": percentiles([e * RAD_TO_ARCSEC for e in gmst_errors_rad]),
        "era_error_rad": percentiles(era_errors_rad),
    }


def angular_separation(ra1, dec1, ra2, dec2):
    """Compute angular separation between two (RA, Dec) pairs in radians.

    Uses the numerically stable atan2(|sin|, cos) form (Vincenty) so the
    metric does not saturate at the acos floor (~1 mas regime). Audit fix F5.
    """
    sdec1, cdec1 = math.sin(dec1), math.cos(dec1)
    sdec2, cdec2 = math.sin(dec2), math.cos(dec2)
    dra = ra2 - ra1
    sdra, cdra = math.sin(dra), math.cos(dra)
    # Numerator: sqrt of |cross|^2 in spherical (Vincenty special-case for
    # the unit sphere).
    num_a = cdec2 * sdra
    num_b = cdec1 * sdec2 - sdec1 * cdec2 * cdra
    num = math.hypot(num_a, num_b)
    den = sdec1 * sdec2 + cdec1 * cdec2 * cdra
    return math.atan2(num, den)


def compute_angular_accuracy(ref_cases, cand_cases, ref_label, cand_label,
                             ra_key="ra_rad", dec_key="dec_rad",
                             extra_keys=None):
    """Compare RA/Dec angular positions between reference and candidate.

    Works for equ_ecl (lon/lat), solar/lunar position, etc.
    extra_keys: optional list of keys to also compute absolute difference stats.
    """
    mismatch = _check_case_counts(ref_cases, cand_cases, ref_label, cand_label)
    if mismatch:
        return mismatch
    sep_errors_arcsec = []
    signed_ra_errors = []
    signed_dec_errors = []
    extra_diffs = {k: [] for k in (extra_keys or [])}
    nan_count = 0

    for ref_c, cand_c in zip(ref_cases, cand_cases):
        r_ra = ref_c.get(ra_key)
        r_dec = ref_c.get(dec_key)
        c_ra = cand_c.get(ra_key)
        c_dec = cand_c.get(dec_key)

        if any(v is None for v in [r_ra, r_dec, c_ra, c_dec]):
            nan_count += 1
            continue
        if any(math.isnan(v) or math.isinf(v) for v in [c_ra, c_dec]):
            nan_count += 1
            continue

        sep = angular_separation(r_ra, r_dec, c_ra, c_dec)
        sep_errors_arcsec.append(sep * RAD_TO_ARCSEC)

        # Signed errors for bias detection
        dra = c_ra - r_ra
        # wrap RA difference to [-π, π]
        if dra > math.pi:
            dra -= 2 * math.pi
        elif dra < -math.pi:
            dra += 2 * math.pi
        signed_ra_errors.append(dra * RAD_TO_ARCSEC)
        signed_dec_errors.append((c_dec - r_dec) * RAD_TO_ARCSEC)

        for k in (extra_keys or []):
            rv = ref_c.get(k)
            cv = cand_c.get(k)
            if rv is not None and cv is not None:
                extra_diffs[k].append(cv - rv)

    def percentiles(arr):
        if len(arr) == 0:
            return {"p50": None, "p90": None, "p99": None, "max": None, "mean": None, "rms": None}
        a = np.array(arr)
        return {
            "p50": float(np.percentile(np.abs(a), 50)),
            "p90": float(np.percentile(np.abs(a), 90)),
            "p99": float(np.percentile(np.abs(a), 99)),
            "max": float(np.max(np.abs(a))),
            "mean": float(np.mean(a)),
            "rms": float(np.sqrt(np.mean(a**2))),
        }

    result = {
        "reference": ref_label,
        "candidate": cand_label,
        "angular_sep_arcsec": percentiles(sep_errors_arcsec),
        "signed_ra_error_arcsec": percentiles(signed_ra_errors),
        "signed_dec_error_arcsec": percentiles(signed_dec_errors),
        "nan_count": nan_count,
    }

    for k in (extra_keys or []):
        result[f"{k}_diff"] = percentiles(extra_diffs[k])

    return result


def compute_kepler_accuracy(ref_cases, cand_cases, ref_label, cand_label):
    """Compare Kepler solver results: E and ν residuals, plus self-consistency."""
    mismatch = _check_case_counts(ref_cases, cand_cases, ref_label, cand_label)
    if mismatch:
        return mismatch

    def wrap_to_pi(angle_rad: float) -> float:
        """Wrap an angle to [-pi, pi] in constant time."""
        return ((angle_rad + math.pi) % (2.0 * math.pi)) - math.pi

    E_errors_rad = []
    nu_errors_rad = []
    consistency_errors = []
    nan_count = 0

    for ref_c, cand_c in zip(ref_cases, cand_cases):
        r_E = ref_c.get("E_rad")
        c_E = cand_c.get("E_rad")
        r_nu = ref_c.get("nu_rad")
        c_nu = cand_c.get("nu_rad")

        if any(v is None for v in [r_E, c_E, r_nu, c_nu]):
            nan_count += 1
            continue
        if any(not math.isfinite(v) for v in [r_E, c_E, r_nu, c_nu]):
            nan_count += 1
            continue

        # Skip cases where the reference itself has poor self-consistency
        # (e.g., Newton-Raphson diverged for extreme eccentricity).
        r_residual = ref_c.get("residual_rad", 0.0)
        if not math.isfinite(r_residual) or abs(r_residual) > 1e-10:
            nan_count += 1
            continue

        # Wrap differences to [-π, π] since E and ν are defined mod 2π.
        E_errors_rad.append(wrap_to_pi(c_E - r_E))

        nu_errors_rad.append(wrap_to_pi(c_nu - r_nu))

        # Self-consistency: M = E - e*sin(E) should hold
        M_input = cand_c.get("M_rad", ref_c.get("M_rad", 0.0))
        e = cand_c.get("e", ref_c.get("e", 0.0))
        M_recon = c_E - e * math.sin(c_E)
        # Wrap to [0, 2π)
        M_input_w = M_input % (2 * math.pi)
        M_recon_w = M_recon % (2 * math.pi)
        consistency = abs(M_input_w - M_recon_w)
        if consistency > math.pi:
            consistency = 2 * math.pi - consistency
        consistency_errors.append(consistency)

    def percentiles(arr):
        if len(arr) == 0:
            return {"p50": None, "p90": None, "p99": None, "max": None, "mean": None, "rms": None}
        a = np.array(arr)
        return {
            "p50": float(np.percentile(np.abs(a), 50)),
            "p90": float(np.percentile(np.abs(a), 90)),
            "p99": float(np.percentile(np.abs(a), 99)),
            "max": float(np.max(np.abs(a))),
            "mean": float(np.mean(a)),
            "rms": float(np.sqrt(np.mean(a**2))),
        }

    return {
        "reference": ref_label,
        "candidate": cand_label,
        "E_error_rad": percentiles(E_errors_rad),
        "nu_error_rad": percentiles(nu_errors_rad),
        "consistency_error_rad": percentiles(consistency_errors),
        "nan_count": nan_count,
    }


# ---------------------------------------------------------------------------
# Alignment checklist
# ---------------------------------------------------------------------------

def alignment_checklist(
    experiment: str,
    mode: str = "common_denominator",
    candidate_library: str = "",
    candidate_label: str = "",
):
    """Return the alignment checklist for this run."""
    base = {
        "units": {
            "angles": "radians (internal), mas for error reporting",
            "distances": "meters",
            "float_type": "f64",
        },
        "time_input": "JD (Julian Date), TT scale for precession/nutation, UT1 for sidereal time",
        "time_scales": "TT for BPN matrix; UT1≈TT-69.184s simplified",
        "leap_seconds": "not applicable (JD input, no UTC conversion in this experiment)",
        "earth_orientation": {
            "ut1_minus_utc": "not used (JD(TT) input)",
            "polar_motion_xp_yp": "zero (not applied)",
            "eop_mode": "disabled",
        },
        "geodesy": "not applicable (direction-only experiment)",
        "refraction": "disabled",
        "ephemeris_source": "not applicable (no aberration/parallax)",
        "library_notes": {
            "astropy": (
                "The 'astropy' adapter uses public Astropy Time and SkyCoord APIs. "
                "Astropy may use ERFA internally, but this adapter no longer calls "
                "ERFA/pyerfa kernels directly."
            ),
        },
    }

    if experiment == "frame_rotation_bpn":
        base["models"] = {
            "erfa": "IAU 2006/2000A bias-precession-nutation (eraPnm06a)",
            "siderust": "IERS 2003 frame bias + IAU 2006 precession + IAU 2006/2000A nutation (frame_rotation provider)",
            "astropy": "Public SkyCoord GCRS→TETE transform (equinox-based Astropy frame graph)",
            "libnova": "Meeus precession (ζ,z,θ Equ 20.3) + IAU 1980 nutation (63-term Table 21A), applied as RA/Dec corrections (no BPN matrix)",
        }
        base["model_parity_class"] = "model-mismatch"
        base["accuracy_interpretation"] = "agreement with ERFA baseline (Astropy high-level transform, no direct ERFA call in adapter)"
        base["mode"] = mode
        base["note"] = (
            "ERFA is the raw SOFA-style BPN matrix reference. Astropy is measured "
            "through its public GCRS/TETE transform graph, whose equinox-based orientation "
            "matches the SOFA pnm06a BPN matrix for direction-only inputs. "
            "Siderust now uses the same IAU 2006/2000A decomposition. "
            "libnova uses Meeus precession + IAU 1980 nutation via coordinate-level API (no rotation matrix). "
            "Differences measure the model gap, not implementation bugs."
        )
    elif experiment == "gmst_era":
        base["models"] = {
            "erfa": "GMST=IAU2006 (eraGmst06), ERA=IAU2000 (eraEra00)",
            "siderust": "GST polynomial (IAU 2006 coefficients), ERA from IERS definition",
            "astropy": "Public Time.sidereal_time and Time.earth_rotation_angle APIs",
            "libnova": "GMST=Meeus Formula 11.4, GAST=MST+nutation correction (no ERA)",
        }
        base["model_parity_class"] = "model-mismatch"
        base["accuracy_interpretation"] = "agreement with ERFA baseline (libnova uses Meeus, no ERA)"
        base["mode"] = mode

    elif experiment == "equ_ecl":
        base["models"] = {
            "erfa": "IAU 2006 obliquity-based transform (eraEqec06 / eraEceq06)",
            "siderust": "IAU 2006 ecliptic-of-date via precession matrix + mean obliquity",
            "astropy": "Public SkyCoord ICRS→BarycentricMeanEcliptic transform",
            "libnova": "Meeus obliquity (Eq 22.2) via ln_get_ecl_from_equ / ln_get_equ_from_ecl",
        }
        base["model_parity_class"] = "model-mismatch"
        base["accuracy_interpretation"] = "agreement with ERFA baseline (libnova Meeus obliquity differs)"
        base["note"] = (
            "Astropy is measured through its public BarycentricMeanEcliptic orientation, "
            "which matches SOFA's mean ecliptic-of-date rotation for direction-only inputs. "
            "Siderust uses an explicit IAU 2006 equatorial/ecliptic-of-date transform path. "
            "libnova uses Meeus obliquity polynomial — expect ~arcsec-level differences."
        )

    elif experiment == "equ_horizontal":
        base["models"] = {
            "erfa": "Spherical trig via eraHd2ae / eraAe2hd; GAST via eraGst06a; no refraction",
            "siderust": "Spherical trig matching ERFA formulas; GAST IAU 2006 via siderust astro path",
            "astropy": "Public SkyCoord TETE→AltAz transform with pressure=0",
            "libnova": "ln_get_hrz_from_equ / ln_get_equ_from_hrz; convention fix: az_erfa = (360 - az_ln + 180) % 360",
        }
        base["model_parity_class"] = "model-mismatch"
        base["accuracy_interpretation"] = "accuracy vs ERFA reference (Astropy high-level AltAz path, no direct ERFA trig call)"
        base["note"] = (
            "Azimuth convention: ERFA 0°=North CW; libnova 0°=South. "
            "Astropy is measured through public TETE/AltAz transforms with atmospheric "
            "refraction disabled."
        )
        base["refraction"] = "disabled"

    elif strip_apparent_suffix(experiment) == "solar_position":
        _apparent = is_apparent_experiment(experiment)
        base["models"] = {
            "jpl_horizons": (
                "JPL Horizons OBSERVER astrometric geocentric RA/Dec (DE441, geocenter, TT)"
                if _apparent else
                "JPL Horizons geometric VECTORS (DE441, ICRF, VEC_CORR=NONE, Earth geocenter, TT)"
            ),
            "erfa": "VSOP87 via eraEpv00: heliocentric Earth → geocentric Sun (negate); BCRS equatorial output",
            "siderust": "Geometric heliocentric-ecliptic center transformed to geocentric ICRS (no aberration)",
            "astropy": (
                "Astropy public solar_system_ephemeris('builtin') + "
                "get_body_barycentric('sun'/'earth')"
            ),
            "libnova": (
                "VSOP87 geometric (ln_get_solar_geo_coords; heliocentric + geocentric "
                "rectangular vectors; no nutation/aberration)"
                if not _apparent else
                "VSOP87 via ln_get_solar_equ_coords (applies nutation; apparent-style)"
            ),
            "anise": "SPK translation SUN_J2000 → EARTH_J2000 (DE440 ephemeris, geometric state vector)",
        }
        base["model_parity_class"] = "external-reference"
        base["accuracy_interpretation"] = (
            "agreement with JPL Horizons OBSERVER astrometric reference"
            if _apparent else
            "agreement with JPL Horizons geometric VECTORS reference (no aberration / nutation)"
        )
        base["ephemeris_source"] = "JPL Horizons (DE441) for reference; VSOP87/SPK for candidates"
        base["reference_mode"] = (
            "OBSERVER astrometric geocentric RA/Dec" if _apparent
            else "VECTORS geometric ICRF state (X/Y/Z)"
        )
        base["reference_frame"] = "ICRF"
        base["reference_center"] = "Earth geocenter (500@399)"
        base["reference_time_scale"] = "TT"
        base["note"] = (
            "Apparent lane — diagnostic; ranks candidates that apply aberration/nutation. "
            "Same observable (astrometric RA/Dec) for all candidates; libnova VSOP87+nutation matches the lane."
            if _apparent else
            "Public geometric lane — JPL VECTORS (no aberration, no light-time, no nutation). "
            "Ranked as best-available model vs JPL reference: same observable, different physical models "
            "(libnova VSOP87 geometric, siderust DE441/DE440/VSOP87 best-available, ANISE SPK)."
        )

    elif strip_apparent_suffix(experiment) == "lunar_position":
        _apparent = is_apparent_experiment(experiment)
        base["models"] = {
            "jpl_horizons": (
                "JPL Horizons OBSERVER astrometric geocentric RA/Dec (DE441, geocenter, TT)"
                if _apparent else
                "JPL Horizons geometric VECTORS (DE441, ICRF, VEC_CORR=NONE, Earth geocenter, TT)"
            ),
            "erfa": "Simplified Meeus Ch.47 (major terms only, ~10' accuracy)",
            "siderust": "Simplified Meeus Ch.47 (major terms only), centralized in siderust astro module",
            "astropy": "Simplified Meeus Ch.47 (same algorithm as ERFA adapter)",
            "libnova": (
                "ELP 2000-82B geometric (ln_get_lunar_geo_posn + J2000 obliquity rotation; "
                "no nutation/aberration)"
                if not _apparent else
                "ELP 2000-82B via ln_get_lunar_equ_coords (applies nutation; apparent-style)"
            ),
            "anise": "SPK translation MOON_J2000 → EARTH_J2000 (DE440 ephemeris, geometric state vector)",
        }
        base["model_parity_class"] = "external-reference"
        base["accuracy_interpretation"] = (
            "agreement with JPL Horizons OBSERVER astrometric reference"
            if _apparent else
            "agreement with JPL Horizons geometric VECTORS reference (no aberration / nutation)"
        )
        base["reference_mode"] = (
            "OBSERVER astrometric geocentric RA/Dec" if _apparent
            else "VECTORS geometric ICRF state (X/Y/Z)"
        )
        base["reference_frame"] = "ICRF"
        base["reference_center"] = "Earth geocenter (500@399)"
        base["reference_time_scale"] = "TT"
        base["note"] = (
            "Apparent lane — diagnostic; ranks candidates that apply aberration/nutation."
            if _apparent else
            "Public geometric lane — JPL VECTORS (no aberration, no light-time, no nutation). "
            "Ranked as best-available model vs JPL reference: libnova uses ELP 2000-82B geometric, "
            "ERFA/Astropy use the simplified Meeus Ch.47 fallback (ERFA's eraMoon98 path is best-available "
            "when enabled), Siderust uses its centralised Meeus implementation."
        )
        base["ephemeris_source"] = "JPL Horizons (DE441) for reference; Meeus/ELP 2000/DE440 for candidates"

    elif experiment in PLANET_POSITION_EXPERIMENTS:
        body = PLANET_POSITION_EXPERIMENTS[experiment]["body"]
        _apparent = is_apparent_experiment(experiment)
        base["models"] = {
            "jpl_horizons": (
                f"JPL Horizons OBSERVER astrometric RA/Dec of {body} (DE441, geocenter, TT)"
                if _apparent else
                f"JPL Horizons geometric VECTORS of {body} (DE441, ICRF, VEC_CORR=NONE, Earth geocenter, TT)"
            ),
            "erfa": (
                f"ERFA eraPlan94 heliocentric {body} analytic state minus eraEpv00 Earth state "
                "(geometric, J2000 equatorial)"
            ),
            "siderust": (
                f"VSOP87A heliocentric {body} state shifted to geocenter, then rotated to ICRS "
                "(geometric, no aberration)"
            ),
            "astropy": (
                f"Astropy public solar_system_ephemeris('builtin') + "
                f"get_body_barycentric('{body.lower()}') - get_body_barycentric('earth') "
                "(geometric, J2000 equatorial)"
            ),
            "libnova": (
                f"VSOP87 via ln_get_{body.lower()}_rect_helio - ln_get_earth_rect_helio "
                "(geometric rectangular, no nutation/aberration)"
                if not _apparent else
                f"VSOP87 via ln_get_{body.lower()}_equ_coords / "
                f"ln_get_{body.lower()}_earth_dist (apparent-style)"
            ),
            "anise": (
                f"SPK translation {body.upper()}_J2000 -> EARTH_J2000 "
                "(DE440 ephemeris, geometric state vector)"
            ),
        }
        base["model_parity_class"] = "external-reference"
        base["accuracy_interpretation"] = (
            f"agreement with JPL Horizons OBSERVER astrometric reference for {body}"
            if _apparent else
            f"agreement with JPL Horizons geometric VECTORS reference for {body} "
            "(no aberration / nutation)"
        )
        base["reference_mode"] = (
            "OBSERVER astrometric geocentric RA/Dec" if _apparent
            else "VECTORS geometric ICRF state (X/Y/Z)"
        )
        base["reference_frame"] = "ICRF"
        base["reference_center"] = "Earth geocenter (500@399)"
        base["reference_time_scale"] = "TT"
        base["ephemeris_source"] = "JPL Horizons (DE441) for reference; VSOP87/plan94/SPK for candidates"
        base["note"] = (
            f"Apparent diagnostic lane for {body} — ranks candidates that apply aberration/nutation."
            if _apparent else
            f"Public geometric lane for {body} — JPL VECTORS (no aberration, no light-time, no nutation). "
            "Ranked as best-available model vs JPL reference: libnova VSOP87 geometric path, "
            "ERFA/Astropy use eraPlan94 analytic, ANISE uses DE440 SPK when available."
        )

    elif experiment == "kepler_solver":
        base["models"] = {
            "erfa": "Newton-Raphson iteration (100 iters, tol 1e-15)",
            "siderust": "solve_keplers_equation (internal algorithm)",
            "astropy": "Newton-Raphson iteration in Python (100 iters, tol 1e-15)",
            "libnova": "Sinnott bisection via ln_solve_kepler (internal convergence ~1e-6 deg)",
        }
        base["model_parity_class"] = "model-parity"
        base["accuracy_interpretation"] = "accuracy vs ERFA reference (same equation, different solvers)"
        base["note"] = (
            "Kepler's equation M = E - e*sin(E) is solved for E given (M, e). "
            "Self-consistency M_reconstructed = E - e*sin(E) is the primary metric. "
            "libnova uses a bisection method with lower convergence tolerance."
        )

    elif experiment == "frame_bias":
        base["models"] = {
            "erfa": "IAU 2006 frame bias matrix component from eraBp06",
            "siderust": "IERS 2003 frame bias via frame rotation provider (ICRS → EquatorialMeanJ2000)",
            "astropy": "Unsupported in Astropy adapter: no public high-level isolated frame-bias API",
            "libnova": "Not available (no frame bias concept in libnova)",
        }
        base["model_parity_class"] = "model-parity"
        base["accuracy_interpretation"] = "accuracy vs ERFA reference (IAU frame bias is a fixed rotation)"
        base["note"] = (
            "Frame bias is a small (~17 mas) time-independent rotation between ICRS and mean J2000. "
            "Astropy and libnova have no public equivalent route in this adapter — their results are skipped."
        )

    elif experiment == "precession":
        base["models"] = {
            "erfa": "IAU 2006 pure precession matrix from eraBp06 → rp",
            "siderust": "IAU 2006 precession via frame rotation provider (EquatorialMeanJ2000 → EquatorialMeanOfDate)",
            "astropy": "Unsupported in Astropy adapter: no public high-level pure-precession matrix API",
            "libnova": "Meeus precession (ζ,z,θ Equ 20.3) via ln_get_equ_prec2",
        }
        base["model_parity_class"] = "model-mismatch"
        base["accuracy_interpretation"] = "agreement with ERFA baseline (libnova uses Meeus model)"
        base["note"] = (
            "ERFA and Siderust use IAU 2006 precession paths. "
            "The Astropy adapter does not expose the isolated component without direct low-level kernels. "
            "libnova uses Meeus precession formulae — expect arcsec-level differences."
        )

    elif experiment == "nutation":
        base["models"] = {
            "erfa": "IAU 2000A nutation (1365 terms) via eraNum06a",
            "siderust": "IAU 2006/2000A nutation via frame rotation provider",
            "astropy": "Unsupported in Astropy adapter: no public high-level isolated nutation matrix API",
            "libnova": "IAU 1980 nutation (69 terms) via ln_get_equ_nut / ln_nutation",
        }
        base["model_parity_class"] = "model-mismatch"
        base["accuracy_interpretation"] = "agreement with ERFA baseline (libnova uses the older IAU 1980 model)"
        base["note"] = (
            "ERFA and Siderust use IAU 2006/2000A nutation paths. "
            "The Astropy adapter does not expose the isolated component without direct low-level kernels. "
            "IAU 1980 (libnova) has 69 terms and will differ by tens of mas."
        )

    elif experiment == "icrs_ecl_j2000":
        base["models"] = {
            "erfa": "IAU 2006 ecliptic rotation at J2000 epoch via eraEcm06",
            "siderust": "ICRS → EclipticMeanJ2000 via frame rotation (mean obliquity at J2000)",
            "astropy": "Unsupported in Astropy adapter: no public high-level J2000 ecliptic matrix API",
            "libnova": "Meeus obliquity (Eq 22.2) applied at J2000 epoch",
            "anise": "J2000 ↔ ECLIPJ2000 built-in orientation rotation (constant obliquity)",
        }
        base["model_parity_class"] = "model-parity"
        base["accuracy_interpretation"] = "accuracy vs ERFA reference (time-independent obliquity)"
        base["note"] = (
            "Time-independent rotation by the mean obliquity at J2000. "
            "All IAU-based libraries should agree to µas level. "
            "libnova uses Meeus obliquity which is close but not identical."
        )

    elif experiment == "icrs_ecl_tod":
        base["models"] = {
            "erfa": "IAU 2006 equatorial → ecliptic of date via eraEqec06",
            "siderust": "ICRS → ecliptic of date via DirectionAstroExt::to_ecliptic_of_date",
            "astropy": "Public SkyCoord ICRS→BarycentricMeanEcliptic transform",
            "libnova": "Meeus obliquity (Eq 22.2) via ln_get_ecl_from_equ",
        }
        base["model_parity_class"] = "model-mismatch"
        base["accuracy_interpretation"] = "agreement with ERFA baseline (libnova Meeus obliquity differs)"
        base["note"] = (
            "Similar to equ_ecl but explicitly identified as ICRS → ecliptic-of-date transform. "
            "Astropy is measured through its public BarycentricMeanEcliptic orientation. "
            "ERFA and Siderust use explicit IAU 2006 transform paths; libnova uses Meeus."
        )

    elif experiment == "horiz_to_equ":
        base["models"] = {
            "erfa": "Spherical trig via eraAe2hd; GAST via eraGst06a; no refraction",
            "siderust": "Spherical trig via FromHorizontal::to_equatorial; GAST IAU 2006",
            "astropy": "Public SkyCoord AltAz→TETE transform with pressure=0",
            "libnova": "ln_get_equ_from_hrz; convention fix: az = (input_az - 180) % 360",
        }
        base["model_parity_class"] = "model-mismatch"
        base["accuracy_interpretation"] = "accuracy vs ERFA reference (Astropy high-level AltAz path, no direct ERFA trig call)"
        base["note"] = (
            "Inverse of equ_horizontal. Astropy is measured through public AltAz/TETE transforms. "
            "Azimuth convention: ERFA 0°=North CW; libnova 0°=South. "
            "No atmospheric refraction applied."
        )
        base["refraction"] = "disabled"

    # 13 new matrix experiments — alignment checklists
    elif experiment in ("inv_frame_bias",):
        base["models"] = {
            "erfa": "Transpose of IAU 2006 frame bias matrix (eraBp06 → rb^T)",
            "siderust": "EquatorialMeanJ2000 → ICRS via frame rotation provider inverse",
            "astropy": "Unsupported in Astropy adapter: no public high-level isolated inverse frame-bias API",
            "libnova": "Not available (no frame bias concept)",
        }
        base["model_parity_class"] = "model-parity"

    elif experiment in ("inv_precession",):
        base["models"] = {
            "erfa": "Transpose of pure IAU 2006 precession matrix (eraBp06 → rp^T)",
            "siderust": "EquatorialMeanOfDate → EquatorialMeanJ2000 via frame rotation inverse",
            "astropy": "Unsupported in Astropy adapter: no public high-level isolated inverse-precession API",
            "libnova": "Meeus inverse precession via ln_get_equ_prec2(date→J2000)",
        }
        base["model_parity_class"] = "model-mismatch"

    elif experiment in ("inv_nutation",):
        base["models"] = {
            "erfa": "Transpose of IAU 2000A nutation matrix (eraNum06a → rn^T)",
            "siderust": "EquatorialTrueOfDate → EquatorialMeanOfDate via frame rotation inverse",
            "astropy": "Unsupported in Astropy adapter: no public high-level isolated inverse-nutation API",
            "libnova": "Approximate inverse via ΔRA/ΔDec subtraction (IAU 1980)",
        }
        base["model_parity_class"] = "model-mismatch"

    elif experiment in ("inv_bpn",):
        base["models"] = {
            "erfa": "Transpose of IAU 2006 BPN matrix (eraPnm06a → rnpb^T)",
            "siderust": "EquatorialTrueOfDate → ICRS via frame rotation inverse",
            "astropy": "Public SkyCoord TETE→GCRS transform (equinox-based Astropy frame graph)",
            "libnova": "Not available (no ICRS/frame bias concept)",
        }
        base["model_parity_class"] = "model-mismatch"

    elif experiment in ("inv_icrs_ecl_j2000",):
        base["models"] = {
            "erfa": "Transpose of eraEcm06(J2000) matrix",
            "siderust": "EclipticMeanJ2000 → ICRS via TransformFrame inverse",
            "astropy": "Unsupported in Astropy adapter: no public high-level J2000 ecliptic inverse matrix API",
            "libnova": "ln_get_equ_from_ecl at J2000 (Meeus obliquity)",
            "anise": "Transpose of built-in J2000 ↔ ECLIPJ2000 rotation",
        }
        base["model_parity_class"] = "model-parity"

    elif experiment in ("obliquity", "inv_obliquity"):
        base["models"] = {
            "erfa": "Pure Rx(±ε₀) rotation using eraObl06(J2000)",
            "siderust": "EclipticMeanJ2000 ↔ EquatorialMeanJ2000 via TransformFrame",
            "astropy": "Unsupported in Astropy adapter: no public high-level isolated obliquity component API",
            "libnova": "ln_get_equ_from_ecl / ln_get_ecl_from_equ at J2000 (Meeus obliquity)",
            "anise": "Built-in J2000 ↔ ECLIPJ2000 obliquity rotation",
        }
        base["model_parity_class"] = "model-parity"

    elif experiment in ("bias_precession", "inv_bias_precession"):
        base["models"] = {
            "erfa": "IAU 2006 bias+precession product (eraBp06 → rbp / rbp^T)",
            "siderust": "ICRS ↔ EquatorialMeanOfDate via composed frame rotation",
            "astropy": "Unsupported in Astropy adapter: no public high-level isolated bias+precession API",
            "libnova": "Not available (no frame bias concept)",
        }
        base["model_parity_class"] = "model-mismatch"

    elif experiment in ("precession_nutation", "inv_precession_nutation"):
        base["models"] = {
            "erfa": "N×P composed matrix (eraNum06a × pure eraBp06-rp / transpose)",
            "siderust": "EquatorialMeanJ2000 ↔ EquatorialTrueOfDate via frame rotation",
            "astropy": "Unsupported in Astropy adapter: no public high-level isolated precession+nutation API",
            "libnova": "ln_get_equ_prec + ln_get_equ_nut sequenced / approximate inverse",
        }
        base["model_parity_class"] = "model-mismatch"

    elif experiment in ("inv_icrs_ecl_tod",):
        base["models"] = {
            "erfa": "Transpose of eraEcm06(date) matrix",
            "siderust": "EclipticTrueOfDate → ICRS via FromEclipticTrueOfDate::to_icrs",
            "astropy": "Unsupported in Astropy adapter: no public high-level ecliptic-of-date inverse matrix API",
            "libnova": "ln_get_equ_from_ecl(date) + ln_get_equ_prec2(date→J2000)",
        }
        base["model_parity_class"] = "model-mismatch"

    elif experiment in ("inv_equ_ecl",):
        base["models"] = {
            "erfa": "RBP × ECM06^T composed matrix",
            "siderust": "EclipticTrueOfDate → EquatorialMeanOfDate via FromEclipticTrueOfDate",
            "astropy": "Unsupported in Astropy adapter: no public high-level inverse equatorial/ecliptic component API",
            "libnova": "ln_get_equ_from_ecl at date (mean-of-date output)",
        }
        base["model_parity_class"] = "model-mismatch"

    elif experiment in PLANET_BARYCENTER_POSITION_EXPERIMENTS:
        base["models"] = {
            "siderust": (
                "When SIDERUST_PLANET_MODEL=de440_barycenter: JPL DE440 embedded SPK via "
                "De440Ephemeris::try_major_planet_geocentric(SystemBarycenter); geocentric planet system barycenter. "
                "When SIDERUST_PLANET_MODEL=vsop87 (default): VSOP87 geocentric planet-center used as best-available "
                "proxy for system barycenter (parity: analytic)."
            ),
            "astropy": "JPL DE440/DE441 via get_body_barycentric(body) − get_body_barycentric('earth'); geocentric planet system barycenter",
            "anise": "JPL DE440 via translate(BODY_BARYCENTER_J2000, EARTH_J2000); geocentric planet system barycenter",
            "erfa": "Not available (eraPlan94 gives heliocentric physical center; no system-barycenter output)",
            "libnova": (
                "VSOP87 heliocentric minus Earth heliocentric (geocentric, planet center); "
                "used as best-available proxy for system barycenter (parity: analytic)."
            ),
        }
        base["model_parity_class"] = "same-family-jpl"
        base["accuracy_interpretation"] = (
            "JPL-backed candidates (siderust DE440, astropy, anise) use JPL DE440 SPK for planet system barycenter "
            "positions, compared against the Horizons DE441 reference: same JPL family, different kernel version "
            "(same-family-jpl), so errors reflect the DE440↔DE441 delta plus floating-point / interpolation differences. "
            "Analytic candidates (siderust VSOP87, libnova) use VSOP87 geocentric planet-center as a best-available "
            "proxy; their errors include both the model residual and the small planet-center vs. system-barycenter offset."
        )

    if "models" in base:
        base["models"].setdefault("anise", "Not available in ANISE adapter for this experiment")

    # ── Per-candidate parity ──────────────────────────────────────────────
    # Maps (experiment, library) → parity class relative to the reference.
    # "reference"       = this IS the reference library
    # "model-parity"    = same underlying model as reference
    # "model-mismatch"  = different model from reference
    # "external-reference" = reference is external (JPL Horizons)
    _CANDIDATE_PARITY: dict[str, dict[str, str]] = {
        "frame_rotation_bpn": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "gmst_era": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "equ_ecl": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "equ_horizontal": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "solar_position": {
            "jpl_horizons": "reference",
            "erfa": "geometric", "astropy": "geometric",
            "siderust": "geometric", "anise": "geometric",
            "libnova": "apparent",
        },
        "lunar_position": {
            "jpl_horizons": "reference",
            "erfa": "geometric", "astropy": "geometric",
            "siderust": "geometric", "anise": "geometric",
            "libnova": "apparent",
        },
        "kepler_solver": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-parity",
        },
        "frame_bias": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "precession": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "nutation": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "icrs_ecl_j2000": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
            "anise": "model-parity",
        },
        "icrs_ecl_tod": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "horiz_to_equ": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        # Inverse/composed experiments inherit from parent
        "inv_frame_bias": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "inv_precession": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "inv_nutation": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "inv_bpn": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "inv_icrs_ecl_j2000": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
            "anise": "model-parity",
        },
        "obliquity": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
            "anise": "model-parity",
        },
        "inv_obliquity": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
            "anise": "model-parity",
        },
        "bias_precession": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "inv_bias_precession": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "precession_nutation": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "inv_precession_nutation": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "inv_icrs_ecl_tod": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
        "inv_equ_ecl": {
            "erfa": "reference", "astropy": "model-parity",
            "siderust": "model-parity", "libnova": "model-mismatch",
        },
    }

    for exp_name in PLANET_POSITION_EXPERIMENTS:
        _CANDIDATE_PARITY.setdefault(exp_name, {
            "jpl_horizons": "reference",
            "erfa": "geometric", "astropy": "geometric",
            "siderust": "geometric", "anise": "geometric",
            "libnova": "apparent",
        })

    # Apparent diagnostic ephemeris IDs mirror the public IDs but on the
    # apparent JPL OBSERVER lane.
    for _apparent_exp in APPARENT_EPHEMERIS_EXPERIMENTS:
        _CANDIDATE_PARITY.setdefault(_apparent_exp, {
            "jpl_horizons": "reference",
            "erfa": "geometric", "astropy": "geometric",
            "siderust": "geometric", "anise": "geometric",
            "libnova": "apparent",
        })

    if candidate_library:
        # For ephemeris experiments, parity is lane-dependent (libnova has a
        # geometric helio/geo path on the geometric lane, and an apparent path
        # on the apparent lane). Use the lane-aware table for those.
        eph_lane = ephemeris_lane_for(experiment)
        if eph_lane is not None and candidate_library != "jpl_horizons":
            base["candidate_parity"] = _ephemeris_candidate_parity(
                candidate_library, eph_lane, candidate_label=candidate_label or None
            )
        else:
            exp_parity = _CANDIDATE_PARITY.get(experiment, {})
            base["candidate_parity"] = exp_parity.get(candidate_library, base.get("model_parity_class", "unknown"))

    # Attach lane metadata for ephemeris experiments so rankability can
    # decide which candidate parities are admissible.
    lane = ephemeris_lane_for(experiment)
    if lane:
        base["lane"] = lane

    # Per audit M4: expose the experiment-level parity as `default_…` to
    # discourage UI code from showing it as authoritative when the
    # candidate-level `candidate_parity` field is present (and more accurate).
    if "model_parity_class" in base:
        base["default_model_parity_class"] = base["model_parity_class"]

    return base


# ---------------------------------------------------------------------------
# Run metadata
# ---------------------------------------------------------------------------

def get_git_sha(repo_path: Path) -> str:
    if not Path(repo_path).exists():
        return "unknown"
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip()[:12] if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_git_dirty(repo_path: Path) -> bool | None:
    if not Path(repo_path).exists():
        return None
    try:
        r = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=5,
        )
        return bool(r.stdout.strip()) if r.returncode == 0 else None
    except Exception:
        return None


# Submodule vendor locations.  The architectural rework relocated every
# upstream library under ``pipeline/adapters/<name>_adapter/vendor/<name>``
# (see .gitmodules).  Provenance capture MUST read the SHA from the real
# submodule path or the published manifest carries "unknown" SHAs — exactly
# the fairness defect the audit flags (issue #6).
SUBMODULE_PATHS: dict[str, Path] = {
    "siderust": LAB_ROOT / "pipeline/adapters/siderust_adapter/vendor/siderust",
    "anise": LAB_ROOT / "pipeline/adapters/anise_adapter/vendor/anise",
    "erfa": LAB_ROOT / "pipeline/adapters/erfa_adapter/vendor/erfa",
    "libnova": LAB_ROOT / "pipeline/adapters/libnova_adapter/vendor/libnova",
    "astropy": LAB_ROOT / "pipeline/adapters/astropy_adapter/vendor/astropy",
}


def _collect_git_shas() -> dict[str, str]:
    shas = {"lab": get_git_sha(LAB_ROOT)}
    for name, path in SUBMODULE_PATHS.items():
        shas[name] = get_git_sha(path)
    return shas


def _collect_git_dirty() -> dict[str, bool | None]:
    dirty = {"lab": get_git_dirty(LAB_ROOT)}
    for name, path in SUBMODULE_PATHS.items():
        dirty[name] = get_git_dirty(path)
    return dirty


def _cargo_lock_hash() -> dict[str, str]:
    """Hash each adapter Cargo.lock so the exact Rust dependency graph is pinned."""
    out: dict[str, str] = {}
    for name in ("siderust_adapter", "anise_adapter"):
        lock = LAB_ROOT / "pipeline/adapters" / name / "Cargo.lock"
        if lock.is_file():
            try:
                out[name] = hashlib.sha256(lock.read_bytes()).hexdigest()
            except Exception:
                pass
    return out


def run_metadata():
    """Collect environment metadata for reproducibility."""
    meta = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_shas": _collect_git_shas(),
        "git_dirty": _collect_git_dirty(),
        "cargo_lock_sha256": _cargo_lock_hash(),
        "git_branch": _get_git_branch(LAB_ROOT),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "os": f"{platform.system()} {platform.release()}",
        "platform_detail": platform.platform(),
        "toolchain": {
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
    }

    # Add rustc and cc versions if available
    for tool, cmd in [("rustc", ["rustc", "--version"]), ("cc", ["gcc", "--version"])]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                meta["toolchain"][tool] = r.stdout.strip().split("\n")[0]
        except Exception:
            pass

    # Try to get CPU frequency info
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    meta["cpu_model"] = line.split(":")[1].strip()
                    break
    except Exception:
        pass

    # Try to get pyerfa version
    try:
        import erfa
        meta["toolchain"]["pyerfa"] = erfa.__version__
    except Exception:
        pass

    # A3 / deep-audit M6: record adapter binary provenance (sha256, size, mtime).
    meta["adapter_binaries"] = _collect_adapter_binary_provenance()

    # A3: record library versions for C/Rust libraries (best-effort).
    meta["library_versions"] = _collect_library_versions()

    # A3: record ANISE SPK provenance if discoverable.
    spk_info = _discover_anise_spk_provenance()
    if spk_info:
        meta["anise_spk"] = spk_info
    siderust_planet_spks = _discover_siderust_planet_spk_provenance()
    if siderust_planet_spks:
        meta["siderust_planet_spks"] = siderust_planet_spks

    return meta


def _ensure_accuracy_counts(accuracy: dict, n_requested: int) -> dict:
    """Attach count_requested / count_valid / error_count when adapters omit them."""
    if accuracy.get("error"):
        accuracy.setdefault("count_requested", n_requested)
        accuracy.setdefault("count_valid", 0)
        accuracy.setdefault("error_count", n_requested)
        return accuracy
    if "count_requested" not in accuracy:
        nan = int(accuracy.get("nan_count") or 0)
        inf = int(accuracy.get("inf_count") or 0)
        count_valid = max(0, n_requested - nan - inf)
        accuracy["count_requested"] = n_requested
        accuracy["count_valid"] = count_valid
        accuracy["error_count"] = n_requested - count_valid
    return accuracy


def _accuracy_status_from_metrics(accuracy: dict | None) -> str:
    """Map accuracy metrics to row status (ok | partial | failed)."""
    if not accuracy:
        return "failed"
    if accuracy.get("error"):
        return "failed"
    n_req = int(accuracy.get("count_requested") or 0)
    n_valid = int(accuracy.get("count_valid") or 0)
    if n_req <= 0:
        return "failed"
    if n_valid <= 0:
        return "failed"
    if n_valid < n_req:
        return "partial"
    return "ok"


def _partial_accuracy_reason(accuracy: dict) -> str:
    return (
        f"incomplete accuracy coverage: {accuracy.get('count_valid')}/"
        f"{accuracy.get('count_requested')} valid cases "
        f"(nan={accuracy.get('nan_count', 0)}, inf={accuracy.get('inf_count', 0)})"
    )


def _validate_publish_latest(scope: dict, metadata: dict, *, perf_enabled: bool = True,
                             perf_rounds: int = 10, perf_scalar_n: int = 5000,
                             perf_batch_n: int = 100000, perf_batch_rounds: int = 5,
                             perf_warmup: int = 100) -> list[str]:
    """Return human-readable blockers for copying a run to latest_results/."""
    blockers: list[str] = []
    git_dirty = metadata.get("git_dirty") or {}
    if git_dirty.get("lab") is True:
        blockers.append("git_dirty.lab is true (working tree has uncommitted changes)")
    if scope.get("partial"):
        missing = scope.get("missing_requested_experiments") or []
        blockers.append(
            "run scope is partial"
            + (f" (missing: {', '.join(missing)})" if missing else "")
        )
    if perf_enabled:
        if perf_rounds < 10:
            blockers.append(f"perf_rounds {perf_rounds} < 10 (publication standard)")
        if perf_scalar_n < 5000:
            blockers.append(f"perf_scalar_n {perf_scalar_n} < 5000 (publication standard)")
        if perf_batch_n < 100000:
            blockers.append(f"perf_batch_n {perf_batch_n} < 100000 (publication standard)")
        if perf_batch_rounds < 5:
            blockers.append(f"perf_batch_rounds {perf_batch_rounds} < 5 (publication standard)")
        if perf_warmup < 100:
            blockers.append(f"perf_warmup {perf_warmup} < 100 (publication standard)")
    else:
        blockers.append("performance measurement is disabled")
    return blockers


def _publish_overrides_satisfy(
    blockers: list[str],
    *,
    allow_dirty: bool,
    allow_partial: bool,
) -> bool:
    """True when every blocker is explicitly overridden."""
    for msg in blockers:
        if "git_dirty" in msg and not allow_dirty:
            return False
        # Treat non-standard performance or disabled performance as "partial"
        # for publication gate override purposes.
        if ("partial" in msg.lower() or "perf" in msg.lower() or "performance" in msg.lower()) and not allow_partial:
            return False
    return True


def _mark_perf_block_invalid(block: dict, issues: list[str]) -> dict:
    out = dict(block)
    out["valid"] = False
    warnings = list(out.get("warnings") or [])
    for msg in issues:
        if msg and msg not in warnings:
            warnings.append(msg)
    out["warnings"] = warnings
    return out


def _perf_block_issues(block: dict | None, *, expected_n: int | None = None) -> list[str]:
    if not isinstance(block, dict):
        return []
    issues: list[str] = []
    if block.get("valid") is False:
        issues.append("performance workload marked invalid")
    if block.get("skipped"):
        issues.append(str(block.get("skip_reason") or "performance workload skipped"))
    status = block.get("status")
    if status in ("partial", "failed", "skipped"):
        issues.append(f"performance workload status={status}")
    count_requested = block.get("count_requested")
    if count_requested is None and expected_n is not None:
        count_requested = block.get("n_per_round") or block.get("n") or expected_n
    count_valid = block.get("count_valid")
    if count_requested is not None and count_valid is not None:
        if int(count_valid) < int(count_requested):
            issues.append(f"only {count_valid}/{count_requested} perf cases succeeded")
    error_count = block.get("error_count")
    if error_count is not None and int(error_count) > 0:
        issues.append(f"error_count={error_count}")
    for key in ("nan_count", "inf_count"):
        val = block.get(key)
        if val is not None and int(val) > 0:
            issues.append(f"{key}={val}")
    if expected_n is not None:
        got_n = block.get("n_per_round") or block.get("n")
        if got_n is not None and int(got_n) != int(expected_n):
            issues.append(f"only {got_n}/{expected_n} cases timed")
    return issues


def _invalidate_perf_if_incomplete(
    perf_workloads: dict | None,
    *,
    expected_scalar_n: int,
    expected_batch_n: int,
    row_status: str | None = None,
) -> dict | None:
    """Mark performance workloads invalid when coverage or row status forbids ranking."""
    if not isinstance(perf_workloads, dict):
        return perf_workloads
    row_issues: list[str] = []
    if row_status in ("partial", "failed", "skipped"):
        row_issues.append(f"row status is {row_status}")
    for key, expected_n in (
        ("scalar_warm", expected_scalar_n),
        ("batch_throughput", expected_batch_n),
    ):
        block = perf_workloads.get(key)
        if not isinstance(block, dict):
            continue
        issues = row_issues + _perf_block_issues(block, expected_n=expected_n)
        if issues:
            perf_workloads[key] = _mark_perf_block_invalid(block, issues)
    return perf_workloads


_COMPLETENESS_STATUSES = ("ok", "partial", "skipped", "failed")


def summarize_experiment_completeness(all_results: list[dict]) -> dict[str, dict]:
    """Build per-experiment ok/partial/skipped/failed counts for the run manifest."""
    experiment_completeness: dict[str, dict] = {}
    for r in all_results:
        exp_id = r["experiment"]
        entry = experiment_completeness.setdefault(exp_id, {
            "requested_adapters": [],
            "ok": 0,
            "partial": 0,
            "skipped": 0,
            "failed": 0,
            "lane": None,
            "reference_lane": None,
            "reference_source_tag": None,
            "rows": [],
        })
        lib_label = r["candidate_library"]
        profile = r.get("candidate_profile")
        full_label = (
            f"{lib_label}:{profile}"
            if profile and not (lib_label == "siderust" and profile == "iau2006a")
            else lib_label
        )
        if full_label not in entry["requested_adapters"]:
            entry["requested_adapters"].append(full_label)
        status = r.get("status") or "ok"
        if status not in _COMPLETENESS_STATUSES:
            status = "failed"
        entry[status] = entry.get(status, 0) + 1
        entry["rows"].append({
            "library": full_label,
            "status": status,
            "skip_reason": r.get("skip_reason"),
            "failure_reason": r.get("failure_reason"),
            "rankable": r.get("rankable") if "rankable" in r else r.get("rankable_accuracy"),
            "rankability_reason": r.get("rankability_reason") or r.get("rank_exclusion_reason"),
        })
        alignment = r.get("alignment") or {}
        if entry["lane"] is None and alignment.get("lane"):
            entry["lane"] = alignment["lane"]
            entry["reference_lane"] = alignment["lane"]
        if entry["reference_source_tag"] is None:
            entry["reference_source_tag"] = (
                r.get("reference_source_tag") or alignment.get("horizons_source")
            )
    for entry in experiment_completeness.values():
        entry["requested_adapters"].sort()
    return experiment_completeness


def _run_scope(requested: list[str], completed: list[str]) -> dict:
    """Classify a run against the core public suite (audit issue #5).

  ``partial`` is true when any *requested* experiment did not complete, or when
  the run is non-core-only.  ``core_partial`` / ``core_complete`` track the
  canonical public suite separately so a core+extra run with all requested
  experiments finished is not labelled partial merely for including diagnostics.
    """
    core = set(PUBLIC_EXPERIMENTS)
    completed_set = set(completed)
    requested_set = set(requested)
    covered_core = sorted(core & completed_set)
    missing_core = sorted(core - completed_set)
    missing_requested = sorted(requested_set - completed_set)
    extra = sorted(requested_set - core)

    if completed_set >= core and not extra:
        label = "core"
    elif completed_set >= core:
        label = "core+extra"
    elif covered_core and not extra:
        label = "core-subset"
    elif not (core & requested_set):
        label = "non-core"
    else:
        label = "mixed-subset"

    core_complete = not missing_core
    return {
        "suite_label": label,
        "partial": bool(missing_requested) or not core_complete or label == "non-core",
        "core_complete": core_complete,
        "core_partial": not core_complete,
        "core_experiments_total": len(core),
        "core_experiments_covered": len(covered_core),
        "missing_core_experiments": missing_core,
        "missing_requested_experiments": missing_requested,
        "extra_experiments": extra,
    }


def _collect_adapter_binary_provenance() -> dict:
    """Hash & stat each known adapter binary. Safe no-op if a binary is missing."""
    bins = {
        "siderust_adapter": LAB_ROOT / "pipeline/adapters/siderust_adapter/target/release/siderust-adapter",
        "anise_adapter": LAB_ROOT / "pipeline/adapters/anise_adapter/target/release/anise-adapter",
        "erfa_adapter": LAB_ROOT / "pipeline/adapters/erfa_adapter/build/erfa_adapter",
        "libnova_adapter": LAB_ROOT / "pipeline/adapters/libnova_adapter/build/libnova_adapter",
    }
    out: dict = {}
    for name, path in bins.items():
        if not path.exists():
            out[name] = {"present": False}
            continue
        try:
            data = path.read_bytes()
            out[name] = {
                "present": True,
                "path": str(path.relative_to(LAB_ROOT)),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        except Exception as exc:
            out[name] = {"present": True, "error": str(exc)}
    return out


def _collect_library_versions() -> dict:
    """Best-effort library version probe via pkg-config / well-known files."""
    versions: dict = {}
    # libnova via pkg-config
    try:
        r = subprocess.run(
            ["pkg-config", "--modversion", "libnova"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            versions["libnova"] = r.stdout.strip()
    except Exception:
        pass
    # ERFA C library version (header probe)
    try:
        header = Path("/usr/include/erfa.h")
        if header.exists():
            txt = header.read_text(errors="ignore")
            import re as _re
            m = _re.search(r"ERFA_VERSION\s+\"([^\"]+)\"", txt)
            if m:
                versions["erfa_c"] = m.group(1)
    except Exception:
        pass
    return versions


def _discover_anise_spk_provenance() -> dict | None:
    """Return ANISE SPK path/sha256/size if the same env-var discovery used
    by the adapter resolves a kernel. Mirrors the Rust discovery order."""
    candidates: list[Path] = []
    env_path = os.environ.get("ANISE_BSP_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            candidates.append(p)
        elif p.is_dir():
            candidates.extend(sorted(p.glob("*.bsp")))
    cache_root = os.environ.get("SIDERUST_BENCHES_CACHE")
    if cache_root:
        cache_bsp = Path(cache_root) / "kernels" / "de440.bsp"
        if cache_bsp.is_file():
            candidates.append(cache_bsp)
    datasets = os.environ.get("SIDERUST_DATASETS_DIR")
    if datasets:
        for sub in ("de441_dataset", "de440_dataset"):
            d = Path(datasets) / sub
            if d.is_dir():
                candidates.extend(sorted(d.glob("*.bsp")))
    for legacy in (
        LAB_ROOT / "siderust/scripts/jpl/de440/dataset/de440.bsp",
        LAB_ROOT / "anise/data/de440s.bsp",
        LAB_ROOT / "anise/data/de440.bsp",
    ):
        if legacy.is_file():
            candidates.append(legacy)

    for path in candidates:
        try:
            data = path.read_bytes()
            return {
                "path": str(path),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "source_tag": path.stem,
            }
        except Exception:
            continue
    return None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _discover_siderust_planet_spk_provenance() -> dict | None:
    """Record the SPK stack used by SIDERUST_PLANET_MODEL=spk_* adapters."""
    candidates: list[Path] = []
    env_paths = os.environ.get("SIDERUST_PLANET_KERNELS")
    if env_paths:
        candidates.extend(Path(path) for path in env_paths.split(os.pathsep) if path)
    else:
        cache_roots: list[Path] = []
        datasets = os.environ.get("SIDERUST_DATASETS_DIR")
        if datasets:
            cache_roots.append(Path(datasets))
        runtime_data = os.environ.get("SIDERUST_DATA_DIR")
        if runtime_data:
            cache_roots.append(Path(runtime_data))
        else:
            cache_roots.append(Path.home() / ".siderust/data")

        for root in cache_roots:
            candidates.extend([
                root / "de440_dataset/de440.bsp",
                root / "de441_dataset/de441_part-2.bsp",
                root / "de440.bsp",
                root / "de441_part-2.bsp",
                root / "mar099.bsp",
                root / "jup365.bsp",
                root / "jup365_merged.bsp",
                root / "sat441l.bsp",
                root / "ura184.bsp",
                root / "ura184_merged.bsp",
                root / "nep097.bsp",
            ])
        candidates.append(
            LAB_ROOT / "pipeline/adapters/siderust_adapter/datasets/de440_dataset/de440.bsp"
        )

    kernels = []
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            kernels.append({
                "path": str(path),
                "filename": path.name,
                "sha256": _hash_file(path),
                "size": path.stat().st_size,
            })
        except Exception as exc:
            kernels.append({"path": str(path), "error": str(exc)})
    return {"kernels": kernels} if kernels else None


def _get_git_branch(repo_path: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def generate_summary_table(all_results: list) -> str:
    """Generate a Markdown summary table from all results."""

    def fmt(v, precision=2):
        if v is None:
            return "—"
        if precision == 'e':
            return f"{v:.2e}"
        return f"{v:.{precision}f}"

    def _primary_perf(perf: dict) -> dict:
        if not isinstance(perf, dict):
            return {}
        scalar = perf.get("scalar_warm")
        if isinstance(scalar, dict):
            return scalar
        return perf

    def fmt_perf(perf: dict, precision=1) -> str:
        """Format scalar-warm per-op latency with † annotation if invalid."""
        p = _primary_perf(perf)
        ns = p.get("ns_per_op", p.get("per_op_ns"))
        if ns is None:
            return "—"
        suffix = "" if p.get("valid", True) else "†"
        return f"{ns:.{precision}f}{suffix}"

    def fmt_speedup(perf: dict, ref_perf: dict) -> str:
        """Format scalar-warm speedup ratio with † if either measurement is invalid."""
        p = _primary_perf(perf)
        rp = _primary_perf(ref_perf)
        ns = p.get("ns_per_op", p.get("per_op_ns"))
        ref_ns = rp.get("ns_per_op", rp.get("per_op_ns"))
        if not ns or not ref_ns:
            return "—"
        suffix = "" if p.get("valid", True) and rp.get("valid", True) else "†"
        return f"{ref_ns / ns:.1f}×{suffix}"

    # Separate by experiment type
    bpn_results = [r for r in all_results if r.get("experiment") == "frame_rotation_bpn"]
    gmst_results = [r for r in all_results if r.get("experiment") == "gmst_era"]

    lines = []

    if bpn_results:
        lines.append("### Frame Rotation (BPN: ICRS → True-of-Date)")
        lines.append("")
        lines.append("| Library | Ang p50 (mas) | Ang p99 (mas) | Ang max (mas) | Matrix Frob p50 | Closure p99 (rad) | Perf (ns/op) | Speedup vs ref |")
        lines.append("|---------|---------------|---------------|---------------|-----------------|-------------------|--------------|----------------|")

        for r in bpn_results:
            lib = r.get("candidate_library", "?")
            acc = r.get("accuracy", {})
            ang = acc.get("angular_error_mas", {})
            clo = acc.get("closure_error_rad", {})
            mfr = acc.get("matrix_frobenius", {}) or {}
            perf = r.get("performance", {})
            ref_perf = r.get("reference_performance", {})

            lines.append(
                f"| {lib} "
                f"| {fmt(ang.get('p50'))} "
                f"| {fmt(ang.get('p99'))} "
                f"| {fmt(ang.get('max'))} "
                f"| {fmt(mfr.get('p50'), 2)} "
                f"| {fmt(clo.get('p99'), 2)} "
                f"| {fmt_perf(perf)} "
                f"| {fmt_speedup(perf, ref_perf)} |"
            )
        lines.append("")

    if gmst_results:
        lines.append("### GMST / ERA (Time Scales)")
        lines.append("")
        lines.append("| Library | GMST p50 (arcsec) | GMST p99 (arcsec) | GMST max (arcsec) | ERA p50 (rad) | ERA max (rad) |")
        lines.append("|---------|-------------------|-------------------|-------------------|---------------|---------------|")

        for r in gmst_results:
            lib = r.get("candidate_library", "?")
            acc = r.get("accuracy", {})
            gmst = acc.get("gmst_error_arcsec", {})
            era = acc.get("era_error_rad", {})

            lines.append(
                f"| {lib} "
                f"| {fmt(gmst.get('p50'), 6)} "
                f"| {fmt(gmst.get('p99'), 6)} "
                f"| {fmt(gmst.get('max'), 6)} "
                f"| {fmt(era.get('p50'), 10)} "
                f"| {fmt(era.get('max'), 10)} |"
            )
        lines.append("")

    # --- Angular experiments (equ_ecl, equ_horizontal, solar_position, lunar_position) ---
    # --- Direction-vector transform experiments (BPN-style metrics) ---
    for exp_name, title in [
        ("frame_bias", "Frame Bias (ICRS → Mean J2000)"),
        ("precession", "Precession (Mean J2000 → Mean of Date)"),
        ("nutation", "Nutation (Mean of Date → True of Date)"),
        ("icrs_ecl_j2000", "ICRS → Ecliptic J2000"),
    ]:
        exp_results = [r for r in all_results if r.get("experiment") == exp_name]
        if not exp_results:
            continue

        lines.append(f"### {title}")
        lines.append("")
        lines.append("| Library | Ang p50 (mas) | Ang p99 (mas) | Ang max (mas) | Closure p99 (rad) | Perf (ns/op) | Speedup vs ref |")
        lines.append("|---------|---------------|---------------|---------------|-------------------|--------------|----------------|")

        for r in exp_results:
            lib = r.get("candidate_library", "?")
            acc = r.get("accuracy", {})
            ang = acc.get("angular_error_mas", {})
            clo = acc.get("closure_error_rad", {})
            perf = r.get("performance", {})
            ref_perf = r.get("reference_performance", {})

            lines.append(
                f"| {lib} "
                f"| {fmt(ang.get('p50'))} "
                f"| {fmt(ang.get('p99'))} "
                f"| {fmt(ang.get('max'))} "
                f"| {fmt(clo.get('p99'), 2)} "
                f"| {fmt_perf(perf)} "
                f"| {fmt_speedup(perf, ref_perf)} |"
            )
        lines.append("")

    # --- Angular experiments (equ_ecl, equ_horizontal, solar_position, etc.) ---
    angular_summary_experiments = [
        ("equ_ecl", "Equatorial ↔ Ecliptic Transform"),
        ("equ_horizontal", "Equatorial → Horizontal (AltAz)"),
        ("solar_position", "Sun Geocentric Position"),
        ("lunar_position", "Moon Geocentric Position"),
        ("icrs_ecl_tod", "ICRS → Ecliptic of Date"),
        ("horiz_to_equ", "Horizontal → Equatorial (AltAz → RA/Dec)"),
    ]
    angular_summary_experiments.extend(
        (exp_name, f"{cfg['body']} Geocentric Position")
        for exp_name, cfg in PLANET_POSITION_EXPERIMENTS.items()
    )

    for exp_name, title in angular_summary_experiments:
        exp_results = [r for r in all_results if r.get("experiment") == exp_name]
        if not exp_results:
            continue

        lines.append(f"### {title}")
        lines.append("")
        lines.append("| Library | Sep p50 (arcsec) | Sep p99 (arcsec) | Sep max (arcsec) | RA bias (arcsec) | Dec bias (arcsec) |")
        lines.append("|---------|------------------|------------------|------------------|------------------|-------------------|")

        for r in exp_results:
            lib = r.get("candidate_library", "?")
            acc = r.get("accuracy", {})
            sep = acc.get("angular_sep_arcsec", {})
            ra_b = acc.get("signed_ra_error_arcsec", {})
            dec_b = acc.get("signed_dec_error_arcsec", {})

            lines.append(
                f"| {lib} "
                f"| {fmt(sep.get('p50'), 4)} "
                f"| {fmt(sep.get('p99'), 4)} "
                f"| {fmt(sep.get('max'), 4)} "
                f"| {fmt(ra_b.get('mean'), 4)} "
                f"| {fmt(dec_b.get('mean'), 4)} |"
            )
        lines.append("")

    # --- Kepler solver ---
    kepler_results = [r for r in all_results if r.get("experiment") == "kepler_solver"]
    if kepler_results:
        lines.append("### Kepler Solver (M→E→ν)")
        lines.append("")
        lines.append("| Library | E p50 (rad) | E max (rad) | ν p50 (rad) | ν max (rad) | Consistency max (rad) |")
        lines.append("|---------|-------------|-------------|-------------|-------------|-----------------------|")

        for r in kepler_results:
            lib = r.get("candidate_library", "?")
            acc = r.get("accuracy", {})
            E_err = acc.get("E_error_rad", {})
            nu_err = acc.get("nu_error_rad", {})
            con = acc.get("consistency_error_rad", {})

            lines.append(
                f"| {lib} "
                f"| {fmt(E_err.get('p50'), 'e')} "
                f"| {fmt(E_err.get('max'), 'e')} "
                f"| {fmt(nu_err.get('p50'), 'e')} "
                f"| {fmt(nu_err.get('max'), 'e')} "
                f"| {fmt(con.get('max'), 'e')} |"
            )
        lines.append("")

    # --- Feature / Model Parity Matrix ---
    lines.append("### Feature / Model Parity Matrix")
    lines.append("")
    experiments_seen = sorted(set(r.get("experiment", "") for r in all_results))
    libs_seen = sorted(set(r.get("candidate_library", "") for r in all_results))
    all_libs = ["erfa"] + libs_seen  # erfa is always reference

    header = "| Experiment | " + " | ".join(all_libs) + " |"
    separator = "|------------|" + "|".join(["---"] * len(all_libs)) + "|"
    lines.append(header)
    lines.append(separator)

    # Model descriptions per (experiment, library) from alignment checklists
    for exp in experiments_seen:
        exp_r = [r for r in all_results if r.get("experiment") == exp]
        if not exp_r:
            continue
        alignment = exp_r[0].get("alignment", {})
        models = alignment.get("models", {})
        cells = []
        for lib in all_libs:
            model_str = models.get(lib, "—")
            # Truncate for table readability
            if len(model_str) > 50:
                model_str = model_str[:47] + "..."
            cells.append(model_str)
        lines.append(f"| {exp} | " + " | ".join(cells) + " |")
    lines.append("")

    # Footnote for invalid perf measurements
    lines.append("† Measurement below reliability threshold (<10 ns/op or CV >20%); treat as indicative only.")
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main experiment runners
# ---------------------------------------------------------------------------

def run_experiment_frame_rotation_bpn(n: int, seed: int, run_perf: bool = True,
                                      perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """
    Run the frame_rotation_bpn experiment end-to-end.

    Reference: ERFA (IAU 2006/2000A BPN matrix)
    Candidates: Siderust, Astropy, libnova, anise
    """
    exp_name = "frame_rotation_bpn"
    candidate_list = candidate_adapters_for(exp_name)
    adapter_list = [("erfa", [str(ERFA_BIN)], "reference")]
    adapter_list += [(lib, cmd, "candidate") for lib, cmd in candidate_list]
    total_steps = 3 + len(adapter_list) + (len(candidate_list) + 1 if run_perf else 0)
    step = 0

    progress(f"Starting experiment (N={n}, seed={seed})", exp_name, "start", total_steps, step)

    # 1) Generate inputs
    step += 1
    progress("Generating inputs...", exp_name, "generate_inputs", total_steps, step)
    epochs, directions, labels = generate_frame_rotation_inputs(n, seed)
    input_text = format_bpn_input(epochs, directions)

    # Compute dataset fingerprint for reproducibility
    ds_fingerprint = dataset_fingerprint({
        "experiment": exp_name, "n": n, "seed": seed,
        "epochs_hash": hashlib.sha256(epochs.tobytes()).hexdigest()[:12],
    })

    # 2) Run adapters
    adapters = {}
    for lib, cmd, role in adapter_list:
        step += 1
        progress(f"Running {lib} adapter ({role})...", exp_name, f"adapter_{lib}", total_steps, step)
        adapters[lib] = run_adapter(cmd, input_text, lib)

    # 3) Compute accuracy metrics
    step += 1
    progress("Computing accuracy metrics...", exp_name, "accuracy", total_steps, step)
    results = []
    ref_data = adapters.get("erfa")
    if ref_data is None:
        progress("ERFA adapter failed — cannot compute accuracy.", exp_name, "error")
        return results

    meta = run_metadata()

    def _make_status_row(lib_label: str, status: str, *,
                         skip_reason: str | None = None,
                         failure_reason: str | None = None,
                         accuracy: dict | None = None) -> dict:
        lib_base_ = adapter_base(lib_label)
        result_ = {
            "experiment": exp_name,
            "candidate_library": lib_base_,
            "reference_library": "erfa",
            "reference_lane": None,
            "reference_source_tag": "ERFA/SOFA",
            "status": status,
            "skip_reason": skip_reason,
            "failure_reason": failure_reason,
            "description": EXPERIMENT_DESCRIPTIONS.get(exp_name, {}),
            "alignment": alignment_checklist(exp_name, candidate_library=lib_base_, candidate_label=lib_label),
            "inputs": {
                "count": n, "seed": seed,
                "epoch_range": [f"JD {min(epochs):.1f}", f"JD {max(epochs):.1f}"],
                "dataset_fingerprint": ds_fingerprint,
            },
            "accuracy": accuracy or {},
            "performance": empty_performance_workloads(),
            "reference_performance": empty_performance_workloads(),
            "benchmark_config": {
                "perf_rounds": perf_rounds if run_perf else 0,
                "perf_scalar_n": perf_scalar_n,
                "perf_batch_n": perf_batch_n,
                "perf_batch_rounds": perf_batch_rounds if run_perf else 0,
                "perf_enabled": run_perf,
            },
            "run_metadata": meta,
        }
        enriched = enrich_result(result_, exp_name, lib_label)
        if status != "ok":
            enriched["rankable_accuracy"] = False
            enriched["rank_exclusion_reason"] = (
                skip_reason or failure_reason or f"status={status}"
            )
        enriched["rankable"] = enriched.get("rankable_accuracy", False)
        enriched["rankability_reason"] = enriched.get("rank_exclusion_reason")
        return enriched

    for lib, _cmd in candidate_list:
        cand_data = adapters.get(lib)
        if cand_data is None:
            results.append(_make_status_row(
                lib, "failed",
                failure_reason="adapter produced no output (process exited unsuccessfully or returned no JSON)",
            ))
            progress(f"{lib}: failed (no output)", exp_name, f"fail_{lib}")
            continue
        if isinstance(cand_data, dict) and cand_data.get("skipped"):
            reason = cand_data.get("reason", "adapter reported skipped")
            results.append(_make_status_row(lib, "skipped", skip_reason=reason))
            progress(f"{lib}: skipped ({reason})", exp_name, f"skip_{lib}")
            continue
        if not isinstance(cand_data, dict) or not cand_data.get("cases"):
            results.append(_make_status_row(
                lib, "failed",
                failure_reason="adapter output missing 'cases' array",
            ))
            progress(f"{lib}: failed (missing cases)", exp_name, f"fail_{lib}")
            continue

        lib_base = adapter_base(lib)
        accuracy = compute_accuracy_metrics(
            ref_data["cases"], cand_data["cases"], "erfa", adapter_display(lib)
        )
        accuracy = _ensure_accuracy_counts(accuracy, len(ref_data["cases"]))
        acc_status = _accuracy_status_from_metrics(accuracy)
        results.append(_make_status_row(
            lib, acc_status, accuracy=accuracy,
            failure_reason=_partial_accuracy_reason(accuracy) if acc_status == "partial" else None,
        ))

    # 4) Performance measurement (Phase-6 workloads)
    if run_perf:
        progress(
            f"Running performance workloads (scalar N={perf_scalar_n}, batch N={perf_batch_n})...",
            exp_name, "performance", total_steps, step + 1,
        )

        def _bpn_perf_inputs(count, seed_):
            e, d, _ = generate_frame_rotation_inputs(count, seed_)
            return e, d

        for lib, cmd in candidate_list:
            step += 1
            progress(f"Timing {lib} workloads...", exp_name, f"perf_{lib}", total_steps, step)
            perf_data = run_perf_workloads(
                cmd, exp_name, _bpn_perf_inputs, format_bpn_perf_input, seed,
                scalar_rounds=perf_rounds,
                scalar_n=perf_scalar_n,
                batch_rounds=perf_batch_rounds,
                batch_n=perf_batch_n,
                warmup=perf_warmup,
                timeout_s=perf_timeout_s,
            )
            for r in results:
                if r["candidate_library"] == adapter_base(lib) and r.get("candidate_profile") == adapter_profile(lib):
                    r["performance"] = _invalidate_perf_if_incomplete(
                        perf_data,
                        expected_scalar_n=perf_scalar_n,
                        expected_batch_n=perf_batch_n,
                    )

        step += 1
        progress(f"Timing erfa reference workloads...", exp_name, "perf_erfa", total_steps, step)
        perf_erfa = run_perf_workloads(
            [str(ERFA_BIN)], exp_name, _bpn_perf_inputs, format_bpn_perf_input, seed,
            scalar_rounds=perf_rounds,
            scalar_n=perf_scalar_n,
            batch_rounds=perf_batch_rounds,
            batch_n=perf_batch_n,
            warmup=perf_warmup,
            timeout_s=perf_timeout_s,
        )
        for r in results:
            r["reference_performance"] = perf_erfa

    progress("Experiment complete.", exp_name, "done", total_steps, total_steps)
    return results



def _run_external_reference_experiment(exp_name: str, n: int, seed: int,
                                        run_perf: bool = True,
                                        perf_rounds: int = DEFAULT_PERF_ROUNDS,
                                        perf_scalar_n: int = SCALAR_WARM_N,
                                        perf_batch_n: int = BATCH_THROUGHPUT_N,
                                        perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS,
                                        perf_warmup: int = DEFAULT_PERF_WARMUP,
                                        perf_timeout_s: int = 120,
                                        input_gen_fn=None, input_fmt_fn=None,
                                        perf_fmt_fn=None,
                                        accuracy_fn=None, accuracy_kwargs=None):
    """Experiment runner using an external reference (e.g. JPL Horizons) instead of ERFA.

    All adapters (including ERFA) are treated as candidates.
    Reference cases come from the external provider (Horizons).
    reference_performance is left empty since the reference is external.
    """
    if accuracy_kwargs is None:
        accuracy_kwargs = {}

    all_adapters = list(candidate_adapters_for(exp_name))
    if _default_catalog().get("erfa", exp_name) is not None:
        # Horizons is the reference for this runner. ERFA is only an
        # additional candidate where its catalogued adapter actually exposes
        # the experiment; the barycenter lanes deliberately do not.
        all_adapters.insert(0, ("erfa", [str(ERFA_BIN)]))
    total_steps = 3 + len(all_adapters) + (len(all_adapters) if run_perf else 0)
    step = 0

    progress(f"Starting experiment with external reference (N={n}, seed={seed})",
             exp_name, "start", total_steps, step)

    # 1) Generate inputs
    step += 1
    progress("Generating inputs...", exp_name, "generate_inputs", total_steps, step)
    inputs = input_gen_fn(n, seed)
    input_text = input_fmt_fn(*inputs) if not isinstance(inputs, str) else inputs

    # Dataset fingerprint
    ds_fp_data = {"experiment": exp_name, "n": n, "seed": seed}
    if isinstance(inputs, tuple) and len(inputs) > 0:
        for i, inp in enumerate(inputs):
            if isinstance(inp, np.ndarray):
                ds_fp_data[f"input_{i}_hash"] = hashlib.sha256(inp.tobytes()).hexdigest()[:12]
    ds_fingerprint = dataset_fingerprint(ds_fp_data)

    # Extract epochs for Horizons query
    epochs = inputs[0] if isinstance(inputs, tuple) else inputs

    # 2) Fetch external reference
    step += 1
    progress("Fetching JPL Horizons reference data...", exp_name, "horizons_fetch", total_steps, step)
    # Lane is derived from the experiment ID — `*_apparent` IDs force the
    # apparent OBSERVER lane; everything else uses the geometric VECTORS lane.
    lane = LANE_APPARENT if is_apparent_experiment(exp_name) else LANE_GEOMETRIC
    try:
        horizons_result = fetch_horizons_reference(
            exp_name,
            epochs,
            use_cache=HORIZONS_USE_CACHE,
            allow_network=HORIZONS_ALLOW_NETWORK,
            lane=lane,
        )
    except Exception as exc:
        progress(f"Horizons fetch failed: {exc} — aborting experiment.", exp_name, "error")
        print(f"  ✗ {exp_name}: Horizons fetch failed: {exc}", file=sys.stderr)
        return []

    ref_cases = horizons_result["cases"]
    source_tag = horizons_result["source_tag"]
    cache_key = horizons_result["cache_key"]
    from_cache = horizons_result["from_cache"]
    lane = horizons_result.get("lane", lane)
    lane_label = "geometric VECTORS" if lane == LANE_GEOMETRIC else "apparent OBSERVER"
    reference_mode = (
        "OBSERVER astrometric geocentric RA/Dec" if lane == LANE_APPARENT
        else "VECTORS geometric ICRF state (X/Y/Z)"
    )

    progress(
        f"Horizons reference loaded (lane={lane}, source={source_tag}, cache={'hit' if from_cache else 'miss'})",
        exp_name, "horizons_done",
    )

    # 3) Run all adapters as candidates
    adapters = {}
    for lib, cmd in all_adapters:
        step += 1
        progress(f"Running {lib} adapter (candidate)...", exp_name, f"adapter_{lib}", total_steps, step)
        adapters[lib] = run_adapter(cmd, input_text, lib, extra_env={"LAB_LANE": lane})

    # 4) Compute accuracy against Horizons reference
    step += 1
    progress("Computing accuracy metrics vs Horizons...", exp_name, "accuracy", total_steps, step)
    results = []
    meta = run_metadata()
    candidate_libs = [lib for lib, _cmd in all_adapters]

    def _make_status_result(lib_label: str, status: str, *,
                            skip_reason: str | None = None,
                            failure_reason: str | None = None,
                            accuracy: dict | None = None,
                            adapter_model: str | None = None) -> dict:
        lib_base_ = adapter_base(lib_label)
        alignment_ = alignment_checklist(exp_name, candidate_library=lib_base_, candidate_label=lib_label)
        alignment_["horizons_source"] = source_tag
        alignment_["horizons_cache_key"] = cache_key
        alignment_["horizons_from_cache"] = from_cache
        alignment_["lane"] = lane
        provenance_ = {
            "source": "JPL Horizons",
            "source_tag": source_tag,
            "lane": lane,
            "cache_key": cache_key,
            "from_cache": from_cache,
            "frame": "ICRF",
            "center": "Earth geocenter (500@399)",
            "vec_corr": "NONE" if lane == LANE_GEOMETRIC else "applied (OBSERVER)",
            "time_scale": "TT",
            "query_params": horizons_result.get("query_params", {}),
        }
        result_ = {
            "experiment": exp_name,
            "candidate_library": lib_base_,
            "reference_library": "jpl_horizons",
            "reference_lane": lane,
            "reference_source_tag": source_tag,
            "status": status,
            "skip_reason": skip_reason,
            "failure_reason": failure_reason,
            "description": EXPERIMENT_DESCRIPTIONS.get(exp_name, {}),
            "alignment": alignment_,
            "inputs": {
                "count": n, "seed": seed,
                "dataset_fingerprint": ds_fingerprint,
                "reference_source": "jpl_horizons",
                "reference_lane": lane,
                "horizons_ephemeris": source_tag,
                "horizons_lane": lane,
                "horizons_mode": reference_mode,
                "horizons_frame": "ICRF",
                "horizons_center": "Earth geocenter (500@399)",
                "horizons_time_scale": "TT",
                "horizons_cache_key": cache_key,
            },
            "accuracy": accuracy or {},
            "performance": empty_performance_workloads(),
            "reference_performance": {},
            "model": adapter_model,
            "benchmark_config": {
                "perf_rounds": perf_rounds if run_perf else 0,
                "perf_warmup": perf_warmup,
                "perf_scalar_n": perf_scalar_n,
                "perf_batch_n": perf_batch_n,
                "perf_batch_rounds": perf_batch_rounds if run_perf else 0,
                "perf_enabled": run_perf,
                "perf_timeout_s": perf_timeout_s,
            },
            "run_metadata": meta,
        }
        enriched = enrich_result(result_, exp_name, lib_label, source_provenance=provenance_)
        # Force non-ok rows out of accuracy rankings.
        if status != "ok":
            enriched["rankable_accuracy"] = False
            enriched["rank_exclusion_reason"] = (
                skip_reason or failure_reason or f"status={status}"
            )
        # Expose lane-aware additive aliases.
        enriched["rankable"] = enriched.get("rankable_accuracy", False)
        enriched["rankability_reason"] = enriched.get("rank_exclusion_reason")
        return enriched

    for lib in candidate_libs:
        cand_data = adapters.get(lib)
        if cand_data is None:
            results.append(_make_status_result(
                lib, "failed",
                failure_reason="adapter produced no output (process exited unsuccessfully or returned no JSON)",
            ))
            progress(f"{lib}: failed (no output)", exp_name, f"fail_{lib}")
            continue
        if isinstance(cand_data, dict) and cand_data.get("skipped"):
            reason = cand_data.get("reason", "adapter reported skipped")
            results.append(_make_status_result(lib, "skipped", skip_reason=reason))
            progress(f"{lib}: skipped ({reason})", exp_name, f"skip_{lib}")
            continue
        if not isinstance(cand_data, dict) or not cand_data.get("cases"):
            results.append(_make_status_result(
                lib, "failed",
                failure_reason="adapter output missing 'cases' array",
            ))
            progress(f"{lib}: failed (missing cases)", exp_name, f"fail_{lib}")
            continue

        accuracy = accuracy_fn(ref_cases, cand_data["cases"], "jpl_horizons",
                               adapter_display(lib), **accuracy_kwargs)
        accuracy = _ensure_accuracy_counts(accuracy, len(ref_cases))
        acc_status = _accuracy_status_from_metrics(accuracy)
        results.append(_make_status_result(
            lib, acc_status, accuracy=accuracy,
            adapter_model=cand_data.get("model") or cand_data.get("model_selected"),
            failure_reason=_partial_accuracy_reason(accuracy) if acc_status == "partial" else None,
        ))

    # 5) Performance measurement (Phase-6 workloads) — no reference_performance for external refs
    if run_perf and perf_fmt_fn is not None:
        progress(
            f"Running performance workloads (scalar N={perf_scalar_n}, batch N={perf_batch_n})...",
            exp_name, "performance", total_steps, step + 1,
        )

        for lib, cmd in all_adapters:
            step += 1
            progress(f"Timing {lib} workloads...", exp_name, f"perf_{lib}", total_steps, step)
            # A5: propagate LAB_LANE so perf runs match accuracy lane (audit F1).
            perf_data = run_perf_workloads(
                cmd, exp_name, input_gen_fn, perf_fmt_fn, seed,
                scalar_rounds=perf_rounds,
                scalar_n=perf_scalar_n,
                batch_rounds=perf_batch_rounds,
                batch_n=perf_batch_n,
                warmup=perf_warmup,
                timeout_s=perf_timeout_s,
                extra_env={"LAB_LANE": lane},
            )
            for r in results:
                if r["candidate_library"] == adapter_base(lib) and r.get("candidate_profile") == adapter_profile(lib):
                    r["performance"] = _invalidate_perf_if_incomplete(
                        perf_data,
                        expected_scalar_n=perf_scalar_n,
                        expected_batch_n=perf_batch_n,
                    )

    progress("Experiment complete.", exp_name, "done", total_steps, total_steps)
    return results

def _run_generic_experiment(exp_name: str, n: int, seed: int, run_perf: bool = True,
                             perf_rounds: int = DEFAULT_PERF_ROUNDS,
                             perf_scalar_n: int = SCALAR_WARM_N,
                             perf_batch_n: int = BATCH_THROUGHPUT_N,
                             perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS,
                             perf_warmup: int = DEFAULT_PERF_WARMUP,
                             perf_timeout_s: int = 120,
                             input_gen_fn=None, input_fmt_fn=None, perf_fmt_fn=None,
                             accuracy_fn=None, accuracy_kwargs=None,
                             python_reference_fn=None,
                             reference_label: str = "erfa",
                             reference_source_tag: str = "ERFA/SOFA"):
    """Generic experiment runner with progress tracking, multi-sample perf, and metadata.

    This consolidates the common pattern shared by all experiments.
    """
    if accuracy_kwargs is None:
        accuracy_kwargs = {}

    candidate_list = candidate_adapters_for(exp_name)
    if python_reference_fn is None:
        adapter_list = [("erfa", [str(ERFA_BIN)])] + candidate_list
    else:
        adapter_list = list(candidate_list)
    total_steps = 3 + len(adapter_list) + (len(candidate_list) + 1 if run_perf and perf_fmt_fn is not None else 0)
    step = 0

    progress(f"Starting experiment (N={n}, seed={seed})", exp_name, "start", total_steps, step)

    # 1) Generate inputs
    step += 1
    progress("Generating inputs...", exp_name, "generate_inputs", total_steps, step)
    inputs = input_gen_fn(n, seed)
    input_text = input_fmt_fn(*inputs) if not isinstance(inputs, str) else inputs

    # Dataset fingerprint
    ds_fp_data = {"experiment": exp_name, "n": n, "seed": seed}
    if isinstance(inputs, tuple) and len(inputs) > 0:
        for i, inp in enumerate(inputs):
            if isinstance(inp, np.ndarray):
                ds_fp_data[f"input_{i}_hash"] = hashlib.sha256(inp.tobytes()).hexdigest()[:12]
    ds_fingerprint = dataset_fingerprint(ds_fp_data)

    # 2) Run adapters
    adapters = {}
    for lib, cmd in adapter_list:
        step += 1
        role = "reference" if lib == "erfa" else "candidate"
        progress(f"Running {lib} adapter ({role})...", exp_name, f"adapter_{lib}", total_steps, step)
        adapters[lib] = run_adapter(cmd, input_text, lib)

    # 3) Compute accuracy
    step += 1
    progress("Computing accuracy metrics...", exp_name, "accuracy", total_steps, step)
    results = []
    if python_reference_fn is not None:
        ref_cases = python_reference_fn(*inputs) if not isinstance(inputs, str) else python_reference_fn(inputs)
        ref_data = {"cases": ref_cases, "library": reference_label, "model": reference_source_tag}
    else:
        ref_data = adapters.get("erfa")
        if ref_data is None:
            progress("ERFA adapter failed — cannot compute accuracy.", exp_name, "error")
            return results

    meta = run_metadata()

    def _make_status_row(lib_label: str, status: str, *,
                         skip_reason: str | None = None,
                         failure_reason: str | None = None,
                         accuracy: dict | None = None) -> dict:
        lib_base_ = adapter_base(lib_label)
        result_ = {
            "experiment": exp_name,
            "candidate_library": lib_base_,
            "reference_library": reference_label,
            "reference_lane": None,
            "reference_source_tag": reference_source_tag,
            "status": status,
            "skip_reason": skip_reason,
            "failure_reason": failure_reason,
            "description": EXPERIMENT_DESCRIPTIONS.get(exp_name, {}),
            "alignment": alignment_checklist(exp_name, candidate_library=lib_base_, candidate_label=lib_label),
            "inputs": {
                "count": n, "seed": seed,
                "dataset_fingerprint": ds_fingerprint,
            },
            "accuracy": accuracy or {},
            "performance": empty_performance_workloads(),
            "reference_performance": empty_performance_workloads(),
            "benchmark_config": {
                "perf_rounds": perf_rounds if run_perf else 0,
                "perf_warmup": perf_warmup,
                "perf_scalar_n": perf_scalar_n,
                "perf_batch_n": perf_batch_n,
                "perf_batch_rounds": perf_batch_rounds if run_perf else 0,
                "perf_enabled": run_perf,
                "perf_timeout_s": perf_timeout_s,
            },
            "run_metadata": meta,
        }
        enriched = enrich_result(result_, exp_name, lib_label)
        if status != "ok":
            enriched["rankable_accuracy"] = False
            enriched["rank_exclusion_reason"] = (
                skip_reason or failure_reason or f"status={status}"
            )
        enriched["rankable"] = enriched.get("rankable_accuracy", False)
        enriched["rankability_reason"] = enriched.get("rank_exclusion_reason")
        return enriched

    for lib, _cmd in candidate_list:
        cand_data = adapters.get(lib)
        if cand_data is None:
            results.append(_make_status_row(
                lib, "failed",
                failure_reason="adapter produced no output (process exited unsuccessfully or returned no JSON)",
            ))
            progress(f"{lib}: failed (no output)", exp_name, f"fail_{lib}")
            continue

        if isinstance(cand_data, dict) and cand_data.get("skipped"):
            reason = cand_data.get("reason", "adapter reported skipped")
            results.append(_make_status_row(lib, "skipped", skip_reason=reason))
            progress(f"{lib}: skipped ({reason})", exp_name, f"skip_{lib}")
            continue

        if not isinstance(cand_data, dict) or not cand_data.get("cases"):
            results.append(_make_status_row(
                lib, "failed",
                failure_reason="adapter output missing 'cases' array",
            ))
            progress(f"{lib}: failed (missing cases)", exp_name, f"fail_{lib}")
            continue

        lib_base = adapter_base(lib)
        accuracy = accuracy_fn(ref_data["cases"], cand_data["cases"], reference_label, adapter_display(lib), **accuracy_kwargs)
        accuracy = _ensure_accuracy_counts(accuracy, len(ref_data["cases"]))
        acc_status = _accuracy_status_from_metrics(accuracy)
        results.append(_make_status_row(
            lib, acc_status, accuracy=accuracy,
            failure_reason=_partial_accuracy_reason(accuracy) if acc_status == "partial" else None,
        ))

    # 4) Performance measurement (Phase-6 workloads)
    if run_perf and perf_fmt_fn is not None:
        progress(
            f"Running performance workloads (scalar N={perf_scalar_n}, batch N={perf_batch_n})...",
            exp_name, "performance", total_steps, step + 1,
        )

        for lib, cmd in candidate_list:
            step += 1
            progress(f"Timing {lib} workloads...", exp_name, f"perf_{lib}", total_steps, step)
            perf_data = run_perf_workloads(
                cmd, exp_name, input_gen_fn, perf_fmt_fn, seed,
                scalar_rounds=perf_rounds,
                scalar_n=perf_scalar_n,
                batch_rounds=perf_batch_rounds,
                batch_n=perf_batch_n,
                warmup=perf_warmup,
                timeout_s=perf_timeout_s,
            )
            for r in results:
                if r["candidate_library"] == adapter_base(lib) and r.get("candidate_profile") == adapter_profile(lib):
                    r["performance"] = _invalidate_perf_if_incomplete(
                        perf_data,
                        expected_scalar_n=perf_scalar_n,
                        expected_batch_n=perf_batch_n,
                    )

        if python_reference_fn is None:
            step += 1
            progress(f"Timing erfa reference workloads...", exp_name, "perf_erfa", total_steps, step)
            perf_erfa = run_perf_workloads(
                [str(ERFA_BIN)], exp_name, input_gen_fn, perf_fmt_fn, seed,
                scalar_rounds=perf_rounds,
                scalar_n=perf_scalar_n,
                batch_rounds=perf_batch_rounds,
                batch_n=perf_batch_n,
                warmup=perf_warmup,
                timeout_s=perf_timeout_s,
            )
            for r in results:
                r["reference_performance"] = perf_erfa

    progress("Experiment complete.", exp_name, "done", total_steps, total_steps)
    return results
def run_experiment_gmst_era(n: int, seed: int, run_perf: bool = True,
                            perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the gmst_era experiment end-to-end."""
    return _run_generic_experiment(
        exp_name="gmst_era", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_gmst_era_inputs,
        input_fmt_fn=format_gmst_input,
        perf_fmt_fn=format_gmst_perf_input,
        accuracy_fn=compute_gmst_accuracy,
    )


def run_experiment_equ_ecl(n: int, seed: int, run_perf: bool = True,
                           perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the equ_ecl experiment: equatorial ↔ ecliptic coordinate transform."""
    return _run_generic_experiment(
        exp_name="equ_ecl", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_equ_ecl_inputs,
        input_fmt_fn=format_equ_ecl_input,
        perf_fmt_fn=format_equ_ecl_perf_input,
        accuracy_fn=compute_angular_accuracy,
        accuracy_kwargs={"ra_key": "ecl_lon_rad", "dec_key": "ecl_lat_rad"},
    )


def run_experiment_equ_horizontal(n: int, seed: int, run_perf: bool = True,
                                   perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the equ_horizontal experiment: equatorial → horizontal (AltAz)."""
    return _run_generic_experiment(
        exp_name="equ_horizontal", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_equ_horizontal_inputs,
        input_fmt_fn=format_equ_horizontal_input,
        perf_fmt_fn=format_equ_horizontal_perf_input,
        accuracy_fn=compute_angular_accuracy,
        accuracy_kwargs={"ra_key": "az_rad", "dec_key": "alt_rad"},
    )


def run_experiment_solar_position(n: int, seed: int, run_perf: bool = True, perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120,
                                   exp_name: str = "solar_position"):
    """Run the solar_position experiment: geocentric Sun RA/Dec vs JPL Horizons."""
    def _solar_gen(n, seed):
        epochs = generate_solar_position_inputs(n, seed)
        return (epochs,)

    return _run_external_reference_experiment(
        exp_name=exp_name, n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=_solar_gen,
        input_fmt_fn=lambda epochs: format_solar_position_input(epochs),
        perf_fmt_fn=lambda epochs: format_solar_position_perf_input(epochs),
        accuracy_fn=compute_angular_accuracy,
        accuracy_kwargs={"ra_key": "ra_rad", "dec_key": "dec_rad", "extra_keys": ["dist_au"]},
    )


def run_experiment_lunar_position(n: int, seed: int, run_perf: bool = True, perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120,
                                   exp_name: str = "lunar_position"):
    """Run the lunar_position experiment: geocentric Moon RA/Dec vs JPL Horizons."""
    def _lunar_gen(n, seed):
        epochs = generate_lunar_position_inputs(n, seed)
        return (epochs,)

    return _run_external_reference_experiment(
        exp_name=exp_name, n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=_lunar_gen,
        input_fmt_fn=lambda epochs: format_lunar_position_input(epochs),
        perf_fmt_fn=lambda epochs: format_lunar_position_perf_input(epochs),
        accuracy_fn=compute_angular_accuracy,
        accuracy_kwargs={"ra_key": "ra_rad", "dec_key": "dec_rad", "extra_keys": ["dist_km"]},
    )


def run_experiment_planet_position(exp_name: str, n: int, seed: int, run_perf: bool = True,
                                   perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run one planetary geocentric/barycenter position experiment vs JPL Horizons."""
    if exp_name not in PLANET_POSITION_EXPERIMENTS:
        raise KeyError(f"Unknown planetary position experiment '{exp_name}'")

    def _planet_gen(n, seed):
        epochs = generate_planet_position_inputs(n, seed)
        return (epochs,)

    return _run_external_reference_experiment(
        exp_name=exp_name, n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=_planet_gen,
        input_fmt_fn=lambda epochs, exp_name=exp_name: _format_external_position_input(exp_name, epochs),
        perf_fmt_fn=lambda epochs, exp_name=exp_name: _format_external_position_perf_input(exp_name, epochs),
        accuracy_fn=compute_angular_accuracy,
        accuracy_kwargs={"ra_key": "ra_rad", "dec_key": "dec_rad", "extra_keys": ["dist_au"]},
    )


def kepler_python_reference(M_arr, e_arr):
    """High-precision Python reference for Kepler's equation.

    Neither SOFA nor ERFA expose a public Kepler-equation solver, so the
    audit policy treats this experiment as ``self-consistent``: every
    candidate is benchmarked against a Newton-Raphson iteration computed
    in pipeline Python to machine epsilon (≤ 1e-15 residual).

    The reference is mathematics: M = E - e·sin(E) has a unique root for
    every (M, e) with e ∈ [0, 1).  We expose it as a separate function
    (not embedded inside any adapter) so the truth path is auditable.
    """
    cases = []
    for M, e in zip(M_arr, e_arr):
        # Initial guess: M for low e, π for near-parabolic (Danby).
        E = float(M) if e < 0.8 else math.pi
        for _ in range(200):
            f = E - e * math.sin(E) - M
            fp = 1.0 - e * math.cos(E)
            dE = f / fp
            E -= dE
            if abs(dE) < 1e-15:
                break
        # True anomaly via half-angle (numerically stable for high e).
        sqrt_term = math.sqrt((1.0 + e) / max(1.0 - e, 1e-300))
        nu = 2.0 * math.atan2(sqrt_term * math.sin(E / 2.0), math.cos(E / 2.0))
        residual = E - e * math.sin(E) - M
        cases.append({
            "M_rad": float(M),
            "e": float(e),
            "E_rad": float(E),
            "nu_rad": float(nu),
            "residual_rad": float(residual),
        })
    return cases


def run_experiment_kepler_solver(n: int, seed: int, run_perf: bool = True,
                                  perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the kepler_solver experiment: Kepler's equation M→E→ν.

    Reference is a pipeline-side Newton-Raphson solver to ~machine
    epsilon (no SOFA/ERFA public Kepler solver exists).
    """
    return _run_generic_experiment(
        exp_name="kepler_solver", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_kepler_inputs,
        input_fmt_fn=format_kepler_input,
        perf_fmt_fn=format_kepler_perf_input,
        accuracy_fn=compute_kepler_accuracy,
        python_reference_fn=kepler_python_reference,
        reference_label="pipeline_python",
        reference_source_tag="Pipeline Newton-Raphson (machine epsilon)",
    )


def run_experiment_frame_bias(n: int, seed: int, run_perf: bool = True,
                               perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the frame_bias experiment: ICRS → Mean J2000 frame bias."""
    return _run_generic_experiment(
        exp_name="frame_bias", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_direction_vector_inputs,
        input_fmt_fn=format_frame_bias_input,
        perf_fmt_fn=format_frame_bias_perf_input,
        accuracy_fn=compute_accuracy_metrics,
    )


def run_experiment_precession(n: int, seed: int, run_perf: bool = True,
                               perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the precession experiment: Mean J2000 → Mean of Date."""
    return _run_generic_experiment(
        exp_name="precession", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_direction_vector_inputs,
        input_fmt_fn=format_precession_input,
        perf_fmt_fn=format_precession_perf_input,
        accuracy_fn=compute_accuracy_metrics,
    )


def run_experiment_nutation(n: int, seed: int, run_perf: bool = True,
                             perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the nutation experiment: Mean of Date → True of Date."""
    return _run_generic_experiment(
        exp_name="nutation", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_direction_vector_inputs,
        input_fmt_fn=format_nutation_input,
        perf_fmt_fn=format_nutation_perf_input,
        accuracy_fn=compute_accuracy_metrics,
    )


def run_experiment_icrs_ecl_j2000(n: int, seed: int, run_perf: bool = True,
                                    perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the icrs_ecl_j2000 experiment: ICRS → Ecliptic J2000."""
    return _run_generic_experiment(
        exp_name="icrs_ecl_j2000", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_direction_vector_inputs,
        input_fmt_fn=format_icrs_ecl_j2000_input,
        perf_fmt_fn=format_icrs_ecl_j2000_perf_input,
        accuracy_fn=compute_accuracy_metrics,
    )


def run_experiment_icrs_ecl_tod(n: int, seed: int, run_perf: bool = True,
                                 perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the icrs_ecl_tod experiment: ICRS → Ecliptic of Date."""
    return _run_generic_experiment(
        exp_name="icrs_ecl_tod", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_equ_ecl_inputs,
        input_fmt_fn=format_icrs_ecl_tod_input,
        perf_fmt_fn=format_icrs_ecl_tod_perf_input,
        accuracy_fn=compute_angular_accuracy,
        accuracy_kwargs={"ra_key": "ecl_lon_rad", "dec_key": "ecl_lat_rad"},
    )


def run_experiment_horiz_to_equ(n: int, seed: int, run_perf: bool = True,
                                 perf_rounds: int = DEFAULT_PERF_ROUNDS, perf_scalar_n: int = SCALAR_WARM_N, perf_batch_n: int = BATCH_THROUGHPUT_N, perf_batch_rounds: int = BATCH_THROUGHPUT_ROUNDS, perf_warmup: int = DEFAULT_PERF_WARMUP, perf_timeout_s: int = 120):
    """Run the horiz_to_equ experiment: Horizontal → Equatorial."""
    return _run_generic_experiment(
        exp_name="horiz_to_equ", n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
        input_gen_fn=generate_horiz_to_equ_inputs,
        input_fmt_fn=format_horiz_to_equ_input,
        perf_fmt_fn=format_horiz_to_equ_perf_input,
        accuracy_fn=compute_angular_accuracy,
        accuracy_kwargs={"ra_key": "ra_rad", "dec_key": "dec_rad"},
    )


# 13 new matrix experiment runner functions
def _make_dir_experiment_runner(exp_name, fmt_input, fmt_perf_input):
    """Factory for direction-vector experiment runners."""
    def runner(n, seed, run_perf=True, perf_rounds=DEFAULT_PERF_ROUNDS, perf_scalar_n=SCALAR_WARM_N, perf_batch_n=BATCH_THROUGHPUT_N, perf_batch_rounds=BATCH_THROUGHPUT_ROUNDS, perf_warmup=DEFAULT_PERF_WARMUP, perf_timeout_s=120):
        return _run_generic_experiment(
            exp_name=exp_name, n=n, seed=seed, run_perf=run_perf, perf_rounds=perf_rounds, perf_scalar_n=perf_scalar_n, perf_batch_n=perf_batch_n, perf_batch_rounds=perf_batch_rounds, perf_warmup=perf_warmup, perf_timeout_s=perf_timeout_s,
            input_gen_fn=generate_direction_vector_inputs,
            input_fmt_fn=fmt_input,
            perf_fmt_fn=fmt_perf_input,
            accuracy_fn=compute_accuracy_metrics,
        )
    return runner

run_experiment_inv_frame_bias = _make_dir_experiment_runner("inv_frame_bias", format_inv_frame_bias_input, format_inv_frame_bias_perf_input)
run_experiment_inv_precession = _make_dir_experiment_runner("inv_precession", format_inv_precession_input, format_inv_precession_perf_input)
run_experiment_inv_nutation = _make_dir_experiment_runner("inv_nutation", format_inv_nutation_input, format_inv_nutation_perf_input)
run_experiment_inv_bpn = _make_dir_experiment_runner("inv_bpn", format_inv_bpn_input, format_inv_bpn_perf_input)
run_experiment_inv_icrs_ecl_j2000 = _make_dir_experiment_runner("inv_icrs_ecl_j2000", format_inv_icrs_ecl_j2000_input, format_inv_icrs_ecl_j2000_perf_input)
run_experiment_obliquity = _make_dir_experiment_runner("obliquity", format_obliquity_input, format_obliquity_perf_input)
run_experiment_inv_obliquity = _make_dir_experiment_runner("inv_obliquity", format_inv_obliquity_input, format_inv_obliquity_perf_input)
run_experiment_bias_precession = _make_dir_experiment_runner("bias_precession", format_bias_precession_input, format_bias_precession_perf_input)
run_experiment_inv_bias_precession = _make_dir_experiment_runner("inv_bias_precession", format_inv_bias_precession_input, format_inv_bias_precession_perf_input)
run_experiment_precession_nutation = _make_dir_experiment_runner("precession_nutation", format_precession_nutation_input, format_precession_nutation_perf_input)
run_experiment_inv_precession_nutation = _make_dir_experiment_runner("inv_precession_nutation", format_inv_precession_nutation_input, format_inv_precession_nutation_perf_input)
run_experiment_inv_icrs_ecl_tod_dir = _make_dir_experiment_runner("inv_icrs_ecl_tod", format_inv_icrs_ecl_tod_dir_input, format_inv_icrs_ecl_tod_dir_perf_input)
run_experiment_inv_equ_ecl_dir = _make_dir_experiment_runner("inv_equ_ecl", format_inv_equ_ecl_dir_input, format_inv_equ_ecl_dir_perf_input)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _display_path(path: Path) -> Path:
    """Return a repo-relative path when possible, otherwise the absolute path."""
    return path.relative_to(LAB_ROOT) if path.is_relative_to(LAB_ROOT) else path


def write_results(results: list, experiment: str, timestamp_str: str | None = None):
    """Write result JSON files and summary table."""
    # Use provided timestamp or generate new one (for backward compatibility)
    if timestamp_str is None:
        timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = RESULTS_DIR / timestamp_str / experiment
    out_dir.mkdir(parents=True, exist_ok=True)

    for r in results:
        lib = r.get("candidate_library", "unknown")
        profile = r.get("candidate_profile")
        file_stem = f"{lib}_{profile}" if profile and not (lib == "siderust" and profile == "iau2006a") else lib
        path = out_dir / f"{file_stem}.json"
        with open(path, "w") as f:
            json.dump(r, f, indent=2)
        print(f"  ✓ Wrote {_display_path(path)}")

    # Summary table
    summary = generate_summary_table(results)
    summary_path = out_dir / "summary.md"
    with open(summary_path, "w") as f:
        f.write(f"# {experiment} — Summary\n\n")
        f.write(f"Timestamp: {timestamp_str}\n\n")
        f.write(summary)
        f.write("\n## Alignment Checklist\n\n")
        if results:
            f.write("```json\n")
            json.dump(results[0].get("alignment", {}), f, indent=2)
            f.write("\n```\n")
    print(f"  ✓ Wrote {_display_path(summary_path)}")

    return out_dir


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _apply_ci_overrides(args) -> None:
    """Apply CI-mode overrides to argparse Namespace in-place.

    Only overrides values that are still the publication defaults.
    """
    # Reduce N if still default
    if getattr(args, "n", None) == 1000:
        args.n = 100
    # Reduce perf rounds if still default
    if getattr(args, "perf_rounds", None) == DEFAULT_PERF_ROUNDS:
        args.perf_rounds = 2
    # Reduce perf sizes/timeouts only when they are publication defaults
    if getattr(args, "perf_scalar_n", None) == SCALAR_WARM_N:
        args.perf_scalar_n = 500
    if getattr(args, "perf_batch_n", None) == BATCH_THROUGHPUT_N:
        args.perf_batch_n = 5000
    if getattr(args, "perf_batch_rounds", None) == BATCH_THROUGHPUT_ROUNDS:
        args.perf_batch_rounds = 1
    if getattr(args, "perf_timeout_s", None) == 120:
        args.perf_timeout_s = 30

    # No return; mutate in-place


def main():
    planet_experiments = list(PLANET_POSITION_EXPERIMENTS.keys())
    all_experiments = [
        "frame_rotation_bpn", "gmst_era", "equ_ecl", "equ_horizontal",
        "solar_position", "lunar_position", *planet_experiments, "kepler_solver",
        "solar_position_apparent", "lunar_position_apparent",
        "frame_bias", "precession", "nutation", "icrs_ecl_j2000",
        "icrs_ecl_tod", "horiz_to_equ",
        # 13 new matrix experiments
        "inv_frame_bias", "inv_precession", "inv_nutation", "inv_bpn",
        "inv_icrs_ecl_j2000", "obliquity", "inv_obliquity",
        "bias_precession", "inv_bias_precession",
        "precession_nutation", "inv_precession_nutation",
        "inv_icrs_ecl_tod", "inv_equ_ecl",
    ]

    parser = argparse.ArgumentParser(description="Siderust Lab Orchestrator")
    parser.add_argument("--experiment", default=None,
                        choices=all_experiments + ["all"],
                        help="(deprecated, use --experiments) Which experiment to run")
    parser.add_argument("--experiments", default=None,
                        help="Comma-separated list of experiments to run, or 'all'")
    parser.add_argument("--n", type=int, default=1000,
                        help="Number of test cases")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for input generation")
    parser.add_argument("--no-perf", action="store_true",
                        help="Skip performance tests")
    parser.add_argument("--perf-rounds", type=int, default=DEFAULT_PERF_ROUNDS,
                        help=f"Number of performance timing rounds (default: {DEFAULT_PERF_ROUNDS})")
    parser.add_argument("--perf-scalar-n", type=int, default=SCALAR_WARM_N,
                        help=f"Scalar workload size for latency (default: {SCALAR_WARM_N})")
    parser.add_argument("--perf-batch-n", type=int, default=BATCH_THROUGHPUT_N,
                        help=f"Batch workload size for throughput (default: {BATCH_THROUGHPUT_N})")
    parser.add_argument("--perf-batch-rounds", type=int, default=BATCH_THROUGHPUT_ROUNDS,
                        help=f"Number of timing rounds for batch throughput (default: {BATCH_THROUGHPUT_ROUNDS})")
    parser.add_argument("--perf-warmup", type=int, default=DEFAULT_PERF_WARMUP,
                        help=f"Number of warmup iterations (default: {DEFAULT_PERF_WARMUP})")
    parser.add_argument("--perf-timeout-s", type=int, default=120,
                        help="Timeout in seconds for each adapter performance round (default: 120)")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: fewer rounds, smaller N for faster execution")
    parser.add_argument("--no-build", action="store_true",
                        help="Skip automatic rebuild of Rust adapters (siderust/anise)")
    parser.add_argument("--adapters", default=None,
                        help="Comma-separated candidate adapters to run (siderust,astropy,libnova,anise)")
    parser.add_argument("--siderust-profiles", default="iau2006a",
                        help="Comma-separated Siderust nutation profiles: iau2006a, iau2000a, iau2000b, precession_only")
    parser.add_argument("--horizons-no-cache", action="store_true",
                        help="Do not read/write the Horizons cache")
    parser.add_argument("--horizons-offline", action="store_true",
                        help="Require cached Horizons reference data; never contact the network")
    parser.add_argument("--output-dir", default="results",
                        help="Output directory for run artifacts (default: results)")
    parser.add_argument("--publish-latest", action="store_true",
                        help="Copy the completed run to latest_results/")
    parser.add_argument("--allow-dirty-publish", action="store_true",
                        help="Allow publish-latest when git_dirty.lab is true")
    parser.add_argument("--allow-partial-publish", action="store_true",
                        help="Allow publish-latest when scope.partial is true")
    parser.add_argument("--run-label", default=None,
                        help="Human-readable run label written to the manifest")
    parser.add_argument("--run-phase", default=None,
                        help="Plan phase label written to the manifest")
    parser.add_argument("--run-tags", default="",
                        help="Comma-separated run tags written to the manifest")
    args = parser.parse_args()
    # Apply CI-mode overrides (only when requested)
    if args.ci:
        _apply_ci_overrides(args)


    adapters = [a.strip() for a in args.adapters.split(",") if a.strip()] if args.adapters else None
    siderust_profiles = [p.strip() for p in args.siderust_profiles.split(",") if p.strip()]
    run_tags = [t.strip() for t in args.run_tags.split(",") if t.strip()]
    configure_run(
        adapters=adapters,
        siderust_profiles=siderust_profiles,
        horizons_use_cache=not args.horizons_no_cache,
        horizons_allow_network=not args.horizons_offline,
        output_dir=args.output_dir,
    )

    if not args.no_build:
        ensure_rust_adapters_built()

    # Resolve which experiments to run (--experiments takes precedence)
    raw = args.experiments or args.experiment or "all"
    if raw == "all":
        experiments_to_run = all_experiments
    else:
        experiments_to_run = [e.strip() for e in raw.split(",") if e.strip()]

    # Generate single timestamp for this entire run
    run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

    # Print run configuration banner
    run_perf = not args.no_perf
    print(f"\n{'='*70}")
    print(f" Siderust Lab — Benchmark Run")
    print(f"{'='*70}")
    print(f"  Timestamp:     {run_timestamp}")
    print(f"  Experiments:   {', '.join(experiments_to_run)}")
    print(f"  N (cases):     {args.n}")
    print(f"  Seed:          {args.seed}")
    if run_perf:
        print(f"  Performance:   enabled ({args.perf_rounds} rounds)")
        print(f"    rounds:       {args.perf_rounds}")
        print(f"    scalar_n:     {args.perf_scalar_n}")
        print(f"    batch_n:      {args.perf_batch_n}")
        print(f"    batch_rounds: {args.perf_batch_rounds}")
        print(f"    warmup:       {args.perf_warmup}")
        print(f"    timeout_s:    {args.perf_timeout_s}")
    else:
        print(f"  Performance:   disabled")
    print(f"  CI mode:       {'yes' if args.ci else 'no'}")
    print(f"  Adapters:      {', '.join(adapters or ['siderust', 'astropy', 'libnova', 'anise'])}")
    print(f"  Siderust:      {', '.join(SIDERUST_PROFILES)}")
    print(f"  Horizons:      cache={'yes' if HORIZONS_USE_CACHE else 'no'}, network={'yes' if HORIZONS_ALLOW_NETWORK else 'no'}")
    print(f"  Output dir:    {_display_path(RESULTS_DIR)}")
    if args.run_label or args.run_phase or run_tags:
        print(f"  Run label:     {args.run_label or '-'}")
        print(f"  Run phase:     {args.run_phase or '-'}")
        print(f"  Run tags:      {', '.join(run_tags) if run_tags else '-'}")
    print(f"{'='*70}\n")

    all_results = []

    dispatch = {
        "frame_rotation_bpn": lambda: run_experiment_frame_rotation_bpn(args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "gmst_era": lambda: run_experiment_gmst_era(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "equ_ecl": lambda: run_experiment_equ_ecl(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "equ_horizontal": lambda: run_experiment_equ_horizontal(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "solar_position": lambda: run_experiment_solar_position(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "solar_position_apparent": lambda: run_experiment_solar_position(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s,
            exp_name="solar_position_apparent",
        ),
        "lunar_position": lambda: run_experiment_lunar_position(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "lunar_position_apparent": lambda: run_experiment_lunar_position(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s,
            exp_name="lunar_position_apparent",
        ),
        "kepler_solver": lambda: run_experiment_kepler_solver(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "frame_bias": lambda: run_experiment_frame_bias(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "precession": lambda: run_experiment_precession(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "nutation": lambda: run_experiment_nutation(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "icrs_ecl_j2000": lambda: run_experiment_icrs_ecl_j2000(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "icrs_ecl_tod": lambda: run_experiment_icrs_ecl_tod(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        "horiz_to_equ": lambda: run_experiment_horiz_to_equ(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        ),
        # 13 new matrix experiments
        "inv_frame_bias": lambda: run_experiment_inv_frame_bias(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_precession": lambda: run_experiment_inv_precession(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_nutation": lambda: run_experiment_inv_nutation(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_bpn": lambda: run_experiment_inv_bpn(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_icrs_ecl_j2000": lambda: run_experiment_inv_icrs_ecl_j2000(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "obliquity": lambda: run_experiment_obliquity(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_obliquity": lambda: run_experiment_inv_obliquity(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "bias_precession": lambda: run_experiment_bias_precession(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_bias_precession": lambda: run_experiment_inv_bias_precession(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "precession_nutation": lambda: run_experiment_precession_nutation(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_precession_nutation": lambda: run_experiment_inv_precession_nutation(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_icrs_ecl_tod": lambda: run_experiment_inv_icrs_ecl_tod_dir(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
        "inv_equ_ecl": lambda: run_experiment_inv_equ_ecl_dir(
            args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s),
    }

    for exp_name in planet_experiments:
        dispatch[exp_name] = lambda exp_name=exp_name: run_experiment_planet_position(
            exp_name, args.n, args.seed, run_perf=run_perf, perf_rounds=args.perf_rounds, perf_scalar_n=args.perf_scalar_n, perf_batch_n=args.perf_batch_n, perf_batch_rounds=args.perf_batch_rounds, perf_warmup=args.perf_warmup, perf_timeout_s=args.perf_timeout_s
        )

    total_experiments = len(experiments_to_run)
    for exp_idx, exp in enumerate(experiments_to_run, 1):
        progress(f"Experiment {exp_idx}/{total_experiments}: {exp}",
                 step="experiment_start", current_step=exp_idx, total_steps=total_experiments)

        runner_fn = dispatch.get(exp)
        if runner_fn is None:
            print(f"Unknown experiment: {exp}", file=sys.stderr)
            continue

        results = runner_fn()

        if results:
            write_results(results, exp, run_timestamp)
            all_results.extend(results)

            # Print summary
            print(f"\n{'─'*70}")
            print(f" Results Summary: {exp}")
            print(f"{'─'*70}")
            for r in results:
                lib = r.get("candidate_library", "?")
                ref = r.get("reference_library", "erfa")
                acc = r.get("accuracy", {})

                ang = acc.get("angular_error_mas", {})
                if ang.get("p50") is not None:
                    print(f"  {lib} vs {ref}:")
                    print(f"    Angular error (mas): p50={ang['p50']:.3f}  p99={ang['p99']:.3f}  max={ang['max']:.3f}")

                gmst = acc.get("gmst_error_arcsec", {})
                if gmst.get("p50") is not None:
                    print(f"  {lib} vs {ref}:")
                    print(f"    GMST error (arcsec): p50={gmst['p50']:.6f}  p99={gmst['p99']:.6f}  max={gmst['max']:.6f}")

                sep = acc.get("angular_sep_arcsec", {})
                if sep.get("p50") is not None:
                    print(f"  {lib} vs {ref}:")
                    print(f"    Angular sep (arcsec): p50={sep['p50']:.4f}  p99={sep['p99']:.4f}  max={sep['max']:.4f}")

                E_err = acc.get("E_error_rad", {})
                if E_err.get("p50") is not None:
                    con = acc.get("consistency_error_rad", {})
                    print(f"  {lib} vs {ref}:")
                    print(f"    E error (rad): p50={E_err['p50']:.2e}  max={E_err['max']:.2e}  consistency max={con.get('max', 0):.2e}")

                perf = r.get("performance", {})
                if perf.get("per_op_ns"):
                    ns = perf["per_op_ns"]
                    ops = perf.get("throughput_ops_s", 0)
                    cv = perf.get("per_op_ns_cv_pct", 0)
                    rounds = perf.get("rounds", 1)
                    print(f"    Performance: {ns:.0f} ns/op (median, {rounds} rounds, CV={cv:.1f}%)")
                    if perf.get("warnings"):
                        for w in perf["warnings"]:
                            print(f"    ⚠ {w}")

    if all_results:
        # Write combined summary
        summary = generate_summary_table(all_results)
        print(f"\n{'='*70}")
        print(" Combined Summary Table")
        print(f"{'='*70}")
        print(summary)

        # Write run manifest with completeness tracking
        completed_experiments = sorted(set(r["experiment"] for r in all_results))
        completed_libraries = sorted(set(
            f"{r['candidate_library']}:{r['candidate_profile']}"
            if r.get("candidate_profile") and not (r["candidate_library"] == "siderust" and r["candidate_profile"] == "iau2006a")
            else r["candidate_library"]
            for r in all_results
        ))
        missing_experiments = sorted(set(experiments_to_run) - set(completed_experiments))

        experiment_completeness = summarize_experiment_completeness(all_results)

        for exp_id, entry in experiment_completeness.items():
            blocked = runtime_blocked_for(exp_id)
            if blocked:
                entry["excluded_candidates"] = [
                    {"candidate_id": cid, "support_status": "runtime-blocked", "reason": reason}
                    for _label, cid, reason in blocked
                ]

        scope = _run_scope(experiments_to_run, completed_experiments)
        if args.run_label:
            scope["run_label"] = args.run_label
        if args.run_phase:
            scope["run_phase"] = args.run_phase
        if run_tags:
            scope["run_tags"] = run_tags

        pub_blockers = _validate_publish_latest(
            scope, run_metadata(),
            perf_enabled=run_perf,
            perf_rounds=args.perf_rounds,
            perf_scalar_n=args.perf_scalar_n,
            perf_batch_n=args.perf_batch_n,
            perf_batch_rounds=args.perf_batch_rounds,
            perf_warmup=args.perf_warmup,
        )
        publication = {
            "grade": "publication" if not pub_blockers else "draft",
            "publish_blockers": pub_blockers,
            "git_dirty": run_metadata().get("git_dirty"),
            "allow_dirty_override": bool(args.allow_dirty_publish),
            "allow_partial_override": bool(args.allow_partial_publish),
        }

        manifest = {
            "run_id": run_timestamp,
            "config": {
                "run_label": args.run_label,
                "run_phase": args.run_phase,
                "run_tags": run_tags,
                "experiments": experiments_to_run,
                "n": args.n,
                "seed": args.seed,
                "perf_enabled": run_perf,
                "perf_rounds": args.perf_rounds,
                "perf_scalar_n": args.perf_scalar_n,
                "perf_batch_n": args.perf_batch_n,
                "perf_batch_rounds": args.perf_batch_rounds,
                "perf_warmup": args.perf_warmup,
                "perf_timeout_s": args.perf_timeout_s,
                "ci_mode": args.ci,
                "adapters": adapters or ["siderust", "astropy", "libnova", "anise"],
                "siderust_profiles": SIDERUST_PROFILES,
                "horizons_use_cache": HORIZONS_USE_CACHE,
                "horizons_allow_network": HORIZONS_ALLOW_NETWORK,
            },
            "scope": scope,
            "publication": publication,
            "latest_results_merge": {"is_merge": False},
            "labels": {
                "run_label": args.run_label,
                "run_phase": args.run_phase,
                "run_tags": run_tags,
            },
            "metadata": run_metadata(),
            "completeness": {
                "requested": len(experiments_to_run),
                "completed": len(completed_experiments),
                "missing": missing_experiments,
                "completed_experiments": completed_experiments,
                "libraries": completed_libraries,
                "per_experiment": experiment_completeness,
            },
            "experiment_count": len(completed_experiments),
            "total_results": len(all_results),
        }
        manifest_path = RESULTS_DIR / run_timestamp / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"\n  ✓ Run manifest: {_display_path(manifest_path)}")

        if args.publish_latest:
            if pub_blockers and not _publish_overrides_satisfy(
                pub_blockers,
                allow_dirty=args.allow_dirty_publish,
                allow_partial=args.allow_partial_publish,
            ):
                print(
                    "\n  ✗ Refusing publish-latest (not publication-grade):",
                    flush=True,
                )
                for b in pub_blockers:
                    print(f"      - {b}", flush=True)
                print(
                    "    Re-run with --allow-dirty-publish and/or --allow-partial-publish "
                    "to copy anyway; the manifest will label the artifact as draft.",
                    flush=True,
                )
                raise SystemExit(2)
            latest_dir = LAB_ROOT / "latest_results"
            source_dir = RESULTS_DIR / run_timestamp
            if latest_dir.exists():
                shutil.rmtree(latest_dir)
            shutil.copytree(source_dir, latest_dir)
            grade = publication.get("grade", "draft")
            print(
                f"  ✓ Published latest artifact ({grade}): "
                f"{_display_path(latest_dir)}"
            )
if __name__ == "__main__":
    main()
