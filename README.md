# Siderust Lab

Siderust Lab is a reproducible benchmark laboratory for comparing `siderust`
against other astronomy and astrodynamics tools. The pipeline runs local
experiments from TOML configuration, and the dashboard reads static JSON
artifacts.

Canonical documentation is centralized in [`docs/`](docs/README.md):

- [Lab overview and usage](docs/README.md)
- [Benchmarking and publication policy](docs/benchmarking.md)
- [Contributing and local validation](docs/contributing.md)
- [Frontend dashboard](docs/frontend.md)

## Quick Start

```bash
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
pip install -r pipeline/requirements.txt
./run.sh ci
./run.sh dev-delta
```

For the maintained command reference, result layout, suite definitions,
fairness rules, and publication checklist, see [`docs/README.md`](docs/README.md).
