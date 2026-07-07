"""Validated baseline result reuse for Siderust Lab.

Baselines are fingerprinted, inspectable artifacts — not ad-hoc merges of
``latest_results``.  Composition is a first-class pipeline mode with provenance
recorded on every result row and in the run manifest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

try:
    from .catalog import CATALOG_PATH, CandidateEntry, default_registry
except ImportError:  # pragma: no cover - direct script path
    from catalog import CATALOG_PATH, CandidateEntry, default_registry  # type: ignore[no-redef]

BASELINE_SCHEMA_VERSION = 1
BENCHMARK_CONTRACT_VERSION = 1
RESULT_SCHEMA_VERSION = 1

ReusePerformance = bool | Literal["same-machine-only"]


@dataclass(frozen=True)
class BaselinePolicy:
    enabled: bool
    root: Path
    reuse_candidates: frozenset[str]
    refresh_candidates: frozenset[str]
    reuse_accuracy: bool
    reuse_performance: ReusePerformance
    require_complete_baselines: bool
    write_missing_baselines: bool
    refresh_all: bool = False


@dataclass(frozen=True)
class ConvergenceConfig:
    enabled: bool
    stages: tuple[int, ...]
    primary_metric: str
    relative_tolerance: float
    absolute_tolerance: float
    stop_after_stable_stages: int


@dataclass(frozen=True)
class RunFingerprints:
    input: str
    reference: str
    catalog_entry: str
    catalog_file: str
    benchmark_contract: str
    workload: str
    machine: str
    candidate_adapters: dict[str, str]
    kernel_hashes: dict[str, str]
    suite: str | None = None
    n: int = 0
    seed: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "reference": self.reference,
            "catalog_entry": self.catalog_entry,
            "catalog_file": self.catalog_file,
            "benchmark_contract": self.benchmark_contract,
            "workload": self.workload,
            "machine": self.machine,
            "candidate_adapters": self.candidate_adapters,
            "kernel_hashes": self.kernel_hashes,
            "suite": self.suite,
            "n": self.n,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class BaselineValidation:
    valid: bool
    reason: str | None
    key: str | None
    artifact_path: Path | None
    reuse_kind: Literal["accuracy", "performance", "combined"] | None = None


@dataclass
class CompositionState:
    mode: Literal["fresh", "baseline_delta"]
    fresh_candidates: list[str] = field(default_factory=list)
    baseline_candidates: list[str] = field(default_factory=list)
    baseline_root: str | None = None
    reuse_accuracy: bool = False
    reuse_performance: ReusePerformance = False
    all_baselines_valid: bool = True
    missing_baselines: list[str] = field(default_factory=list)
    stale_baselines: list[str] = field(default_factory=list)
    refresh_all: bool = False

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "fresh_candidates": sorted(set(self.fresh_candidates)),
            "baseline_candidates": sorted(set(self.baseline_candidates)),
            "baseline_root": self.baseline_root,
            "reuse_accuracy": self.reuse_accuracy,
            "reuse_performance": self.reuse_performance,
            "all_baselines_valid": self.all_baselines_valid,
            "missing_baselines": sorted(set(self.missing_baselines)),
            "stale_baselines": sorted(set(self.stale_baselines)),
            "refresh_all": self.refresh_all,
        }


def _sha256_hex(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_reuse_performance(value: Any) -> ReusePerformance:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "no", "off"}:
            return False
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized == "same-machine-only":
            return "same-machine-only"
    raise ValueError(
        "baselines.reuse_performance must be false, true, or 'same-machine-only'"
    )


def parse_baseline_policy(
    raw: dict[str, Any] | None,
    *,
    lab_root: Path,
    refresh_all: bool = False,
) -> BaselinePolicy:
    section = raw or {}
    enabled = bool(section.get("enabled", False))
    root_raw = str(section.get("root", ".benches_cache/baseline_results"))
    root = Path(root_raw)
    if not root.is_absolute():
        root = (lab_root / root).resolve()

    def _candidate_set(key: str) -> frozenset[str]:
        value = section.get(key)
        if value is None:
            return frozenset()
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            raise ValueError(f"baselines.{key} must be a string or list")
        return frozenset(items)

    return BaselinePolicy(
        enabled=enabled,
        root=root,
        reuse_candidates=_candidate_set("reuse_candidates"),
        refresh_candidates=_candidate_set("refresh_candidates"),
        reuse_accuracy=bool(section.get("reuse_accuracy", True)),
        reuse_performance=parse_reuse_performance(section.get("reuse_performance", False)),
        require_complete_baselines=bool(section.get("require_complete_baselines", False)),
        write_missing_baselines=bool(section.get("write_missing_baselines", True)),
        refresh_all=refresh_all,
    )


def parse_convergence_config(raw: dict[str, Any] | None) -> ConvergenceConfig:
    section = raw or {}
    stages_raw = section.get("stages", [50, 100, 250, 1000])
    if isinstance(stages_raw, list):
        stages = tuple(int(x) for x in stages_raw)
    else:
        raise ValueError("convergence.stages must be a list of integers")
    return ConvergenceConfig(
        enabled=bool(section.get("enabled", False)),
        stages=stages,
        primary_metric=str(section.get("primary_metric", "p99")),
        relative_tolerance=float(section.get("relative_tolerance", 0.02)),
        absolute_tolerance=float(section.get("absolute_tolerance", 1e-12)),
        stop_after_stable_stages=int(section.get("stop_after_stable_stages", 2)),
    )


def matches_candidate_pattern(candidate_id: str, patterns: frozenset[str]) -> bool:
    if not patterns:
        return False
    if "*" in patterns:
        return True
    if candidate_id in patterns:
        return True
    for pat in patterns:
        if candidate_id == pat or candidate_id.startswith(f"{pat}:"):
            return True
    return False


def should_refresh_candidate(candidate_id: str, policy: BaselinePolicy) -> bool:
    if not policy.enabled:
        return True
    if policy.refresh_all:
        return True
    if matches_candidate_pattern(candidate_id, policy.refresh_candidates):
        return True
    return False


def should_attempt_baseline_reuse(candidate_id: str, policy: BaselinePolicy) -> bool:
    if not policy.enabled or policy.refresh_all:
        return False
    if should_refresh_candidate(candidate_id, policy):
        return False
    if not policy.reuse_candidates:
        return False
    return matches_candidate_pattern(candidate_id, policy.reuse_candidates)


def compute_catalog_file_fingerprint(path: Path = CATALOG_PATH) -> str:
    if not path.is_file():
        return "missing"
    return _sha256_file(path)[:16]


def compute_catalog_entry_fingerprint(entry: CandidateEntry | None) -> str:
    if entry is None:
        return "missing"
    payload = {
        "id": entry.id,
        "experiment": entry.experiment,
        "api_surface": entry.api_surface,
        "api_method": entry.api_method,
        "model": entry.model,
        "source": entry.source,
        "lane": entry.lane,
        "parity": entry.parity,
        "support": entry.support,
        "exclusion_reason": entry.exclusion_reason,
    }
    return _sha256_hex(payload)[:16]


def compute_input_fingerprint(
    *,
    experiment: str,
    n: int,
    seed: int,
    dataset_fingerprint: str | None,
    suite: str | None = None,
) -> str:
    payload = {
        "experiment": experiment,
        "n": n,
        "seed": seed,
        "dataset_fingerprint": dataset_fingerprint or "",
        "suite": suite or "",
    }
    return _sha256_hex(payload)[:16]


def compute_reference_fingerprint(
    *,
    experiment: str,
    reference_model: str | None,
    reference_source_tag: str | None,
    reference_lane: str | None,
) -> str:
    payload = {
        "experiment": experiment,
        "reference_model": reference_model or "",
        "reference_source_tag": reference_source_tag or "",
        "reference_lane": reference_lane or "",
    }
    return _sha256_hex(payload)[:16]


def compute_benchmark_contract_fingerprint(
    *,
    perf_enabled: bool,
    perf_rounds: int,
    perf_scalar_n: int,
    perf_batch_n: int,
    perf_batch_rounds: int,
    perf_warmup: int,
    perf_timeout_s: int,
    horizons_use_cache: bool,
    horizons_allow_network: bool,
) -> str:
    payload = {
        "version": BENCHMARK_CONTRACT_VERSION,
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "perf_enabled": perf_enabled,
        "perf_rounds": perf_rounds,
        "perf_scalar_n": perf_scalar_n,
        "perf_batch_n": perf_batch_n,
        "perf_batch_rounds": perf_batch_rounds,
        "perf_warmup": perf_warmup,
        "perf_timeout_s": perf_timeout_s,
        "horizons_use_cache": horizons_use_cache,
        "horizons_allow_network": horizons_allow_network,
    }
    return _sha256_hex(payload)[:16]


def compute_workload_fingerprint(
    *,
    perf_enabled: bool,
    perf_rounds: int,
    perf_scalar_n: int,
    perf_batch_n: int,
    perf_batch_rounds: int,
    perf_warmup: int,
) -> str:
    payload = {
        "perf_enabled": perf_enabled,
        "perf_rounds": perf_rounds,
        "perf_scalar_n": perf_scalar_n,
        "perf_batch_n": perf_batch_n,
        "perf_batch_rounds": perf_batch_rounds,
        "perf_warmup": perf_warmup,
    }
    return _sha256_hex(payload)[:16]


def _adapter_binary_hash(metadata: dict[str, Any], library: str) -> str:
    binaries = metadata.get("adapter_binaries") or {}
    key = f"{library}_adapter"
    info = binaries.get(key) or {}
    return str(info.get("sha256") or "missing")


def compute_candidate_adapter_fingerprint(
    candidate_id: str,
    metadata: dict[str, Any],
) -> str:
    library = candidate_id.split(":", 1)[0]
    payload = {
        "candidate_id": candidate_id,
        "library": library,
        "adapter_binary_sha256": _adapter_binary_hash(metadata, library),
        "git_sha": (metadata.get("git_shas") or {}).get(library, "unknown"),
        "cargo_lock": (metadata.get("cargo_lock_sha256") or {}).get(f"{library}_adapter"),
    }
    return _sha256_hex(payload)[:16]


def compute_machine_fingerprint(metadata: dict[str, Any]) -> str:
    toolchain = metadata.get("toolchain") or {}
    payload = {
        "cpu_model": metadata.get("cpu_model") or metadata.get("cpu") or "",
        "platform_detail": metadata.get("platform_detail") or metadata.get("os") or "",
        "rustc": toolchain.get("rustc", ""),
        "cc": toolchain.get("cc", ""),
        "python": toolchain.get("python", ""),
    }
    return _sha256_hex(payload)[:16]


def compute_kernel_fingerprints(metadata: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    anise = metadata.get("anise_spk") or {}
    if anise.get("sha256"):
        out["anise_spk"] = str(anise["sha256"])[:16]
    for name, info in (metadata.get("siderust_planet_spks") or {}).items():
        if isinstance(info, dict) and info.get("sha256"):
            out[str(name)] = str(info["sha256"])[:16]
    return out


def build_run_fingerprints(
    *,
    experiment: str,
    candidate_id: str,
    metadata: dict[str, Any],
    n: int,
    seed: int,
    dataset_fingerprint: str | None,
    reference_model: str | None,
    reference_source_tag: str | None,
    reference_lane: str | None,
    catalog_entry: CandidateEntry | None,
    perf_enabled: bool,
    perf_rounds: int,
    perf_scalar_n: int,
    perf_batch_n: int,
    perf_batch_rounds: int,
    perf_warmup: int,
    perf_timeout_s: int,
    horizons_use_cache: bool,
    horizons_allow_network: bool,
    suite: str | None = None,
) -> RunFingerprints:
    adapters = {
        candidate_id: compute_candidate_adapter_fingerprint(candidate_id, metadata),
    }
    return RunFingerprints(
        input=compute_input_fingerprint(
            experiment=experiment,
            n=n,
            seed=seed,
            dataset_fingerprint=dataset_fingerprint,
            suite=suite,
        ),
        reference=compute_reference_fingerprint(
            experiment=experiment,
            reference_model=reference_model,
            reference_source_tag=reference_source_tag,
            reference_lane=reference_lane,
        ),
        catalog_entry=compute_catalog_entry_fingerprint(catalog_entry),
        catalog_file=compute_catalog_file_fingerprint(),
        benchmark_contract=compute_benchmark_contract_fingerprint(
            perf_enabled=perf_enabled,
            perf_rounds=perf_rounds,
            perf_scalar_n=perf_scalar_n,
            perf_batch_n=perf_batch_n,
            perf_batch_rounds=perf_batch_rounds,
            perf_warmup=perf_warmup,
            perf_timeout_s=perf_timeout_s,
            horizons_use_cache=horizons_use_cache,
            horizons_allow_network=horizons_allow_network,
        ),
        workload=compute_workload_fingerprint(
            perf_enabled=perf_enabled,
            perf_rounds=perf_rounds,
            perf_scalar_n=perf_scalar_n,
            perf_batch_n=perf_batch_n,
            perf_batch_rounds=perf_batch_rounds,
            perf_warmup=perf_warmup,
        ),
        machine=compute_machine_fingerprint(metadata),
        candidate_adapters=adapters,
        kernel_hashes=compute_kernel_fingerprints(metadata),
        suite=suite,
        n=n,
        seed=seed,
    )


def compute_baseline_key(
    *,
    candidate_id: str,
    experiment: str,
    fingerprints: RunFingerprints,
    kind: str = "combined",
) -> str:
    payload = {
        "candidate_id": candidate_id,
        "experiment": experiment,
        "kind": kind,
        **fingerprints.as_dict(),
    }
    return _sha256_hex(payload)


def _artifact_dir(policy: BaselinePolicy, kind: str = "combined") -> Path:
    return policy.root / kind


def _artifact_path(policy: BaselinePolicy, baseline_key: str, kind: str = "combined") -> Path:
    return _artifact_dir(policy, kind) / f"{baseline_key}.json"


def is_reusable_result_row(row: dict[str, Any]) -> bool:
    status = row.get("status")
    if status not in {"ok"}:
        return False
    if row.get("api_surface") == "reference":
        return False
    if row.get("support_status") not in {None, "supported"}:
        return False
    accuracy = row.get("accuracy") or {}
    if accuracy.get("error"):
        return False
    n_req = int(accuracy.get("count_requested") or row.get("inputs", {}).get("count") or 0)
    n_valid = int(accuracy.get("count_valid") or 0)
    if n_req > 0 and n_valid < n_req:
        return False
    if not row.get("candidate_id"):
        return False
    if not row.get("source_provenance") and not row.get("reference_source_tag"):
        # Require some provenance signal for ephemeris / reference-backed rows.
        family = row.get("family") or ""
        if family == "solar_system_ephemerides":
            return False
    return True


def _fingerprint_mismatch(
    expected: RunFingerprints,
    stored: dict[str, Any],
    *,
    for_performance: bool,
) -> str | None:
    stored_fp = stored.get("fingerprints") or {}
    accuracy_keys = (
        "input",
        "reference",
        "catalog_entry",
        "catalog_file",
        "benchmark_contract",
        "candidate_adapters",
        "kernel_hashes",
    )
    for key in accuracy_keys:
        exp_val = expected.as_dict().get(key)
        got_val = stored_fp.get(key)
        if key == "candidate_adapters":
            exp_map = exp_val or {}
            got_map = got_val or {}
            for cid, digest in exp_map.items():
                if got_map.get(cid) != digest:
                    return f"candidate adapter fingerprint mismatch for {cid}"
            continue
        if exp_val != got_val:
            return f"fingerprint mismatch: {key}"
    if for_performance:
        for key in ("workload", "machine"):
            if expected.as_dict().get(key) != stored_fp.get(key):
                return f"performance fingerprint mismatch: {key}"
    return None


def _performance_reuse_allowed(policy: BaselinePolicy) -> bool:
    return policy.reuse_performance is True or policy.reuse_performance == "same-machine-only"


def validate_baseline_artifact(
    artifact: dict[str, Any],
    *,
    expected: RunFingerprints,
    policy: BaselinePolicy,
    candidate_id: str,
    experiment: str,
) -> BaselineValidation:
    key = str(artifact.get("baseline_key") or "")
    path = None
    if not artifact:
        return BaselineValidation(False, "empty artifact", key or None, path)

    if artifact.get("schema_version") != BASELINE_SCHEMA_VERSION:
        return BaselineValidation(False, "unsupported baseline schema version", key or None, path)

    if artifact.get("candidate_id") != candidate_id or artifact.get("experiment") != experiment:
        return BaselineValidation(
            False,
            "candidate_id/experiment mismatch",
            key or None,
            path,
        )

    row = artifact.get("result") or {}
    if not is_reusable_result_row(row):
        return BaselineValidation(False, "baseline row is not complete/valid", key or None, path)

    perf_allowed = _performance_reuse_allowed(policy)
    mismatch = _fingerprint_mismatch(
        expected,
        artifact,
        for_performance=perf_allowed,
    )
    if mismatch:
        return BaselineValidation(False, mismatch, key or None, path)

    if perf_allowed:
        reuse_kind: Literal["accuracy", "performance", "combined"] = "combined"
    elif policy.reuse_accuracy:
        reuse_kind = "accuracy"
    else:
        return BaselineValidation(False, "baseline reuse disabled", key or None, path)

    return BaselineValidation(True, None, key or None, path, reuse_kind)


def load_baseline_artifact(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def load_valid_baseline(
    *,
    policy: BaselinePolicy,
    candidate_id: str,
    experiment: str,
    expected: RunFingerprints,
    kind: str = "combined",
) -> tuple[dict[str, Any] | None, BaselineValidation]:
    key = compute_baseline_key(
        candidate_id=candidate_id,
        experiment=experiment,
        fingerprints=expected,
        kind=kind,
    )
    path = _artifact_path(policy, key, kind=kind)
    artifact = load_baseline_artifact(path)
    if artifact is None:
        return None, BaselineValidation(False, "baseline missing", key, path)
    validation = validate_baseline_artifact(
        artifact,
        expected=expected,
        policy=policy,
        candidate_id=candidate_id,
        experiment=experiment,
    )
    validation = BaselineValidation(
        validation.valid,
        validation.reason,
        key,
        path,
        validation.reuse_kind,
    )
    if not validation.valid:
        return None, validation
    return artifact, validation


def _invalidate_performance_blocks(row: dict[str, Any], reason: str) -> None:
    perf = row.get("performance")
    if not isinstance(perf, dict):
        row["performance"] = {}
        perf = row["performance"]
    for block_key in ("scalar_warm", "batch_throughput"):
        block = perf.get(block_key)
        if not isinstance(block, dict):
            continue
        block = dict(block)
        block["valid"] = False
        warnings = list(block.get("warnings") or [])
        if reason not in warnings:
            warnings.append(reason)
        block["warnings"] = warnings
        perf[block_key] = block
    row["rankable_performance"] = False
    if row.get("rankable_accuracy") is not True:
        row["rank_exclusion_reason"] = row.get("rank_exclusion_reason") or reason


def annotate_reused_row(
    row: dict[str, Any],
    *,
    validation: BaselineValidation,
    artifact: dict[str, Any],
    policy: BaselinePolicy,
) -> dict[str, Any]:
    out = json.loads(json.dumps(row))
    out["execution_origin"] = "baseline"
    out["baseline_key"] = validation.key
    out["baseline_run_id"] = artifact.get("created_from_run_id")
    out["baseline_created_at"] = artifact.get("created_at")
    out["baseline_reuse_kind"] = validation.reuse_kind
    out["baseline_validation"] = {"valid": True, "reason": None}

    if validation.reuse_kind == "accuracy" and not _performance_reuse_allowed(policy):
        _invalidate_performance_blocks(
            out,
            "performance not reused (accuracy-only baseline policy)",
        )
    return out


def annotate_fresh_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out.setdefault("execution_origin", "fresh")
    out.setdefault(
        "baseline_validation",
        {"valid": True, "reason": None},
    )
    return out


def write_baseline(
    *,
    policy: BaselinePolicy,
    candidate_id: str,
    experiment: str,
    fingerprints: RunFingerprints,
    row: dict[str, Any],
    run_id: str,
    kind: str = "combined",
) -> Path:
    if not is_reusable_result_row(row):
        raise ValueError(f"refusing to store non-reusable baseline row for {candidate_id}/{experiment}")

    key = compute_baseline_key(
        candidate_id=candidate_id,
        experiment=experiment,
        fingerprints=fingerprints,
        kind=kind,
    )
    path = _artifact_path(policy, key, kind=kind)
    path.parent.mkdir(parents=True, exist_ok=True)

    perf_reusable = _performance_reuse_allowed(policy)
    artifact = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "baseline_key": key,
        "candidate_id": candidate_id,
        "experiment": experiment,
        "kind": kind,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "created_from_run_id": run_id,
        "fingerprints": fingerprints.as_dict(),
        "reuse_policy": {
            "reusable_for_accuracy": True,
            "reusable_for_performance": perf_reusable,
        },
        "result": row,
    }
    path.write_text(json.dumps(artifact, indent=2, sort_keys=False) + "\n")
    _update_index(policy, key, artifact, path)
    return path


def _update_index(policy: BaselinePolicy, key: str, artifact: dict[str, Any], path: Path) -> None:
    index_path = policy.root / "index.json"
    index: dict[str, Any]
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text())
        except Exception:
            index = {"schema_version": BASELINE_SCHEMA_VERSION, "entries": []}
    else:
        index = {"schema_version": BASELINE_SCHEMA_VERSION, "entries": []}

    entries = [e for e in index.get("entries", []) if e.get("baseline_key") != key]
    entries.append(
        {
            "baseline_key": key,
            "candidate_id": artifact.get("candidate_id"),
            "experiment": artifact.get("experiment"),
            "kind": artifact.get("kind"),
            "path": str(path.relative_to(policy.root)) if path.is_relative_to(policy.root) else str(path),
            "created_at": artifact.get("created_at"),
            "created_from_run_id": artifact.get("created_from_run_id"),
        }
    )
    index["entries"] = sorted(entries, key=lambda e: (e.get("experiment", ""), e.get("candidate_id", "")))
    index["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    policy.root.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")


def compose_experiment_results(
    *,
    experiment: str,
    fresh_rows: list[dict[str, Any]],
    policy: BaselinePolicy,
    composition: CompositionState,
    run_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Merge freshly computed rows with validated baseline artifacts."""
    if not policy.enabled:
        return [annotate_fresh_row(r) for r in fresh_rows]

    catalog = default_registry()
    metadata = run_context["metadata"]
    n = int(run_context["n"])
    seed = int(run_context["seed"])
    suite = run_context.get("suite")
    perf_enabled = bool(run_context.get("perf_enabled", True))
    perf_rounds = int(run_context.get("perf_rounds", 10))
    perf_scalar_n = int(run_context.get("perf_scalar_n", 5000))
    perf_batch_n = int(run_context.get("perf_batch_n", 100000))
    perf_batch_rounds = int(run_context.get("perf_batch_rounds", 5))
    perf_warmup = int(run_context.get("perf_warmup", 100))
    perf_timeout_s = int(run_context.get("perf_timeout_s", 120))
    horizons_use_cache = bool(run_context.get("horizons_use_cache", True))
    horizons_allow_network = bool(run_context.get("horizons_allow_network", True))

    fresh_by_id = {
        str(r.get("candidate_id")): r for r in fresh_rows if r.get("candidate_id")
    }
    out: list[dict[str, Any]] = []
    expected_ids = set(fresh_by_id)
    for cid in policy.reuse_candidates:
        entry = catalog.get(cid, experiment)
        if entry is None or entry.support != "supported":
            continue
        expected_ids.add(cid)

    for candidate_id in sorted(expected_ids):
        if should_refresh_candidate(candidate_id, policy):
            row = fresh_by_id.get(candidate_id)
            if row is not None:
                out.append(annotate_fresh_row(row))
                composition.fresh_candidates.append(candidate_id)
            continue

        if not should_attempt_baseline_reuse(candidate_id, policy):
            row = fresh_by_id.get(candidate_id)
            if row is not None:
                out.append(annotate_fresh_row(row))
                composition.fresh_candidates.append(candidate_id)
            continue

        ref_model = None
        ref_tag = None
        ref_lane = None
        dataset_fp = None
        probe = fresh_by_id.get(candidate_id) or next(iter(fresh_rows), None)
        if probe:
            ref_model = probe.get("reference_model")
            ref_tag = probe.get("reference_source_tag")
            ref_lane = probe.get("reference_lane")
            inputs = probe.get("inputs") or {}
            dataset_fp = inputs.get("dataset_fingerprint")

        entry = catalog.get(candidate_id, experiment)
        fingerprints = build_run_fingerprints(
            experiment=experiment,
            candidate_id=candidate_id,
            metadata=metadata,
            n=n,
            seed=seed,
            dataset_fingerprint=dataset_fp,
            reference_model=ref_model,
            reference_source_tag=ref_tag,
            reference_lane=ref_lane,
            catalog_entry=entry,
            perf_enabled=perf_enabled,
            perf_rounds=perf_rounds,
            perf_scalar_n=perf_scalar_n,
            perf_batch_n=perf_batch_n,
            perf_batch_rounds=perf_batch_rounds,
            perf_warmup=perf_warmup,
            perf_timeout_s=perf_timeout_s,
            horizons_use_cache=horizons_use_cache,
            horizons_allow_network=horizons_allow_network,
            suite=suite,
        )

        artifact, validation = load_valid_baseline(
            policy=policy,
            candidate_id=candidate_id,
            experiment=experiment,
            expected=fingerprints,
        )
        if artifact and validation.valid:
            row = annotate_reused_row(
                artifact["result"],
                validation=validation,
                artifact=artifact,
                policy=policy,
            )
            row["experiment"] = experiment
            out.append(row)
            composition.baseline_candidates.append(candidate_id)
            continue

        fresh = fresh_by_id.get(candidate_id)
        if fresh is not None:
            out.append(annotate_fresh_row(fresh))
            composition.fresh_candidates.append(candidate_id)
            if validation.reason and validation.reason != "baseline missing":
                composition.stale_baselines.append(f"{experiment}/{candidate_id}")
                composition.all_baselines_valid = False
            continue

        label = f"{experiment}/{candidate_id}"
        composition.missing_baselines.append(label)
        composition.all_baselines_valid = False
        if validation.reason and validation.reason != "baseline missing":
            composition.stale_baselines.append(label)

    composition.mode = "baseline_delta"
    return out


def persist_fresh_baselines(
    *,
    rows: list[dict[str, Any]],
    policy: BaselinePolicy,
    run_context: dict[str, Any],
    run_id: str,
) -> list[Path]:
    if not policy.enabled or not policy.write_missing_baselines:
        return []

    written: list[Path] = []
    metadata = run_context["metadata"]
    n = int(run_context["n"])
    seed = int(run_context["seed"])
    suite = run_context.get("suite")

    for row in rows:
        if row.get("execution_origin") != "fresh":
            continue
        if row.get("status") != "ok":
            continue
        candidate_id = str(row.get("candidate_id") or "")
        if not candidate_id or should_refresh_candidate(candidate_id, policy):
            continue
        if not matches_candidate_pattern(candidate_id, policy.reuse_candidates):
            continue
        if not is_reusable_result_row(row):
            continue

        experiment = str(row.get("experiment") or "")
        entry = default_registry().get(candidate_id, experiment)
        inputs = row.get("inputs") or {}
        fingerprints = build_run_fingerprints(
            experiment=experiment,
            candidate_id=candidate_id,
            metadata=metadata,
            n=n,
            seed=seed,
            dataset_fingerprint=inputs.get("dataset_fingerprint"),
            reference_model=row.get("reference_model"),
            reference_source_tag=row.get("reference_source_tag"),
            reference_lane=row.get("reference_lane"),
            catalog_entry=entry,
            perf_enabled=bool(run_context.get("perf_enabled", True)),
            perf_rounds=int(run_context.get("perf_rounds", 10)),
            perf_scalar_n=int(run_context.get("perf_scalar_n", 5000)),
            perf_batch_n=int(run_context.get("perf_batch_n", 100000)),
            perf_batch_rounds=int(run_context.get("perf_batch_rounds", 5)),
            perf_warmup=int(run_context.get("perf_warmup", 100)),
            perf_timeout_s=int(run_context.get("perf_timeout_s", 120)),
            horizons_use_cache=bool(run_context.get("horizons_use_cache", True)),
            horizons_allow_network=bool(run_context.get("horizons_allow_network", True)),
            suite=suite,
        )
        written.append(
            write_baseline(
                policy=policy,
                candidate_id=candidate_id,
                experiment=experiment,
                fingerprints=fingerprints,
                row=row,
                run_id=run_id,
            )
        )
    return written


def validate_composition_for_publication(
    composition: CompositionState,
    policy: BaselinePolicy,
) -> list[str]:
    if not policy.enabled:
        return []
    blockers: list[str] = []
    if policy.require_complete_baselines:
        if composition.missing_baselines:
            blockers.append(
                "missing required baselines: " + ", ".join(sorted(composition.missing_baselines))
            )
        if composition.stale_baselines:
            blockers.append(
                "stale baselines rejected: " + ", ".join(sorted(composition.stale_baselines))
            )
        if not composition.all_baselines_valid:
            blockers.append("baseline composition is not fully valid")
    if composition.mode == "baseline_delta" and not composition.all_baselines_valid:
        if policy.require_complete_baselines:
            blockers.append("baseline_delta run has invalid baseline composition")
    return blockers


def attach_stratification_hints(row: dict[str, Any]) -> dict[str, Any]:
    """Preserve worst-case labels for export without building bucket summaries."""
    accuracy = row.get("accuracy") or {}
    worst = accuracy.get("worst_cases")
    if not isinstance(worst, list) or not worst:
        return row
    hints = row.get("stratification") or {}
    hints["worst_case_labels"] = [
        {
            "jd_tt": item.get("jd_tt"),
            "label": item.get("label"),
            "angular_error_mas": item.get("angular_error_mas"),
            "eccentricity": item.get("eccentricity"),
            "altitude_deg": item.get("altitude_deg"),
            "ecliptic_latitude_deg": item.get("ecliptic_latitude_deg"),
        }
        for item in worst[:10]
        if isinstance(item, dict)
    ]
    row["stratification"] = hints
    return row
