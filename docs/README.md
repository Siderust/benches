# Siderust Lab Documentation

Siderust Lab measures `siderust` against other astronomy and astrodynamics
tools with traceable assumptions. The lab has two responsibilities:

- `pipeline/` runs reproducible experiments locally from TOML configuration.
- `webapp/frontend/` is an internal read-only React/Vite viewer for exported
  result artifacts.

The public `siderust.github.io` benchmark page is rendered by the parent Astro
site from static lab artifacts. There is no runtime benchmark API and no web
endpoint that launches benchmarks.

## Documentation Map

- [Benchmarking and publication policy](benchmarking.md)
- [Contributing and local validation](contributing.md)
- [Frontend dashboard](frontend.md)

Compatibility entry points remain at the repository root:

- `README.md`
- `USER_MANUAL.md`
- `CONTRIBUTING.md`
- `pipeline/PERFORMANCE_BENCHMARKING.md`
- `webapp/frontend/README.md`

Vendored dependency docs under `pipeline/adapters/*/vendor/` are third-party
documentation and are not maintained by this lab.

## Reference Sources

The lab uses model/source references, not wrapper libraries, as the authority:

- Transformations, time, and Earth orientation: SOFA / IAU conventions. ERFA
  and Astropy may execute these models, but the reference is the SOFA model and
  documented convention.
- Sun, Moon, and planet ephemerides: JPL Horizons or a documented JPL DE source.
- Numerical primitives such as `kepler_solver`: invariant or self-consistency
  checks, not astronomical truth claims.

If candidate libraries use different physical models, the result is marked as a
model mismatch and excluded from accuracy ranking where appropriate.

## Repository Layout

Lab-owned paths:

- `pipeline/orchestrator.py`: experiment orchestration.
- `pipeline/run_pipeline.py`: TOML-driven local runner.
- `pipeline/run_phase_b.py`: Phase B baseline matrix runner.
- `pipeline/configs/*.toml`: public, CI, publication, full-suite, fast, and
  Phase B presets.
- `pipeline/adapters/`: per-tool wrapper binaries and scripts.
- `pipeline/horizons_client.py`: JPL Horizons cache/network integration.
- `pipeline/scorecard.py` and `pipeline/export_static.py`: static export
  helpers.
- `webapp/frontend/src/`: internal React/Vite dashboard.
- `results/`: timestamped generated run artifacts.
- `latest_results/`: optional publication mirror produced by publication-grade
  runs.
- `static_export/`: local scratch static export for standalone/internal viewers.

Vendored comparison libraries are submodules under `pipeline/adapters/*/vendor/`.
Initialize them before building adapters:

```bash
git submodule update --init --recursive
```

## Quick Start

Create the Python environment and run the small offline CI suite:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r pipeline/requirements.txt
./run.sh ci
```

`./run.sh ci` builds available adapters, runs `pipeline/configs/ci.toml`, and
refreshes `static_export/` and `latest_results/`. The CI config disables
Horizons network access and DE440 auto-downloads.

## Suites

Suite aliases are defined in `pipeline/lab_config.py`:

| Suite | Purpose |
| --- | --- |
| `core` | Public benchmark suite. |
| `ci` | Small offline smoke suite. |
| `ephemeris` | Public ephemeris lanes only. |
| `diagnostic` | Lower-level transform and apparent ephemeris diagnostics. |
| `all` | Public plus diagnostic experiments. |

The public `core` suite contains:

- `gmst_era`
- `frame_rotation_bpn`
- `equ_ecl`
- `equ_horizontal`
- `solar_position`
- `lunar_position`
- `*_barycenter_position` planet-system barycenter experiments
- `kepler_solver`

Physical planet-center experiments are diagnostic only. Public planet-position
benchmarks use planet-system barycenters so DE440-capable adapters can be
compared without requiring satellite center-offset kernels.

## Running The Pipeline

Run a config directly:

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/core.toml
python3 pipeline/run_pipeline.py --config pipeline/configs/ci.toml
python3 pipeline/run_pipeline.py --config pipeline/configs/full.toml
```

Use the shell wrapper for build + run + export:

```bash
./run.sh core
./run.sh ci
./run.sh full
./run.sh pipeline/configs/publication.toml
```

For draft or smoke publication override runs:

```bash
./run.sh pipeline/configs/full_fast.toml --allow-dirty-publish --allow-partial-publish
```

For a publication-grade run:

```bash
./run.sh pipeline/configs/publication.toml
```

`run.sh` maps aliases to files in `pipeline/configs/`. For example, a
`diagnostic` alias would resolve to `pipeline/configs/diagnostic.toml`; that
file is not currently checked in. To run diagnostics with the current configs,
use a TOML whose `suite` is `diagnostic` or `all`; `pipeline/configs/full.toml`
uses `suite = "all"`.

Important config fields:

- `suite`: `core`, `ci`, `ephemeris`, `diagnostic`, or `all`.
- `experiments`: optional explicit experiment ids.
- `n` and `seed`: accuracy input count and deterministic random seed.
- `adapters`: enabled candidate adapters.
- `siderust_profiles`: enabled Siderust model profiles.
- `performance`: timing enablement and workload sizes.
- `horizons`: cache and offline/network policy.
- `cache`: benchmark cache root and DE440 auto-download policy.
- `output`: result directory, `publish_latest`, and publication overrides.
- `run_label`, `phase`/`run_phase`, and `tags`/`run_tags`: manifest labels.

Available Siderust profiles:

- `iau2006a`
- `iau2000a`
- `iau2000b`
- `precession_only`

Profiles without model parity against the reference remain visible but are not
ranked for accuracy.

## Phase B Matrix

Phase B presets live in `pipeline/configs/phase_b_*.toml`:

```bash
python3 pipeline/run_phase_b.py --matrix ci
python3 pipeline/run_phase_b.py --matrix public
python3 pipeline/run_phase_b.py --matrix ephemeris
python3 pipeline/run_phase_b.py --matrix anise
python3 pipeline/run_phase_b.py --matrix performance
python3 pipeline/run_phase_b.py --matrix large
python3 pipeline/run_phase_b.py --matrix all
```

`--matrix ci` is the default small offline leg. Public, ephemeris, performance,
large, and all matrix runs can be long and require live or cached JPL Horizons
data depending on the selected config.

After successful runs, `run_phase_b.py` exports static data to the parent site's
`public/data/lab` path unless `--skip-export` is passed.

## Cache And Kernel Data

The wrapper and runner use `.benches_cache/` by default:

- `.benches_cache/kernels/de440.bsp`
- `.benches_cache/siderust_datasets/`

`pipeline/run_pipeline.py` exports the cache environment through
`pipeline/cache_manager.py`. If a selected run needs DE440 and the kernel is not
cached, `cache.auto_download` and `horizons.allow_network` decide whether the
runner may fetch it.

JPL Horizons responses are cached by the Horizons client under the configured
cache root. Set `horizons.allow_network = false` for offline-only operation; the
run fails with a descriptive error when a required cache entry is missing.

The ANISE adapter searches `ANISE_BSP_PATH` first. `run.sh` sets it to the
benchmark cache DE440 path by default:

```bash
export ANISE_BSP_PATH=/path/to/de440.bsp
python3 pipeline/run_pipeline.py --config pipeline/configs/core.toml
```

For diagnostic physical planet-center lanes, Siderust's exact SPK center profile
may also need satellite center-offset kernels:

| Center lane | Required runtime SPK |
| --- | --- |
| `mars_position` | `mar099.bsp` |
| `jupiter_position` | `jup365.bsp` |
| `saturn_position` | `sat441l.bsp` |
| `uranus_position` | `ura184.bsp` |
| `neptune_position` | `nep097.bsp` |

## Result Artifacts

Raw run output:

```text
results/<run_id>/<experiment>/<candidate>.json
```

Publication mirror, when enabled and allowed:

```text
latest_results/
```

Local static export:

```text
static_export/
```

Export static data explicitly:

```bash
./run.sh export
python3 -m pipeline.export_static --lab-root . --output static_export
```

Static export layout:

- `index.json`: run list and latest pointer.
- `latest/{scorecard,manifest}.json`
- `latest/experiments/<id>.json`
- `runs/<run_id>/{scorecard,manifest}.json`
- `runs/<run_id>/experiments/<id>.json`

Result rows may include public scorecard metadata:

- `family`
- `tier`
- `candidate_profile`
- `reference_model`
- `rankable_accuracy`
- `rank_exclusion_reason`
- `source_provenance`

`source_provenance` records the body id, center, frame, time scale, cache
key/source tag, and query policy when available.

## Fairness Rules

Every experiment must state its assumptions:

- units and angle conventions
- frames and axes
- time scales and epoch representation
- UT1/EOP and polar motion policy
- geodesy and observer height policy
- refraction, aberration, and light-time policy
- precession/nutation/sidereal-time model
- ephemeris source and source tag

Accuracy ranking is allowed only when candidates use the same SOFA/IAU model,
the reference is an external source such as JPL Horizons, or the experiment is
explicitly an invariant/self-consistency benchmark. Rows with model mismatch
remain visible but are excluded from the accuracy winner calculation when they
are not comparable.

Comparability classes:

| Class | Meaning | Broad rank | Strict exact-model rank |
| --- | --- | :---: | :---: |
| `exact-model` | Identical model/kernel as the reference. | Yes | Yes |
| `same-family-jpl` | JPL DE kernel of a different version than the reference. | Yes | No |
| `best-available` | Different model with the same observable. | Yes | No |
| `diagnostic-profile` | Opt-in alternate profile. | No | No |
| `not-comparable` | Different observable or missing parity. | No | No |

Performance ranking ignores invalid timings. See
[`benchmarking.md`](benchmarking.md) for the performance validity rules.

## Publication Checklist

Before citing or committing publication artifacts:

1. `python3 -m pytest pipeline/tests -v` passes.
2. `./run.sh ci` passes.
3. The intended public run completed with `scope.partial == false`.
4. `git_dirty.lab == false`, or the dirty override is intentionally documented.
5. `latest_results_merge.is_merge == false`.
6. Public planet rows use `*_barycenter_position`.
7. No ranked rows have `status` in `partial`, `failed`, or `skipped`.
8. Catalog truth tests pass:

   ```bash
   python3 -m pytest pipeline/tests/test_catalog_truth.py -v
   ```

`--publish-latest` is refused unless the run is publication-grade, except when
`--allow-dirty-publish` and/or `--allow-partial-publish` are explicitly passed.

## Interpreting Results

Do not treat a global aggregate over mixed models as a correctness claim. Use
family scorecards and experiment detail pages to check:

- reference model/source
- candidate profile
- rankability and exclusion reason
- p50, p99, and max accuracy
- valid performance, `ns/op`, coefficient of variation, and warnings
- source provenance for JPL-backed experiments
