from pathlib import Path

import pytest

import sys

TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

from lab_config import EPHEMERIS_EXPERIMENTS, PUBLIC_EXPERIMENTS, load_pipeline_config
from run_pipeline import build_orchestrator_command


def test_core_config_resolves_public_suite():
    cfg = load_pipeline_config(PIPELINE_DIR / "configs" / "core.toml")
    assert cfg.suite == "core"
    assert cfg.experiments == PUBLIC_EXPERIMENTS
    assert "mars_barycenter_position" in cfg.experiments
    assert "mars_position" not in cfg.experiments
    assert cfg.siderust_profiles == ["iau2006a"]
    assert cfg.publish_latest is True


def test_unknown_profile_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('suite = "ci"\nsiderust_profiles = ["iau1980"]\n')
    with pytest.raises(ValueError, match="Unknown Siderust profile"):
        load_pipeline_config(path)


def test_unknown_experiment_is_rejected(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('suite = "core"\nexperiments = ["not_real"]\n')
    with pytest.raises(ValueError, match="Unknown experiment"):
        load_pipeline_config(path)


def test_ci_config_builds_offline_command():
    cmd = build_orchestrator_command(PIPELINE_DIR / "configs" / "ci.toml")
    assert "--horizons-offline" in cmd
    assert "--no-perf" in cmd
    assert "--no-build" in cmd
    assert "--experiments" in cmd
    experiments = cmd[cmd.index("--experiments") + 1]
    assert "solar_position" not in experiments


def test_ephemeris_suite_resolves_horizons_experiments():
    cfg = load_pipeline_config(PIPELINE_DIR / "configs" / "phase_b_ephemeris_seed42.toml")
    assert cfg.suite == "ephemeris"
    assert cfg.experiments == EPHEMERIS_EXPERIMENTS
    assert "solar_position" in cfg.experiments
    assert "neptune_barycenter_position" in cfg.experiments
    assert "mars_position" not in cfg.experiments


def test_phase_b_configs_cover_required_matrix():
    configs = [
        load_pipeline_config(path)
        for path in sorted((PIPELINE_DIR / "configs").glob("phase_b_*.toml"))
    ]
    labels = {cfg.run_label for cfg in configs}
    assert "phase-b-ci-seed42" in labels
    assert "phase-b-public-seed42" in labels
    assert "phase-b-large-validation" in labels
    public_seeds = {
        cfg.seed
        for cfg in configs
        if cfg.run_label and cfg.run_label.startswith("phase-b-public-")
    }
    assert len(public_seeds) >= 3
    assert any("performance" in cfg.run_tags and cfg.perf_rounds >= 20 for cfg in configs)
    assert any("anise" in cfg.run_tags and "anise" in cfg.adapters for cfg in configs)


def test_phase_b_labels_are_passed_to_orchestrator_command():
    cmd = build_orchestrator_command(PIPELINE_DIR / "configs" / "phase_b_ci_seed42.toml")
    assert cmd[cmd.index("--run-label") + 1] == "phase-b-ci-seed42"
    assert cmd[cmd.index("--run-phase") + 1] == "phase-b"
    assert "phase-b,ci,small,seed42" == cmd[cmd.index("--run-tags") + 1]


def test_full_fast_is_offline_smoke_draft():
    cfg = load_pipeline_config(PIPELINE_DIR / "configs" / "full_fast.toml")
    assert cfg.n == 10
    assert len(cfg.experiments) == 32
    assert "icrs_ecl_tod" not in cfg.experiments
    assert not any(exp.endswith("_apparent") for exp in cfg.experiments)
    assert cfg.perf_rounds == 1
    assert cfg.perf_scalar_n == 50
    assert cfg.perf_batch_n == 50
    assert cfg.publish_latest is False
    assert cfg.horizons_allow_network is False
    assert cfg.run_phase == "smoke"
    assert {"smoke", "draft"} <= set(cfg.run_tags)

    cmd = build_orchestrator_command(PIPELINE_DIR / "configs" / "full_fast.toml")
    assert "--horizons-offline" in cmd
    assert "--publish-latest" not in cmd


def test_build_orchestrator_command_forwards_publication_overrides():
    cmd = build_orchestrator_command(
        PIPELINE_DIR / "configs" / "full_fast.toml",
        allow_dirty_publish=True,
        allow_partial_publish=True,
    )
    assert "--allow-dirty-publish" in cmd
    assert "--allow-partial-publish" in cmd


def test_run_pipeline_cli_rejects_unknown_args(monkeypatch):
    import run_pipeline

    monkeypatch.setattr(run_pipeline, "prepare_run_environment", lambda path: {"SIDERUST_BENCHES_CACHE": "dummy"})
    monkeypatch.setattr(run_pipeline, "subprocess", run_pipeline.subprocess)
    monkeypatch.setattr(sys, "argv", [
        "run_pipeline.py",
        "--config",
        "pipeline/configs/full_fast.toml",
        "--allow-dirty-publish",
    ])

    class DummyCompletedProcess:
        returncode = 0

    def fake_run(cmd, cwd, env):
        assert "--allow-dirty-publish" in cmd
        return DummyCompletedProcess()

    monkeypatch.setattr(run_pipeline.subprocess, "run", fake_run)
    assert run_pipeline.main() == 0

    with pytest.raises(SystemExit) as excinfo:
        monkeypatch.setattr(sys, "argv", [
            "run_pipeline.py",
            "--config",
            "pipeline/configs/full_fast.toml",
            "--unknown-flag",
        ])
        run_pipeline.main()
    assert excinfo.value.code != 0
