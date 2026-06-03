"""Tests for the unified benchmark cache manager."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
LAB_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

import cache_manager as cm
from run_pipeline import build_orchestrator_command, prepare_run_environment


def _fake_bsp(path: Path, *, size: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    min_bytes = size if size is not None else cm.DE440_MIN_BYTES + 1
    path.write_bytes(b"\0" * min_bytes)


def test_export_cache_env_sets_expected_variables(tmp_path, small_de440_min_bytes):
    cache_root = tmp_path / "cache"
    _fake_bsp(cache_root / "kernels" / "de440.bsp", size=32)

    env = cm.export_cache_env(cache_root)

    assert env["SIDERUST_BENCHES_CACHE"] == str(cache_root.resolve())
    assert env["ASTROPY_JPL_BSP_PATH"] == str((cache_root / "kernels" / "de440.bsp").resolve())
    assert env["SIDERUST_DATASETS_DIR"] == str((cache_root / "siderust_datasets").resolve())
    link = cache_root / "siderust_datasets" / "de440_dataset" / "de440.bsp"
    assert link.is_symlink()
    assert link.resolve() == (cache_root / "kernels" / "de440.bsp").resolve()


def test_resolve_de440_from_cache_root(tmp_path, small_de440_min_bytes):
    cache_root = tmp_path / "bench_cache"
    bsp = cache_root / "kernels" / "de440.bsp"
    _fake_bsp(bsp)

    result = cm.resolve_de440(cache_root)

    assert result.status == "ok"
    assert result.path == bsp.resolve()


def test_ensure_de440_offline_reports_missing(tmp_path):
    cache_root = tmp_path / "offline_cache"
    cm.prepare_cache_layout(cache_root)

    result = cm.ensure_de440(allow_network=False, cache_root=cache_root)

    assert result.path is None
    assert result.status == "missing"
    assert result.reason


def test_ensure_de440_download_writes_manifest(tmp_path, small_de440_min_bytes):
    cache_root = tmp_path / "download_cache"
    bsp = cache_root / "kernels" / "de440.bsp"
    payload = b"\0" * 32

    def fake_download(url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)

    with patch.object(cm, "_download_atomic", side_effect=fake_download):
        result = cm.ensure_de440(allow_network=True, cache_root=cache_root)

    assert result.status == "ok"
    assert result.path == bsp.resolve()
    manifest = json.loads(cm.manifest_path(cache_root).read_text(encoding="utf-8"))
    assert manifest["path"] == str(bsp.resolve())
    assert manifest["size"] == len(payload)
    assert manifest["source_url"] == cm.DE440_SOURCE_URL
    assert manifest["sha256"]
    assert manifest["downloaded_at"]


def test_astropy_de440_local_uses_benches_cache_path(tmp_path, capsys, small_de440_min_bytes):
    from pipeline.adapters.astropy_adapter import adapter
    from pipeline.adapters.astropy_adapter import common

    cache_root = tmp_path / "lab_cache"
    bsp = cache_root / "kernels" / "de440.bsp"
    _fake_bsp(bsp)

    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ASTROPY_JPL_BSP_PATH", "SIDERUST_DATASETS_DIR")
    }
    env.update({
        "ASTROPY_EPHEMERIS": "de440-local",
        "SIDERUST_BENCHES_CACHE": str(cache_root),
    })
    with patch.dict(os.environ, env, clear=True), patch.object(
        common, "_astropy_geometric_geocentric"
    ) as geometric:
        adapter.run_setup("solar_position_setup")

    geometric.assert_called_once_with(2451545.0, "sun", str(bsp.resolve()))
    assert json.loads(capsys.readouterr().out)["measured"] is True


def test_prepare_run_environment_exports_cache(tmp_path, small_de440_min_bytes):
    cache_root = tmp_path / "bench_cache"
    _fake_bsp(cache_root / "kernels" / "de440.bsp", size=32)
    config = tmp_path / "ephem.toml"
    config.write_text(
        f"""
suite = "ephemeris"
n = 1
adapters = ["astropy"]
no_build = true

[cache]
root = "{cache_root}"
auto_download = false

[kernels.de440]
enabled = true

[horizons]
allow_network = false

[performance]
enabled = false
"""
    )

    with patch.dict(os.environ, {}, clear=False):
        env = prepare_run_environment(config)

    assert env["SIDERUST_BENCHES_CACHE"] == str(cache_root.resolve())
    assert env["ASTROPY_JPL_BSP_PATH"].endswith("kernels/de440.bsp")


def test_prepare_run_environment_fails_offline_without_de440(tmp_path):
    config = tmp_path / "missing.toml"
    config.write_text(
        """
suite = "ephemeris"
n = 1
adapters = ["anise"]
no_build = true

[cache]
root = ".missing_cache"
auto_download = false

[horizons]
allow_network = false

[performance]
enabled = false
"""
    )
    with pytest.raises(RuntimeError, match="DE440|missing|cache"):
        prepare_run_environment(config)


def test_full_fast_config_prints_configured_perf_sizes(tmp_path):
    from lab_config import load_pipeline_config

    fast_cfg = load_pipeline_config(PIPELINE_DIR / "configs" / "full_fast.toml")
    assert fast_cfg.perf_scalar_n == 50
    assert fast_cfg.perf_batch_n == 50

    proc = subprocess.run(
        [
            sys.executable,
            str(PIPELINE_DIR / "orchestrator.py"),
            "--experiments",
            "gmst_era",
            "--n",
            "1",
            "--no-build",
            "--adapters",
            "libnova",
            "--perf-rounds",
            "1",
            "--perf-scalar-n",
            str(fast_cfg.perf_scalar_n),
            "--perf-batch-n",
            str(fast_cfg.perf_batch_n),
            "--perf-batch-rounds",
            "1",
            "--perf-warmup",
            "1",
            "--perf-timeout-s",
            "30",
            "--output-dir",
            str(tmp_path / "out"),
        ],
        cwd=str(LAB_ROOT),
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert f"scalar_n:     {fast_cfg.perf_scalar_n}" in proc.stdout
    assert f"batch_n:      {fast_cfg.perf_batch_n}" in proc.stdout


def test_run_sh_exports_cache_env():
    script = LAB_ROOT / "run.sh"
    text = script.read_text(encoding="utf-8")
    assert 'SIDERUST_BENCHES_CACHE="${SIDERUST_BENCHES_CACHE:-$LAB_ROOT/.benches_cache}"' in text
    assert "ASTROPY_JPL_BSP_PATH" in text
    assert "SIDERUST_DATASETS_DIR" in text
    assert "ln -sf" in text


def test_run_sh_run_forwards_publication_override_flags(tmp_path):
    temp_root = tmp_path / "repo"
    temp_root.mkdir()
    (temp_root / "run.sh").symlink_to(LAB_ROOT / "run.sh")
    (temp_root / "pipeline").symlink_to(LAB_ROOT / "pipeline")

    venv_activate = temp_root / ".venv/bin/activate"
    venv_activate.parent.mkdir(parents=True)
    venv_activate.write_text("export VIRTUAL_ENV=/tmp\n", encoding="utf-8")
    venv_activate.chmod(0o755)

    stub_bin = temp_root / "stubbin"
    stub_bin.mkdir()
    stub_python = stub_bin / "python3"
    stub_python.write_text(
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\"\n",
        encoding="utf-8",
    )
    stub_python.chmod(0o755)

    result = subprocess.run(
        ["bash", "-lc", "./run.sh run pipeline/configs/full_fast.toml --allow-dirty-publish"],
        cwd=str(temp_root),
        env={**os.environ, "PATH": str(stub_bin) + ":" + os.environ.get("PATH", "")},
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "--allow-dirty-publish" in result.stdout
    assert "pipeline/run_pipeline.py" in result.stdout


def test_build_orchestrator_command_includes_perf_from_config(tmp_path):
    config = tmp_path / "perf.toml"
    config.write_text(
        """
[performance]
scalar_n = 77
batch_n = 88
"""
    )
    cmd = build_orchestrator_command(config)
    assert cmd[cmd.index("--perf-scalar-n") + 1] == "77"
    assert cmd[cmd.index("--perf-batch-n") + 1] == "88"
