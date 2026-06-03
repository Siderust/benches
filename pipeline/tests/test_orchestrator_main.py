"""CLI regression tests for orchestrator.main execution flow."""

import json
import subprocess
import sys
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = LAB_ROOT / "pipeline" / "orchestrator.py"


def _run_orchestrator(output_dir: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR),
            "--experiments",
            "gmst_era",
            "--n",
            "1",
            "--no-perf",
            "--no-build",
            "--output-dir",
            str(output_dir),
            *extra_args,
        ],
        cwd=LAB_ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )


def _latest_manifest(output_dir: Path) -> Path:
    manifests = sorted(output_dir.glob("*/manifest.json"))
    assert manifests, f"no manifest written under {output_dir}"
    return manifests[-1]


def test_cli_gmst_era_writes_manifest_and_prints_banner(tmp_path):
    output_dir = tmp_path / "results"

    proc = _run_orchestrator(output_dir)

    assert proc.returncode == 0, proc.stderr
    assert "Siderust Lab" in proc.stdout
    assert "Benchmark Run" in proc.stdout
    manifest_path = _latest_manifest(output_dir)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["config"]["experiments"] == ["gmst_era"]
    assert manifest["config"]["ci_mode"] is False
    assert manifest["completeness"]["completed_experiments"] == ["gmst_era"]


def test_cli_without_ci_executes_normal_flow(tmp_path):
    output_dir = tmp_path / "results"

    proc = _run_orchestrator(output_dir, "--adapters", "libnova")

    assert proc.returncode == 0, proc.stderr
    assert "CI mode:       no" in proc.stdout
    manifest = json.loads(_latest_manifest(output_dir).read_text())
    assert manifest["config"]["ci_mode"] is False
    assert manifest["config"]["adapters"] == ["libnova"]
    assert manifest["experiment_count"] == 1
