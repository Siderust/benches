# Contributing to Siderust Lab

## Python tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r pipeline/requirements.txt
python3 -m pytest pipeline/tests -v
```

Tests are offline: no Horizons network calls and no real DE440 download. Cache
tests monkeypatch `cache_manager.DE440_MIN_BYTES` to a small threshold via
`pipeline/tests/conftest.py`.

## Rust adapter quality gates

After building adapters:

```bash
cd pipeline/adapters/siderust_adapter
cargo build --release
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings

cd ../anise_adapter
cargo build --release
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
```

C adapters:

```bash
make -C pipeline/adapters/erfa_adapter
make -C pipeline/adapters/libnova_adapter
```

## CI-equivalent pipeline smoke

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/ci.toml
python3 -m pipeline.export_static --lab-root . --output static_export
```

`pipeline/configs/ci.toml` sets `horizons.allow_network = false`,
`cache.auto_download = false`, and `kernels.de440.enabled = false` so CI does
not require a populated DE440 cache.
