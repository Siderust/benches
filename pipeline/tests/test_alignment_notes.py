"""Sentinel test for audit M3 / rankability §4: alignment notes must not
re-introduce stale phrasings that contradict current rankability behaviour."""

from pathlib import Path
import sys

TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

import orchestrator as orch


STALE_PHRASES = (
    "libnova is shown but not ranked",
    "Only geometric candidates rank here",
    "Geometric candidates only",
    "same-model comparison",
)


def _all_notes() -> list[str]:
    notes: list[str] = []
    for exp in ("solar_position", "lunar_position", "mars_position", "jupiter_position"):
        a = orch.alignment_checklist(exp, candidate_library="libnova")
        if isinstance(a, dict):
            note = a.get("note")
            if note:
                notes.append(note)
    return notes


def test_no_stale_alignment_phrases():
    notes = _all_notes()
    assert notes, "expected to inspect at least one alignment note"
    for note in notes:
        for phrase in STALE_PHRASES:
            assert phrase not in note, f"stale phrase {phrase!r} found in alignment note: {note}"


def test_geometric_notes_describe_best_available_policy():
    """Public geometric lane notes should explicitly disclose best-available
    model comparison so users understand the model differences."""
    a = orch.alignment_checklist("mars_position", candidate_library="libnova")
    note = a.get("note", "") if isinstance(a, dict) else ""
    assert "best-available" in note.lower(), f"expected best-available disclosure: {note!r}"
