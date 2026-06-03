"""A8: regression test for ANISE adapter SPK discovery env vars and preflight.

Audits requiring this: rankability_and_model_capability §5.

We don't actually need an SPK to validate the discovery *order*. Instead we
construct an empty dir as ANISE_BSP_PATH (and SIDERUST_DATASETS_DIR), run the
adapter with a stub input that triggers `load_ephemeris_almanac`, and inspect
the preflight error. The error must exit non-zero and mention both env-var names
so the operator knows exactly how to fix the setup.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = REPO_ROOT / "pipeline/adapters/anise_adapter/target/release/anise-adapter"


@pytest.mark.skipif(not ADAPTER.exists(), reason="ANISE adapter binary not built")
def test_anise_preflight_exits_nonzero_with_env_var_hints(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    env = dict(os.environ)
    env["ANISE_BSP_PATH"] = str(empty_dir)
    env["SIDERUST_DATASETS_DIR"] = str(empty_dir)

    # Stub solar_position payload: experiment header + 0 samples.
    stub = "solar_position\n0\n"
    proc = subprocess.run(
        [str(ADAPTER)],
        input=stub,
        text=True,
        capture_output=True,
        env=env,
        cwd=tmp_path,  # so legacy relative fallbacks don't accidentally resolve
        timeout=20,
    )
    # Preflight exits non-zero with actionable message on stderr; no skipped rows emitted.
    assert proc.returncode != 0, "expected non-zero exit when SPK is unavailable"
    assert proc.stdout == "", f"expected no stdout output; got: {proc.stdout[:200]}"
    assert "ANISE_BSP_PATH" in proc.stderr
    assert "SIDERUST_DATASETS_DIR" in proc.stderr
