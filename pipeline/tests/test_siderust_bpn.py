"""
Siderust BPN regression test
============================

Verifies that the Siderust adapter no longer disappears on the
`frame_rotation_bpn` experiment when the requested epochs fall outside
common IERS Earth-orientation-parameter coverage.

The fix replaces the default `AstroContext` (IERS-finals-backed) with a
NullEop context and routes BPN through a pure IAU 2006/2000A
bias-precession-nutation matrix, so the comparison stays a pure
SOFA/IAU model test rather than an EOP-coverage test.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

from orchestrator import (  # noqa: E402
    SIDERUST_BIN,
    format_bpn_input,
    run_adapter,
)


# JD_TT values spanning ~1900 .. ~2200, all outside the embedded
# finals2000A.all horizon at one end or the other for IERS A coverage.
BPN_EPOCHS_TT = [
    2415020.5,   # 1900-01-01 (pre-IERS-A)
    2451545.0,   # J2000
    2488069.5,   # 2100-01-01 (post-IERS-A)
    2525000.5,   # ~2200 (well outside coverage)
    2560000.0,   # ~2300 (deep future)
]


@pytest.mark.skipif(not SIDERUST_BIN.exists(),
                    reason="siderust adapter not built")
def test_siderust_bpn_handles_epochs_outside_iers_coverage():
    """Siderust must return valid cases for every requested epoch,
    including epochs outside the IERS A finals2000A.all horizon."""
    epochs = np.array(BPN_EPOCHS_TT, dtype=np.float64)
    # Unit directions: just probe along x; the BPN matrix exercise is
    # the same regardless of input direction.
    dirs = np.tile(np.array([1.0, 0.0, 0.0]), (len(epochs), 1))

    text = format_bpn_input(epochs, dirs)
    result = run_adapter([str(SIDERUST_BIN)], text, "siderust")

    assert result is not None, "siderust adapter returned None (likely panicked)"
    assert result.get("experiment") == "frame_rotation_bpn"
    assert result.get("library") == "siderust"

    # NullEop must show up in the model tag so the artifact records the choice.
    model = result.get("model", "")
    assert "NullEop" in model, (
        f"expected '+NullEop' suffix in model tag, got {model!r}"
    )

    cases = result.get("cases", [])
    assert len(cases) == len(epochs), (
        f"expected {len(epochs)} cases, got {len(cases)}"
    )

    for i, case in enumerate(cases):
        # Every epoch must be present and rotated to a valid unit vector.
        jd = case.get("jd_tt")
        assert jd is not None
        assert abs(jd - epochs[i]) < 1e-9, (
            f"case {i}: jd mismatch {jd} vs {epochs[i]}"
        )
        out = case.get("output")
        assert out is not None and len(out) == 3
        norm = sum(c * c for c in out) ** 0.5
        assert 0.999 < norm < 1.001, (
            f"case {i}: output not unit-norm: {out} (|v|={norm})"
        )

        # No failure/skip markers should appear on a successful adapter row.
        for marker in ("error", "status", "skipped"):
            assert marker not in case or case[marker] in (None, "ok"), (
                f"case {i}: unexpected marker {marker}={case.get(marker)!r}"
            )


@pytest.mark.skipif(not SIDERUST_BIN.exists(),
                    reason="siderust adapter not built")
def test_siderust_bpn_closure_is_zero_at_far_future():
    """The forward+inverse BPN closure must round-trip to identity even at
    far-future epochs where IERS data is unavailable."""
    epochs = np.array([2525000.5, 2560000.0], dtype=np.float64)
    dirs = np.tile(np.array([1.0, 0.0, 0.0]), (len(epochs), 1))
    text = format_bpn_input(epochs, dirs)
    result = run_adapter([str(SIDERUST_BIN)], text, "siderust")

    assert result is not None
    cases = result.get("cases", [])
    assert len(cases) == len(epochs)
    for case in cases:
        cl = case.get("closure_rad")
        assert cl is not None
        # The pure-model BPN matrix is orthogonal; closure should be at
        # the floating-point noise level (well below 1e-12 rad).
        assert abs(cl) < 1e-12, f"closure too large: {cl}"
