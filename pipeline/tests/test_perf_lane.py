"""A5 regression test: perf adapter invocations receive LAB_LANE.

The fairness audit (F1) noted that performance measurements were running
without the lane env var that accuracy uses, producing perf numbers from a
different code path than the accuracy numbers next to them. We patch
`run_adapter` and assert that the env was propagated.
"""

from __future__ import annotations

from unittest.mock import patch

from pipeline import orchestrator


def test_run_multi_sample_perf_propagates_lab_lane() -> None:
    captured = []

    def fake_run_adapter(cmd, input_text, label, *, extra_env=None):
        captured.append({"label": label, "extra_env": extra_env})
        return {"per_op_ns": 100.0, "total_ns": 1000, "count": 10}

    with patch.object(orchestrator, "run_adapter", side_effect=fake_run_adapter):
        out = orchestrator.run_multi_sample_perf(
            ["echo"], "stub", "stub_perf",
            rounds=3,
            extra_env={"LAB_LANE": "geometric_vector"},
        )

    assert out is not None
    assert len(captured) == 3
    for call in captured:
        assert call["extra_env"] == {"LAB_LANE": "geometric_vector"}, call


def test_run_multi_sample_perf_without_env_is_none_default() -> None:
    """Back-compat: callers that don't pass extra_env see None forwarded."""
    captured = []

    def fake_run_adapter(cmd, input_text, label, *, extra_env=None):
        captured.append(extra_env)
        return {"per_op_ns": 1.0, "total_ns": 1, "count": 1}

    with patch.object(orchestrator, "run_adapter", side_effect=fake_run_adapter):
        orchestrator.run_multi_sample_perf(["echo"], "stub", "stub_perf", rounds=2)

    assert captured == [None, None]
