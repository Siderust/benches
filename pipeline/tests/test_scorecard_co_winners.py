"""Regression tests for the scorecard tie/co-winner logic.

Audit fix F6: a "winner" or "crown" must not imply exact-model superiority
when results are within numerical precision of each other. The scorecard
emits both `best_accuracy_co_winners` and `best_accuracy_exact_co_winners`
so the UI can render co-wins explicitly.
"""

from __future__ import annotations

from pipeline.scorecard import compute_scorecard


def _row(library: str, p99: float, *, comparability: str = "exact-model") -> dict:
    return {
        "candidate_library": library,
        "candidate_profile": None,
        "description": {"title": "fake-exp"},
        "alignment": {"lane": "JPL"},
        "reference_library": "horizons",
        "reference_model": "JPL_DE441",
        "reference_lane": "JPL",
        "tier": "public",
        "status": "ok",
        "support_status": "supported",
        "api_surface": "public",
        "comparability_class": comparability,
        "rankable_accuracy": True,
        "accuracy": {
            "angular_sep_arcsec": {
                "p50": p99,
                "mean": p99,
                "p99": p99,
                "max": p99,
                "rms": p99,
            }
        },
        "performance": None,
        "source_provenance": None,
        "reference_source_tag": None,
    }


def test_close_p99_triggers_co_winner_list():
    experiments = {
        "fake-exp": [
            _row("siderust", 1e-9),
            _row("astropy", 1.0005e-9),  # within 1e-3 relative
            _row("erfa", 1e-6),  # far from winner
        ]
    }
    sc = compute_scorecard("rid", experiments)
    fam = sc["families"][0]
    exp = fam["experiments"][0]
    co = exp["best_accuracy_co_winners"]
    assert "siderust" in co
    assert "astropy" in co
    assert "erfa" not in co


def test_exact_co_winners_excludes_best_available():
    experiments = {
        "fake-exp": [
            _row("siderust", 1e-9),
            _row("astropy", 1.0001e-9, comparability="best-available"),
        ]
    }
    sc = compute_scorecard("rid", experiments)
    exp = sc["families"][0]["experiments"][0]
    assert exp["best_accuracy_co_winners"] == ["astropy", "siderust"]
    assert exp["best_accuracy_exact_co_winners"] == ["siderust"]


def test_solo_winner_returns_single_element_list():
    experiments = {
        "fake-exp": [
            _row("siderust", 1e-9),
            _row("astropy", 1e-3),
        ]
    }
    sc = compute_scorecard("rid", experiments)
    exp = sc["families"][0]["experiments"][0]
    assert exp["best_accuracy_co_winners"] == ["siderust"]
