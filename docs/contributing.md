# Contributing And Local Validation

## Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r pipeline/requirements.txt
```

Run the test suite:

```bash
python3 -m pytest pipeline/tests -v
```

Tests are offline. Cache tests monkeypatch the DE440 size threshold so CI does
not require a real kernel download.

## Adapter Builds

Build all available adapters and install Python dependencies through the wrapper:

```bash
./run.sh build
```

Build C adapters directly:

```bash
make -C pipeline/adapters/erfa_adapter
make -C pipeline/adapters/libnova_adapter
```

Build Rust adapters directly:

```bash
cd pipeline/adapters/siderust_adapter
cargo build --release

cd ../anise_adapter
cargo build --release
```

## Rust Quality Gates

```bash
cd pipeline/adapters/siderust_adapter
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings

cd ../anise_adapter
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
```

## CI-Equivalent Smoke

```bash
./run.sh ci
python3 -m pipeline.export_static --lab-root . --output /tmp/lab-check
```

`pipeline/configs/ci.toml` sets `horizons.allow_network = false`,
`cache.auto_download = false`, and `kernels.de440.enabled = false`, so CI does
not need a populated DE440 cache.

## Publication Checks

Before publishing benchmark artifacts:

```bash
python3 -m pytest pipeline/tests -v
python3 -m pytest pipeline/tests/test_catalog_truth.py -v
python3 pipeline/run_pipeline.py --config pipeline/configs/publication.toml
python3 -m pipeline.export_static --lab-root . --output static_export
```

`pipeline/configs/publication.toml` enables publication workload sizes and
`publish_latest`. The orchestrator refuses publication when manifest blockers
are present unless an explicit override is passed.

## Frontend Checks

```bash
cd webapp/frontend
npm install
npm run lint
npm run build:standalone
```

The standalone build copies data from `../../static_export` into `dist/data/lab`.
