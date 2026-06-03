from pathlib import Path
import sys
import pytest
from unittest.mock import patch, MagicMock

TEST_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TEST_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

from lab_config import load_pipeline_config
from run_pipeline import build_orchestrator_command

def test_performance_config_parsing(tmp_path):
    config_path = tmp_path / "perf_test.toml"
    config_path.write_text("""
[performance]
enabled = true
rounds = 20
scalar_n = 123
batch_n = 456
batch_rounds = 7
warmup = 89
timeout_s = 99
""")
    cfg = load_pipeline_config(config_path)
    assert cfg.performance_enabled is True
    assert cfg.perf_rounds == 20
    assert cfg.perf_scalar_n == 123
    assert cfg.perf_batch_n == 456
    assert cfg.perf_batch_rounds == 7
    assert cfg.perf_warmup == 89
    assert cfg.perf_timeout_s == 99

def test_performance_config_defaults(tmp_path):
    config_path = tmp_path / "perf_default.toml"
    config_path.write_text("")
    cfg = load_pipeline_config(config_path)
    assert cfg.performance_enabled is True
    assert cfg.perf_rounds == 10
    assert cfg.perf_scalar_n == 5000
    assert cfg.perf_batch_n == 100000
    assert cfg.perf_batch_rounds == 5
    assert cfg.perf_warmup == 100
    assert cfg.perf_timeout_s == 120

def test_orchestrator_cli_receives_perf_values(tmp_path):
    config_path = tmp_path / "perf_cli.toml"
    config_path.write_text("""
[performance]
rounds = 3
scalar_n = 100
batch_n = 200
batch_rounds = 2
warmup = 10
timeout_s = 50
""")
    cmd = build_orchestrator_command(config_path)
    assert "--perf-rounds" in cmd
    assert cmd[cmd.index("--perf-rounds") + 1] == "3"
    assert "--perf-scalar-n" in cmd
    assert cmd[cmd.index("--perf-scalar-n") + 1] == "100"
    assert "--perf-batch-n" in cmd
    assert cmd[cmd.index("--perf-batch-n") + 1] == "200"
    assert "--perf-batch-rounds" in cmd
    assert cmd[cmd.index("--perf-batch-rounds") + 1] == "2"
    assert "--perf-warmup" in cmd
    assert cmd[cmd.index("--perf-warmup") + 1] == "10"
    assert "--perf-timeout-s" in cmd
    assert cmd[cmd.index("--perf-timeout-s") + 1] == "50"

def test_run_perf_workloads_uses_configured_sizes():
    from orchestrator import run_perf_workloads
    
    mock_cmd = ["dummy"]
    mock_input_gen = MagicMock(return_value=("data",))
    mock_perf_fmt = MagicMock(return_value="formatted")
    
    with patch("orchestrator.run_multi_sample_perf") as mock_run_multi:
        mock_run_multi.return_value = {"per_op_ns": 1.0, "valid": True}
        with patch("orchestrator.run_adapter") as mock_run_adapter:
            mock_run_adapter.return_value = {"setup_ms": 1.0}
            
            run_perf_workloads(
                mock_cmd, "test_exp", mock_input_gen, mock_perf_fmt, seed=42,
                scalar_rounds=2, scalar_n=50,
                batch_rounds=3, batch_n=500,
                warmup=5, timeout_s=10
            )
            
            # Check scalar workload call
            assert mock_input_gen.call_args_list[0][0] == (50, 42)
            assert mock_run_multi.call_args_list[0][1]["rounds"] == 2
            assert mock_run_multi.call_args_list[0][1]["timeout"] == 10
            
            # Check batch workload call
            assert mock_input_gen.call_args_list[1][0] == (500, 42)
            assert mock_run_multi.call_args_list[1][1]["rounds"] == 3
            assert mock_run_multi.call_args_list[1][1]["timeout"] == 10
