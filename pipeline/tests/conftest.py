"""Shared pytest fixtures for the pipeline test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))

import cache_manager as cm


@pytest.fixture
def small_de440_min_bytes(monkeypatch):
    """Use a tiny BSP size threshold in tests (production keeps 100 MiB)."""
    monkeypatch.setattr(cm, "DE440_MIN_BYTES", 16)
