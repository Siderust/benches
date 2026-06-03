"""Scorecard computation over raw JSON result rows.

Mirrors the logic that used to live in webapp/backend/app/services/results_loader.py
but operates on plain dicts so it can be invoked from the static export script
without pulling in pydantic.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:_\d{2}-\d{2}-\d{2})?$")

_PRIMARY_METRICS: list[tuple[str, str, str]] = [
    ("angular_error_mas", "Angular Error", "mas"),
    ("gmst_error_arcsec", "GMST Error", "arcsec"),
    ("angular_sep_arcsec", "Angular Separation", "arcsec"),
    ("E_error_rad", "Kepler E Error", "rad"),
    ("consistency_error_rad", "Consistency Error", "rad"),
]


def _result_key(row: dict[str, Any]) -> str:
    lib = row.get("candidate_library", "?")
    prof = row.get("candidate_profile")
    if prof and not (lib == "siderust" and prof == "iau2006a"):
        return f"{lib}/{prof}"
    return lib


def _primary_metric(row: dict[str, Any]) -> dict[str, Any]:
    accuracy = row.get("accuracy") or {}
    for key, label, unit in _PRIMARY_METRICS:
        stats = accuracy.get(key)
        if isinstance(stats, dict):
            return {"key": key, "label": label, "unit": unit, "stats": stats}
    return {"key": "", "label": "Error", "unit": "", "stats": {}}


def _accuracy_rank_key(row: dict[str, Any]) -> tuple:
    """Lower-is-better rank tuple for accuracy winner selection.

    Order: p99 → max → rms → mean → p50 → display_name (lexicographic tie-break).
    A ``None`` value sorts after any finite value so missing stats never crown a
    candidate over one that has measured data.
    """
    def _v(x: Any) -> tuple:
        return (1, 0.0) if x is None else (0, abs(float(x)))

    return (
        _v(row.get("p99")),
        _v(row.get("max")),
        _v(row.get("rms")),
        _v(row.get("mean")),
        _v(row.get("p50")),
        row.get("display_name") or "",
    )


def _perf_workloads(perf: Any) -> dict[str, Any]:
    """Return Phase-6 workload shape, accepting legacy flat perf rows."""
    empty = {"scalar_warm": None, "batch_throughput": None, "setup_metrics": None}
    if not isinstance(perf, dict):
        return empty
    if any(k in perf for k in empty):
        return {k: perf.get(k) for k in empty}
    if "per_op_ns" in perf:
        scalar = {
            "ns_per_op": perf.get("per_op_ns"),
            "cv": perf.get("per_op_ns_cv_pct"),
            "rounds": perf.get("rounds"),
            "n_per_round": perf.get("batch_size"),
            "valid": perf.get("valid"),
            "warnings": perf.get("warnings") or [],
        }
        return {"scalar_warm": scalar, "batch_throughput": None, "setup_metrics": None}
    return empty


RANKABLE_COMPARABILITY = frozenset({"exact-model", "same-family-jpl", "best-available"})


def _accuracy_rank_eligible(row: dict[str, Any]) -> bool:
    """Strict gate for accuracy crowns (matches publication policy)."""
    if row.get("status") != "ok":
        return False
    if row.get("rankable_accuracy") is not True:
        return False
    if row.get("support_status") != "supported":
        return False
    if row.get("api_surface") != "public":
        return False
    cc = row.get("comparability_class")
    return cc in RANKABLE_COMPARABILITY


def _performance_rank_eligible(row: dict[str, Any]) -> bool:
    if row.get("status") != "ok":
        return False
    if row.get("support_status") != "supported":
        return False
    if row.get("api_surface") != "public":
        return False
    return True


def _perf_valid(perf: dict[str, Any] | None) -> bool:
    if not isinstance(perf, dict):
        return False
    ns = perf.get("ns_per_op", perf.get("per_op_ns"))
    cv = perf.get("cv", perf.get("per_op_ns_cv_pct"))
    if ns is None or perf.get("valid") is False:
        return False
    if isinstance(ns, (int, float)) and ns < 10.0:
        return False
    if isinstance(cv, (int, float)) and cv > 20.0:
        return False
    return True


def discover_runs(lab_root: Path) -> list[tuple[str, Path]]:
    """Return [(run_id, run_dir), ...] sorted newest-first.

    Also exposes the `latest_results/` copy as `id == "latest"` if present.

    Run directories without a ``manifest.json`` are excluded — they are
    assumed to be partial or interrupted runs and should not appear in the
    dashboard.  The "latest" directory is always included even when its
    manifest is missing (it is a mirror, not a raw dated run).
    """
    out: list[tuple[str, Path]] = []
    results_dir = lab_root / "results"
    if results_dir.is_dir():
        for d in sorted(results_dir.iterdir(), reverse=True):
            if d.is_dir() and _DATE_RE.match(d.name):
                if (d / "manifest.json").is_file():
                    out.append((d.name, d))
    latest = lab_root / "latest_results"
    if latest.is_dir():
        out.append(("latest", latest))
    return out


def load_run(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Read every <experiment>/<candidate>.json under run_dir."""
    experiments: dict[str, list[dict[str, Any]]] = {}
    if not run_dir.is_dir():
        return experiments
    for exp_dir in sorted(run_dir.iterdir()):
        if not exp_dir.is_dir():
            continue
        rows: list[dict[str, Any]] = []
        for f in sorted(exp_dir.glob("*.json")):
            try:
                rows.append(json.loads(f.read_text()))
            except Exception:
                continue
        if rows:
            experiments[exp_dir.name] = rows
    return experiments


def _run_metadata(experiments: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    timestamp = git_shas = machine = None
    for rows in experiments.values():
        for r in rows:
            meta = r.get("run_metadata") or {}
            if not timestamp and meta.get("date"):
                timestamp = meta["date"]
            if not git_shas and meta.get("git_shas"):
                git_shas = meta["git_shas"]
            if not machine:
                parts = [meta.get("cpu"), meta.get("os")]
                parts = [p for p in parts if p]
                machine = " / ".join(parts) if parts else None
            if timestamp and git_shas and machine:
                break
    return {"timestamp": timestamp, "git_shas": git_shas or {}, "machine": machine}


def compute_scorecard(run_id: str, experiments: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Build a public, rankability-aware scorecard for one run (dict form)."""
    meta = _run_metadata(experiments)
    family_map: dict[str, dict[str, Any]] = {}
    public_results: list[dict[str, Any]] = []

    for experiment, rows in experiments.items():
        visible = [r for r in rows if (r.get("tier") or "public") == "public"]
        if not visible:
            continue

        family = visible[0].get("family") or "uncategorized"
        family_block = family_map.setdefault(family, {
            "family": family,
            "experiments": [],
            "accuracy_wins": {},
            "performance_wins": {},
        })

        out_rows = []
        best_accuracy = None
        best_performance = None
        raw_fastest = None
        # Use the first row with non-empty accuracy to determine the metric
        # label and unit.  If all rows are skipped/failed (empty accuracy), fall
        # back to the first row in the list so we still produce some label.
        metric_meta = next(
            (_primary_metric(r) for r in visible if r.get("accuracy")),
            _primary_metric(visible[0]),
        )

        for r in visible:
            metric = _primary_metric(r)
            stats = metric["stats"]
            p99 = stats.get("p99")
            perf = _perf_workloads(r.get("performance"))
            scalar_perf = perf.get("scalar_warm")
            batch_perf = perf.get("batch_throughput")
            setup_perf = perf.get("setup_metrics")
            ns = scalar_perf.get("ns_per_op") if isinstance(scalar_perf, dict) else None
            alignment = r.get("alignment") or {}
            row = {
                "library": r.get("candidate_library"),
                "display_name": _result_key(r),
                "profile": r.get("candidate_profile"),
                "rankable_accuracy": r.get("rankable_accuracy") is True,
                "rank_exclusion_reason": r.get("rank_exclusion_reason"),
                "candidate_parity": alignment.get("candidate_parity"),
                "comparability_class": r.get("comparability_class")
                    or ("exact-model" if r.get("rankable_accuracy") is True else "not-comparable"),
                "model_parity_class": alignment.get("candidate_parity_class")
                    or alignment.get("default_model_parity_class")
                    or alignment.get("model_parity_class"),
                "selected_model": r.get("selected_model") or r.get("model"),
                "model_source": r.get("model_source"),
                "lane": r.get("lane") or alignment.get("lane"),
                "api_surface": r.get("api_surface"),
                "support_status": r.get("support_status"),
                "candidate_id": r.get("candidate_id"),
                "catalog_model": r.get("catalog_model"),
                "catalog_source": r.get("catalog_source"),
                "catalog_lane": r.get("catalog_lane"),
                "catalog_parity": r.get("catalog_parity"),
                "status": r.get("status") or "ok",
                "skip_reason": r.get("skip_reason"),
                "failure_reason": r.get("failure_reason"),
                "p50": stats.get("p50"),
                "p99": p99,
                "max": stats.get("max"),
                "rms": stats.get("rms"),
                "mean": stats.get("mean"),
                "ns_per_op": ns,
                "scalar_warm_ns_per_op": ns,
                "scalar_warm_cv": scalar_perf.get("cv") if isinstance(scalar_perf, dict) else None,
                "batch_throughput_ns_per_op": batch_perf.get("ns_per_op") if isinstance(batch_perf, dict) else None,
                "batch_throughput_items_per_sec": batch_perf.get("items_per_sec") if isinstance(batch_perf, dict) else None,
                "setup_ms": setup_perf.get("setup_ms") if isinstance(setup_perf, dict) else None,
                "setup_measured": setup_perf.get("measured") if isinstance(setup_perf, dict) else None,
                "performance": perf,
                "perf_valid": _perf_valid(scalar_perf),
                "perf_cv_pct": scalar_perf.get("cv") if isinstance(scalar_perf, dict) else None,
                "perf_warnings": scalar_perf.get("warnings") if isinstance(scalar_perf, dict) else [],
                "source_provenance": r.get("source_provenance"),
                "reference_source_tag": r.get("reference_source_tag"),
            }
            out_rows.append(row)
            public_results.append(r)

            if _accuracy_rank_eligible(row) and isinstance(p99, (int, float)):
                if best_accuracy is None or _accuracy_rank_key(row) < _accuracy_rank_key(best_accuracy):
                    best_accuracy = row
            # Performance crown (audit issue #3): the *statistically valid*
            # winner (best_performance) only considers rows that pass
            # `perf_valid` (finite ns ≥ 10ns/op, CV ≤ 20%, valid != false).
            # `raw_fastest` records the raw minimum regardless of validity so
            # the dashboard can show it as a diagnostic without ever conflating
            # it with the trustworthy winner.
            if isinstance(ns, (int, float)) and math.isfinite(ns) and ns > 0:
                if raw_fastest is None or ns < raw_fastest["ns_per_op"]:
                    raw_fastest = row
                if row["perf_valid"] and _performance_rank_eligible(row):
                    if best_performance is None or ns < best_performance["ns_per_op"]:
                        best_performance = row

        # Exact-model-only winner: subset of rankable rows whose
        # comparability_class is `exact-model`. Used by the UI's "Exact model
        # only" filter toggle so best-available cross-model rankings can be
        # hidden when a stricter view is requested.
        best_accuracy_exact = None
        for row in out_rows:
            if (
                _accuracy_rank_eligible(row)
                and row["comparability_class"] == "exact-model"
                and isinstance(row["p99"], (int, float))
            ):
                if best_accuracy_exact is None or _accuracy_rank_key(row) < _accuracy_rank_key(best_accuracy_exact):
                    best_accuracy_exact = row

        # Co-winner detection: rows whose p99 is within a small relative
        # tolerance of the winner are reported as ties so a "crown" never
        # implies false superiority when results are numerically
        # indistinguishable. Audit fix F6.
        def _co_winners(winner, pool, *, restrict_exact: bool) -> list[str]:
            if winner is None:
                return []
            w_p99 = winner.get("p99")
            if not isinstance(w_p99, (int, float)):
                return []
            tol_abs = max(abs(w_p99) * 1e-3, 1e-12)
            out = []
            for r in pool:
                if not _accuracy_rank_eligible(r):
                    continue
                if restrict_exact and r["comparability_class"] != "exact-model":
                    continue
                p = r.get("p99")
                if not isinstance(p, (int, float)):
                    continue
                if abs(abs(p) - abs(w_p99)) <= tol_abs:
                    out.append(r["display_name"])
            return sorted(set(out))

        best_accuracy_co_winners = _co_winners(best_accuracy, out_rows, restrict_exact=False)
        best_accuracy_exact_co_winners = _co_winners(best_accuracy_exact, out_rows, restrict_exact=True)

        for row in out_rows:
            if best_accuracy and _accuracy_rank_eligible(row) and isinstance(row["p99"], (int, float)):
                row["accuracy_delta_vs_best"] = abs(row["p99"]) - abs(best_accuracy["p99"])
            else:
                row["accuracy_delta_vs_best"] = None
            if best_performance and isinstance(row["ns_per_op"], (int, float)) and math.isfinite(row["ns_per_op"]):
                row["performance_delta_vs_best_pct"] = (
                    (row["ns_per_op"] / best_performance["ns_per_op"]) - 1.0
                ) * 100.0
            else:
                row["performance_delta_vs_best_pct"] = None

        if best_accuracy:
            family_block["accuracy_wins"][best_accuracy["display_name"]] = (
                family_block["accuracy_wins"].get(best_accuracy["display_name"], 0) + 1
            )
        if best_performance:
            family_block["performance_wins"][best_performance["display_name"]] = (
                family_block["performance_wins"].get(best_performance["display_name"], 0) + 1
            )

        first = visible[0]
        desc = first.get("description") or {}
        if isinstance(desc, dict):
            title = desc.get("title") or experiment
        else:
            title = getattr(desc, "title", experiment)
        alignment0 = first.get("alignment") or {}

        family_block["experiments"].append({
            "experiment": experiment,
            "title": title,
            "reference_library": first.get("reference_library"),
            "reference_model": first.get("reference_model"),
            "reference_lane": alignment0.get("lane") or first.get("reference_lane"),
            "tier": first.get("tier") or "public",
            "metric": {
                "key": metric_meta["key"],
                "label": metric_meta["label"],
                "unit": metric_meta["unit"],
            },
            "rows": out_rows,
            "best_accuracy": best_accuracy["display_name"] if best_accuracy else None,
            "best_accuracy_exact": best_accuracy_exact["display_name"] if best_accuracy_exact else None,
            "best_accuracy_co_winners": best_accuracy_co_winners,
            "best_accuracy_exact_co_winners": best_accuracy_exact_co_winners,
            "best_performance": best_performance["display_name"] if best_performance else None,
            "raw_fastest": raw_fastest["display_name"] if raw_fastest else None,
        })

    references = sorted({
        (r.get("reference_model") or r.get("reference_library"))
        for r in public_results
        if r.get("reference_model") or r.get("reference_library")
    })
    return {
        "run_id": run_id,
        "timestamp": meta["timestamp"],
        "machine": meta["machine"],
        "git_shas": meta["git_shas"],
        "references": references,
        "families": list(family_map.values()),
    }


def compute_summaries(runs: Iterable[tuple[str, Path]]) -> list[dict[str, Any]]:
    """Lightweight summaries for the runs index."""
    out: list[dict[str, Any]] = []
    for run_id, run_dir in runs:
        experiments = load_run(run_dir)
        if not experiments:
            continue
        meta = _run_metadata(experiments)
        all_rows = [r for rows in experiments.values() for r in rows]
        libraries = sorted({r.get("candidate_library") for r in all_rows if r.get("candidate_library")})
        out.append({
            "id": run_id,
            "timestamp": meta["timestamp"],
            "git_shas": meta["git_shas"],
            "machine": meta["machine"],
            "experiments": sorted(experiments.keys()),
            "libraries": libraries,
            "result_count": len(all_rows),
        })
    return out
