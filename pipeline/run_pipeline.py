#!/usr/bin/env python3
"""Run the lab pipeline from a TOML configuration file."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from lab_config import load_pipeline_config


PIPELINE_DIR = Path(__file__).resolve().parent
LAB_ROOT = PIPELINE_DIR.parent


def build_orchestrator_command(config_path: Path) -> list[str]:
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
    if cfg.allow_dirty_publish:
        cmd.append("--allow-dirty-publish")
    if cfg.allow_partial_publish:
        cmd.append("--allow-partial-publish")

    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Siderust Lab from TOML config")
    parser.add_argument(
        "--config",
        default=str(PIPELINE_DIR / "configs" / "core.toml"),
        help="Path to pipeline config TOML",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = LAB_ROOT / config_path

    cmd = build_orchestrator_command(config_path)
    try:
        display_path = config_path.relative_to(LAB_ROOT)
    except ValueError:
        display_path = config_path
    print("Siderust Lab pipeline config:", display_path, flush=True)
    print("Command:", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=str(LAB_ROOT))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
