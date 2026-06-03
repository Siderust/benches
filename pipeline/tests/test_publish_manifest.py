"""Manifest scope, publication gate, and partial-run labelling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import orchestrator
from pipeline.lab_config import PUBLIC_EXPERIMENTS

LAB_ROOT = Path(__file__).resolve().parents[2]


def test_missing_requested_experiment_marks_partial():
    requested = list(PUBLIC_EXPERIMENTS)
    completed = requested[:-1]
    scope = orchestrator._run_scope(requested, completed)
    assert scope["partial"] is True
    assert scope["missing_requested_experiments"] == [requested[-1]]
    assert scope["core_partial"] is True


def test_core_plus_extra_all_completed_not_partial():
    extra = ["frame_bias"]
    requested = [*PUBLIC_EXPERIMENTS, *extra]
    scope = orchestrator._run_scope(requested, requested)
    assert scope["partial"] is False
    assert scope["suite_label"] == "core+extra"
    assert scope["core_complete"] is True


def test_publish_blocked_when_dirty_without_override():
    scope = {"partial": False}
    meta = {"git_dirty": {"lab": True}}
    blockers = orchestrator._validate_publish_latest(scope, meta)
    assert blockers
    assert not orchestrator._publish_overrides_satisfy(
        blockers, allow_dirty=False, allow_partial=False,
    )


def test_publish_blocked_when_partial_without_override():
    scope = {"partial": True, "missing_requested_experiments": ["kepler_solver"]}
    meta = {"git_dirty": {"lab": False}}
    blockers = orchestrator._validate_publish_latest(scope, meta)
    assert blockers
    assert not orchestrator._publish_overrides_satisfy(
        blockers, allow_dirty=False, allow_partial=False,
    )


def test_publish_allowed_with_dirty_override():
    scope = {"partial": False}
    meta = {"git_dirty": {"lab": True}}
    blockers = orchestrator._validate_publish_latest(scope, meta)
    assert orchestrator._publish_overrides_satisfy(
        blockers, allow_dirty=True, allow_partial=False,
    )


def test_latest_manifest_has_publication_block_when_present():
    mp = LAB_ROOT / "latest_results" / "manifest.json"
    if not mp.is_file():
        pytest.skip("no latest_results manifest")
    m = json.loads(mp.read_text())
    if "publication" not in m:
        pytest.skip("manifest predates publication block (re-run pipeline to refresh)")
    assert "grade" in m["publication"]
