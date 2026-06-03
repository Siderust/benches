"""
Benchmark Sanity Tests
======================

These tests verify that the benchmark framework is working correctly:
1. Adapters actually perform work (not zero-work / dead-code eliminated)
2. Performance measurements are above minimum threshold
3. Accuracy results are deterministic with fixed seed
4. Required metadata is present in results
5. Dataset fingerprints are reproducible
"""

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

# Resolve paths
TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
LAB_ROOT = PIPELINE_DIR.parent

sys.path.insert(0, str(PIPELINE_DIR))
from orchestrator import (
    generate_frame_rotation_inputs,
    generate_gmst_era_inputs,
    generate_kepler_inputs,
    format_bpn_input,
    format_gmst_input,
    format_kepler_input,
    run_adapter,
    compute_accuracy_metrics,
    compute_gmst_accuracy,
    compute_kepler_accuracy,
    dataset_fingerprint,
    run_metadata,
    ERFA_BIN,
    SIDERUST_BIN,
    ASTROPY_SCRIPT,
    LIBNOVA_BIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def adapter_available(path: Path) -> bool:
    """Check if an adapter binary/script exists."""
    return path.exists()


def skip_if_not_built(path: Path, name: str):
    """Skip test if adapter is not built."""
    if not adapter_available(path):
        pytest.skip(f"{name} adapter not built at {path}")


# ---------------------------------------------------------------------------
# Test: Dataset fingerprints are deterministic
# ---------------------------------------------------------------------------

class TestDatasetFingerprint:
    def test_same_input_same_fingerprint(self):
        """Same inputs must produce the same fingerprint."""
        fp1 = dataset_fingerprint({"n": 100, "seed": 42, "experiment": "test"})
        fp2 = dataset_fingerprint({"n": 100, "seed": 42, "experiment": "test"})
        assert fp1 == fp2

    def test_different_input_different_fingerprint(self):
        """Different inputs must produce different fingerprints."""
        fp1 = dataset_fingerprint({"n": 100, "seed": 42, "experiment": "test"})
        fp2 = dataset_fingerprint({"n": 200, "seed": 42, "experiment": "test"})
        assert fp1 != fp2

    def test_fingerprint_is_hex(self):
        """Fingerprint must be a 16-char hex string."""
        fp = dataset_fingerprint({"test": True})
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)


# ---------------------------------------------------------------------------
# Test: Input generation is deterministic
# ---------------------------------------------------------------------------

class TestInputDeterminism:
    def test_frame_rotation_inputs_deterministic(self):
        """Same seed must produce identical frame rotation inputs."""
        e1, d1, l1 = generate_frame_rotation_inputs(50, 42)
        e2, d2, l2 = generate_frame_rotation_inputs(50, 42)
        np.testing.assert_array_equal(e1, e2)
        np.testing.assert_array_equal(d1, d2)
        assert l1 == l2

    def test_gmst_inputs_deterministic(self):
        """Same seed must produce identical GMST inputs."""
        u1, t1 = generate_gmst_era_inputs(50, 42)
        u2, t2 = generate_gmst_era_inputs(50, 42)
        np.testing.assert_array_equal(u1, u2)
        np.testing.assert_array_equal(t1, t2)

    def test_kepler_inputs_deterministic(self):
        """Same seed must produce identical Kepler inputs."""
        m1, e1 = generate_kepler_inputs(50, 42)
        m2, e2 = generate_kepler_inputs(50, 42)
        np.testing.assert_array_equal(m1, m2)
        np.testing.assert_array_equal(e1, e2)

    def test_different_seeds_different_inputs(self):
        """Different seeds must produce different inputs."""
        e1, _, _ = generate_frame_rotation_inputs(50, 42)
        e2, _, _ = generate_frame_rotation_inputs(50, 99)
        assert not np.array_equal(e1, e2)


# ---------------------------------------------------------------------------
# Test: Adapters produce valid output (non-zero work)
# ---------------------------------------------------------------------------

class TestAdapterOutput:
    """Verify adapters actually compute results (not empty/zero output)."""

    def _run_and_validate(self, cmd, input_text, label, expected_experiment):
        """Helper: run adapter and validate output structure."""
        result = run_adapter(cmd, input_text, label)
        assert result is not None, f"{label} adapter returned None"
        assert result.get("experiment") == expected_experiment, \
            f"Expected experiment '{expected_experiment}', got '{result.get('experiment')}'"
        assert result.get("count", 0) > 0, f"{label}: count is 0"
        assert len(result.get("cases", [])) > 0, f"{label}: no cases returned"
        return result

    @pytest.mark.skipif(not adapter_available(ERFA_BIN), reason="ERFA not built")
    def test_erfa_bpn_produces_output(self):
        epochs, dirs, _ = generate_frame_rotation_inputs(10, 42)
        text = format_bpn_input(epochs, dirs)
        result = self._run_and_validate([str(ERFA_BIN)], text, "erfa", "frame_rotation_bpn")
        # Verify outputs are not all zeros
        for case in result["cases"]:
            out = case["output"]
            assert any(abs(v) > 1e-15 for v in out), "BPN output is all zeros"

    @pytest.mark.skipif(not adapter_available(ERFA_BIN), reason="ERFA not built")
    def test_erfa_gmst_produces_output(self):
        ut1, tt = generate_gmst_era_inputs(10, 42)
        text = format_gmst_input(ut1, tt)
        result = self._run_and_validate([str(ERFA_BIN)], text, "erfa", "gmst_era")
        for case in result["cases"]:
            assert case.get("gmst_rad") is not None, "GMST is None"
            assert abs(case["gmst_rad"]) > 0, "GMST is zero"

    @pytest.mark.skipif(not adapter_available(ERFA_BIN), reason="ERFA not built")
    def test_erfa_kepler_returns_unsupported(self):
        """ERFA exposes no public Kepler solver — adapter must declare it
        unsupported (truth invariant from audit-and-rework-plan)."""
        M, e = generate_kepler_inputs(10, 42)
        text = format_kepler_input(M, e)
        result = run_adapter([str(ERFA_BIN)], text, "erfa")
        assert result is not None
        assert result.get("experiment") == "kepler_solver"
        assert result.get("status") == "unsupported"
        assert result.get("count", 0) == 0
        assert not result.get("cases")


# ---------------------------------------------------------------------------
# Test: Accuracy metrics are consistent across runs
# ---------------------------------------------------------------------------

class TestAccuracyStability:
    """Verify that accuracy metrics are stable across repeated computations."""

    @pytest.mark.skipif(not adapter_available(ERFA_BIN), reason="ERFA not built")
    def test_bpn_accuracy_deterministic(self):
        """BPN accuracy must be identical across two runs with same input."""
        epochs, dirs, _ = generate_frame_rotation_inputs(20, 42)
        text = format_bpn_input(epochs, dirs)

        r1 = run_adapter([str(ERFA_BIN)], text, "erfa_run1")
        r2 = run_adapter([str(ERFA_BIN)], text, "erfa_run2")

        assert r1 is not None and r2 is not None

        # Compare output vectors
        for c1, c2 in zip(r1["cases"], r2["cases"]):
            for v1, v2 in zip(c1["output"], c2["output"]):
                assert v1 == v2, "BPN outputs differ between identical runs"


# ---------------------------------------------------------------------------
# Test: Run metadata is complete
# ---------------------------------------------------------------------------

class TestRunMetadata:
    def test_metadata_has_required_fields(self):
        """Run metadata must include date, git SHAs, CPU, and OS."""
        meta = run_metadata()
        assert meta.get("date") is not None, "Missing date"
        assert meta.get("git_shas") is not None, "Missing git_shas"
        assert meta.get("cpu") is not None or meta.get("cpu_model") is not None, "Missing CPU info"
        assert meta.get("os") is not None, "Missing OS info"
        assert "python" in meta.get("toolchain", {}), "Missing Python version"

    def test_metadata_date_is_utc(self):
        """Date must be in UTC ISO format."""
        meta = run_metadata()
        date_str = meta["date"]
        assert date_str.endswith("Z"), f"Date should end with Z (UTC): {date_str}"

    def test_metadata_has_numpy_version(self):
        """Numpy version should be captured."""
        meta = run_metadata()
        assert "numpy" in meta.get("toolchain", {}), "Missing numpy version"


# ---------------------------------------------------------------------------
# Test: Performance results structure (if adapters are available)
# ---------------------------------------------------------------------------

class TestPerformanceStructure:
    """Verify performance measurements return valid structure."""

    @pytest.mark.skipif(not adapter_available(ERFA_BIN), reason="ERFA not built")
    def test_perf_result_has_timing(self):
        """Performance adapter must return per_op_ns and total_ns."""
        from orchestrator import format_bpn_perf_input
        epochs, dirs, _ = generate_frame_rotation_inputs(50, 42)
        text = format_bpn_perf_input(epochs, dirs)
        result = run_adapter([str(ERFA_BIN)], text, "erfa_perf")

        assert result is not None, "Performance adapter returned None"
        assert result.get("per_op_ns") is not None, "Missing per_op_ns"
        assert result.get("total_ns") is not None, "Missing total_ns"
        assert result["per_op_ns"] > 0, "per_op_ns must be positive"
        assert result["total_ns"] > 0, "total_ns must be positive"

    @pytest.mark.skipif(not adapter_available(ERFA_BIN), reason="ERFA not built")
    def test_perf_not_suspiciously_fast(self):
        """BPN performance should not be below 1 ns/op (would indicate no-op)."""
        from orchestrator import format_bpn_perf_input
        epochs, dirs, _ = generate_frame_rotation_inputs(100, 42)
        text = format_bpn_perf_input(epochs, dirs)
        result = run_adapter([str(ERFA_BIN)], text, "erfa_perf")

        assert result is not None
        per_op = result["per_op_ns"]
        # BPN computation involves matrix multiply + nutation series —
        # should take at least ~100ns per operation
        assert per_op > 1.0, f"per_op_ns={per_op} is suspiciously fast (< 1 ns)"


# ---------------------------------------------------------------------------
# Test: Multi-sample performance
# ---------------------------------------------------------------------------

class TestMultiSamplePerf:
    @pytest.mark.skipif(not adapter_available(ERFA_BIN), reason="ERFA not built")
    def test_multi_sample_returns_statistics(self):
        """run_multi_sample_perf must return statistical fields."""
        from orchestrator import format_bpn_perf_input, run_multi_sample_perf
        epochs, dirs, _ = generate_frame_rotation_inputs(50, 42)
        text = format_bpn_perf_input(epochs, dirs)

        result = run_multi_sample_perf([str(ERFA_BIN)], text, "erfa_perf", rounds=2)
        assert result is not None, "multi-sample perf returned None"
        assert result.get("per_op_ns_median") is not None
        assert result.get("per_op_ns_mean") is not None
        assert result.get("rounds") == 2
        assert result.get("samples") is not None
        assert len(result["samples"]) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
