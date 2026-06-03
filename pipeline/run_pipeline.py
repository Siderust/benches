#!/usr/bin/env python3
"""Run the lab pipeline from a TOML configuration file."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from cache_manager import (
    default_cache_root,
    ensure_de440,
    export_cache_env,
    pipeline_needs_de440,
)
from lab_config import load_pipeline_config


PIPELINE_DIR = Path(__file__).resolve().parent
LAB_ROOT = PIPELINE_DIR.parent


def _resolve_cache_root(cfg_cache_root: str) -> Path:
    path = Path(cfg_cache_root)
    if path.is_absolute():
        return path.resolve()
    return (LAB_ROOT / path).resolve()


def build_orchestrator_command(
    config_path: Path,
    *,
    env: dict[str, str] | None = None,
    allow_dirty_publish: bool = False,
    allow_partial_publish: bool = False,
) -> list[str]:
    cfg = load_pipeline_config(config_path)
    cmd = [
        sys.executable,
        str(PIPELINE_DIR / "orchestrator.py"),
        "--experiments",
        ",".join(cfg.experiments),
        "--n",
        str(cfg.n),
        "--seed",
        str(cfg.seed),
        "--perf-rounds",
        str(cfg.perf_rounds),
        "--perf-scalar-n",
        str(cfg.perf_scalar_n),
        "--perf-batch-n",
        str(cfg.perf_batch_n),
        "--perf-batch-rounds",
        str(cfg.perf_batch_rounds),
        "--perf-warmup",
        str(cfg.perf_warmup),
        "--perf-timeout-s",
        str(cfg.perf_timeout_s),
        "--adapters",
        ",".join(cfg.adapters),
        "--siderust-profiles",
        ",".join(cfg.siderust_profiles),
        "--output-dir",
        cfg.output_dir,
    ]

    if cfg.run_label:
        cmd.extend(["--run-label", cfg.run_label])
    if cfg.run_phase:
        cmd.extend(["--run-phase", cfg.run_phase])
    if cfg.run_tags:
        cmd.extend(["--run-tags", ",".join(cfg.run_tags)])
    if not cfg.performance_enabled:
        cmd.append("--no-perf")
    if cfg.no_build:
        cmd.append("--no-build")
    if not cfg.horizons_use_cache:
        cmd.append("--horizons-no-cache")
    if not cfg.horizons_allow_network:
        cmd.append("--horizons-offline")
    if cfg.publish_latest:
        cmd.append("--publish-latest")
    if cfg.allow_dirty_publish or allow_dirty_publish:
        cmd.append("--allow-dirty-publish")
    if cfg.allow_partial_publish or allow_partial_publish:
        cmd.append("--allow-partial-publish")
    return cmd


def prepare_run_environment(config_path: Path) -> dict[str, str]:
    """Export cache env vars and ensure DE440 when the selected run needs it."""
    cfg = load_pipeline_config(config_path)
    cache_root = _resolve_cache_root(cfg.cache_root)
    env = export_cache_env(cache_root)
    if not cfg.kernels_de440_enabled:
        env["SIDERUST_KERNEL_DE440_ENABLED"] = "0"
    os.environ.update(env)

    if pipeline_needs_de440(
        adapters=cfg.adapters,
        experiments=cfg.experiments,
        kernels_de440_enabled=cfg.kernels_de440_enabled,
    ):
        allow_network = cfg.cache_auto_download and cfg.horizons_allow_network
        result = ensure_de440(allow_network=allow_network, cache_root=cache_root)
        if result.path is None:
            raise RuntimeError(
                result.reason or "DE440 kernel unavailable in benchmark cache"
            )
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Siderust Lab from TOML config")
    parser.add_argument(
        "--config",
        default=str(PIPELINE_DIR / "configs" / "core.toml"),
        help="Path to pipeline config TOML",
    )
    parser.add_argument(
        "--allow-dirty-publish",
        action="store_true",
        help="Allow dirty publish override when running orchestrator.",
    )
    parser.add_argument(
        "--allow-partial-publish",
        action="store_true",
        help="Allow partial publish override when running orchestrator.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = LAB_ROOT / config_path

    try:
        env = prepare_run_environment(config_path)
    except RuntimeError as exc:
        print(f"Cache setup failed: {exc}", file=sys.stderr)
        return 1

    cmd = build_orchestrator_command(
        config_path,
        env=env,
        allow_dirty_publish=args.allow_dirty_publish,
        allow_partial_publish=args.allow_partial_publish,
    )
    try:
        display_path = config_path.relative_to(LAB_ROOT)
    except ValueError:
        display_path = config_path
    print("Siderust Lab pipeline config:", display_path, flush=True)
    print("Benchmark cache:", env.get("SIDERUST_BENCHES_CACHE", default_cache_root()), flush=True)
    print("Command:", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=str(LAB_ROOT), env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
