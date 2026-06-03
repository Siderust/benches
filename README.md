# Siderust Lab

This repository is a virtual laboratory for measuring **siderust** against other
astronomy and astrodynamics tools with traceable assumptions.

The public lab is now split into two responsibilities:

- `pipeline/` runs reproducible experiments locally from TOML configuration.
- `webapp/` is a read-only viewer for published result artifacts.

The web UI does not launch benchmarks. This keeps the public dashboard focused
on interpreting results instead of mixing execution controls with comparative
analysis.

## References

The lab uses model/source references, not wrapper libraries, as the authority:

- Transformations, time, and Earth orientation: **SOFA / IAU conventions**.
  ERFA and Astropy may execute these models, but the reference is the SOFA model
  and documented convention.
- Sun, Moon, and planet ephemerides: **JPL ephemerides**, normally via JPL
  Horizons or a documented DE source.
- Numerical primitives such as `kepler_solver`: invariant/self-consistency
  checks, not astronomical truth claims.

If candidate libraries use different physical models, the result is marked as a
model mismatch and excluded from accuracy ranking.

## Repository Layout

Vendored comparison libraries are submodules:

- `siderust/`
- `anise/`
- `astropy/`
- `erfa/`
- `libnova/`

Lab-owned entrypoints:

- `pipeline/orchestrator.py` - experiment orchestration
- `pipeline/run_pipeline.py` - TOML-driven local runner
- `pipeline/configs/*.toml` - public, CI, and diagnostic suites
- `pipeline/adapters/` - per-tool wrapper binaries/scripts
- `pipeline/horizons_client.py` - JPL Horizons cache/network integration
- `pipeline/scorecard.py` / `pipeline/export_static.py` - static export helpers for internal/standalone viewers
- `webapp/frontend/src/` - internal React/Vite standalone dashboard
- `results/` and `latest_results/` - generated run artifacts

Initialize submodules before running adapters:

```bash
git submodule update --init --recursive
```

## Suites

The default public suite is intentionally small:

- `gmst_era` - time and Earth rotation, SOFA/ERFA reference
- `frame_rotation_bpn` - ICRS to true-of-date orientation, SOFA `pnm06a`
- `equ_ecl` - ecliptic of date transform
- `equ_horizontal` - topocentric Alt/Az pointing
- `solar_position`, `lunar_position`, and planet-system barycenter experiments
  (`*_barycenter_position`) — JPL Horizons geometric VECTORS reference
- `kepler_solver` - numerical invariant benchmark

The diagnostic suite keeps lower-level and redundant transforms for development:
`inv_*`, `frame_bias`, `obliquity`, `bias_precession`,
`precession_nutation`, `icrs_ecl_j2000`, `icrs_ecl_tod`, and related
FROMxTO coverage. These are not part of the public scorecard by default.

## Running The Pipeline

Use the config runner:

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/core.toml
```

The shell wrapper delegates to the same runner:

```bash
./run.sh pipeline/configs/core.toml
./run.sh pipeline/configs/ci.toml
./run.sh diagnostic
./run.sh phase-b ci
```

Config files define:

- suite and experiment selection
- sample count `n` and random `seed`
- adapters and siderust profiles
- performance measurement settings
- Horizons cache and offline/network policy
- output directory
- whether to publish the run to `latest_results/`
- optional run labels (`run_label`, `phase`, `tags`) written into the
  manifest for Phase B matrix runs

Phase B baseline presets live in `pipeline/configs/phase_b_*.toml`. The matrix
runner executes named legs and refreshes the static export after successful
runs:

```bash
python3 pipeline/run_phase_b.py --matrix ci          # small offline smoke
python3 pipeline/run_phase_b.py --matrix public      # 3 public seeds
python3 pipeline/run_phase_b.py --matrix all         # long live/cached baseline
```

The full Phase B matrix includes a small CI run, three normal public seeds, an
ephemeris-focused run, an ANISE/JPL-family run, a timing-stability run, and a
large validation run. Public/ephemeris/large legs require live or cached JPL
Horizons data.

Available siderust profiles are:

- `iau2006a`
- `iau2000a`
- `iau2000b`
- `precession_only`

Profiles without model parity against the reference remain visible but are not
ranked for accuracy.

## Execution Guide

### Prerequisites

1. **Build the siderust adapter** (requires Rust toolchain):

   ```bash
   cd pipeline/adapters/siderust_adapter
   cargo build --release
   ```

2. **Initialize all submodules** (first time or after re-clone):

   ```bash
   git submodule update --init --recursive
   ```

3. **Install Python dependencies** (standard Python ≥ 3.11):

   ```bash
   pip install -r pipeline/requirements.txt
   ```

### Quick Path

Run the public core suite with the Horizons cache (no network required if
already cached):

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/core.toml
```

### Full Path

Run all public experiments with performance measurement and publish the
results to `latest_results/`:

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/core.toml
```

`pipeline/configs/core.toml` has `publish_latest = true`.

Run the diagnostic suite (frame-transform primitives, siderust only):

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/diagnostic.toml
```

### Horizons Cache Behavior

JPL Horizons queries are cached on disk under `pipeline/horizons_cache/`.
Re-running with the same experiment, epoch range, and sample count uses the
cached response — no network needed.

Set `horizons.allow_network = true` in the TOML to fetch new data when the
cache is cold. Set `horizons.allow_network = false` to enforce offline-only
operation; the run will fail with a descriptive error if a required cache entry
is missing.

### ANISE / SPK Dataset Configuration

The `anise` adapter requires a JPL DE440 or DE441 SPK kernel.  The adapter
searches the following locations in order:

1. The path in the `ANISE_BSP_PATH` environment variable.
2. The default Siderust dataset directory (`~/.siderust/data/`).

If no kernel is found the adapter exits with a non-zero status and an
actionable message explaining which path was checked.  The runner records the
failure in the result file and continues with the remaining candidates.  The
run does not abort.

To configure the SPK path explicitly:

```bash
export ANISE_BSP_PATH=/path/to/de440.bsp
python3 pipeline/run_pipeline.py --config pipeline/configs/core.toml
```

### SideRust Planet-Center SPK Configuration (diagnostic lane)

Public **core** planet-position benchmarks use **planet-system barycenters**
(NAIF IDs 1–8; experiment IDs `*_barycenter_position`).  Physical planet-center
experiments (`mercury_position` … `neptune_position`) are **diagnostic only**
and are not ranked on the public scoreboard.

The solar and lunar public experiments use the Sun and Moon body targets.
For the diagnostic planet-center experiments the planetary DE kernel supplies
the base JPL motion; the note below covers the extra center-offset data needed
for outer planets with satellites.

The exact SideRust center profile, `siderust:spk_center`, resolves a runtime
SPK stack.  Mercury and Venus centers are available from the planetary DE
kernel, but Mars through Neptune center lanes need the corresponding satellite
SPK center-offset kernel as well:

| Center lane | Required runtime SPK |
|---|---|
| `mars_position` | `mar099.bsp` |
| `jupiter_position` | `jup365.bsp` |
| `saturn_position` | `sat441l.bsp` |
| `uranus_position` | `ura184.bsp` |
| `neptune_position` | `nep097.bsp` |

Without that offset kernel the exact SideRust center row is skipped.  The
default `siderust` row still appears, but it is the analytic VSOP87 profile and
is not the high-accuracy center path.

The runtime adapter searches `SIDERUST_PLANET_KERNELS` first, then the cache
roots selected by `SIDERUST_DATASETS_DIR` and `SIDERUST_DATA_DIR`.  The vendored
Siderust prefetcher can prepare a partial or full center stack:

```bash
export SIDERUST_DATASETS_DIR="$PWD/.siderust_datasets"
pipeline/adapters/siderust_adapter/vendor/siderust/scripts/prefetch_datasets.sh \
    --de440 --mar099 --jup365
python3 pipeline/run_pipeline.py --config pipeline/configs/core.toml
```

### Result and Export Locations

| Location | Contents |
|---|---|
| `results/<timestamp>/` | Raw per-experiment JSON for a single run |
| `latest_results/` | Versioned latest static bundle consumed by the parent Astro dashboard |
| `static_export/` | Local scratch static export for internal/standalone viewers |

Export a local static report tree for standalone/internal viewers:

```bash
python3 -m pipeline.export_static
```

## Result Artifacts

Each completed run writes timestamped output under:

```text
results/<YYYY-MM-DD_HH-MM-SS>/<experiment>/<candidate>.json
```

When `publish_latest = true` on a **publication-grade** run, the completed run is
also copied to `latest_results/` locally by the pipeline. For the parent Astro
site, `latest_results/` is the committed latest static bundle
(`scorecard.json`, `manifest.json`, `experiments/<id>.json`); do not commit
stale, dirty, partial, or accidental artifacts.

Result JSON files remain backward-compatible and may include these public
scorecard fields:

- `family`
- `tier`
- `candidate_profile`
- `reference_model`
- `rankable_accuracy`
- `rank_exclusion_reason`
- `source_provenance`

## Ranking Policy

### Comparability classes

Every candidate row is tagged with a **comparability class** describing how
fairly it can be compared to the reference for that experiment. The reference
for ephemeris experiments is **JPL Horizons DE441**.

| Class | Meaning | Ranked in broad view | Ranked in strict *exact-model* view |
|-------|---------|:---:|:---:|
| `exact-model` | Identical model/kernel as the reference (e.g. SOFA IAU 2006/2000A transforms vs the SOFA reference, or a true DE441 ephemeris candidate). | ✅ | ✅ |
| `same-family-jpl` | A JPL DE kernel of a **different version** than the reference — e.g. a **DE440** candidate (siderust embedded DE440, ANISE `de440.bsp`, Astropy DE440) compared against the **DE441** Horizons reference. Comparable, but the DE440↔DE441 delta is part of the residual. | ✅ | ❌ |
| `best-available` | A different model with the same observable (VSOP87 / Meeus / ELP2000 vs JPL). | ✅ | ❌ |
| `diagnostic-profile` | Opt-in alternate profile; shown, never ranked. | ❌ | ❌ |
| `not-comparable` | Different observable or missing parity. | ❌ | ❌ |

The catalog (`pipeline/catalog.toml`) tags each `(candidate, experiment)` with a
`parity` drawn from six classes — `exact-same-kernel`, `same-family-jpl`,
`best-available`, `model-mismatch`, `diagnostic-only`, `reference` — which the
orchestrator maps onto the comparability classes above.

**Important:** DE440 is **never** crowned in the strict exact-model view against
the DE441 reference. The dashboard exposes the *exact-model-only* accuracy
winner separately from the broad best-available winner so the two can never be
confused.

### Performance validity

Performance has two crowns that are never conflated:

- `best_performance` — the **statistically valid** fastest candidate. A row only
  qualifies when `perf_valid` is true: a finite `ns/op ≥ 10`, coefficient of
  variation `≤ 20%`, and `valid != false`.
- `raw_fastest` — the raw minimum `ns/op` regardless of validity, shown only as a
  diagnostic. It is explicitly **not** equivalent to a statistically valid winner.

### Run scope, publication grade, and provenance

Every manifest declares:

- `scope.partial` — true when any **requested** experiment did not complete (not
  only when core experiments are missing).
- `scope.core_complete` / `scope.core_partial` — canonical public suite coverage.
- `publication.grade` — `publication` or `draft` (dirty tree, partial scope, or
  explicit publish overrides).
- `latest_results_merge.is_merge` — true only for intentional surgical merges.

`--publish-latest` is refused unless the run is publication-grade, unless you pass
`--allow-dirty-publish` and/or `--allow-partial-publish` (surfaced in the
dashboard). Submodule SHAs in `metadata.git_shas` must be real commit ids, not
`unknown`, for publication-grade artifacts.

### Publication-grade checklist

1. `./run.sh ci` and `pytest pipeline/tests` pass.
2. Core suite completed with `scope.partial == false` and `git_dirty.lab == false`.
3. Public planet benchmarks use `*_barycenter_position` (system barycenter), not
   physical planet centers.
4. No ranked rows with `status` in `partial`, `failed`, `skipped`, or catalog
   `support` other than `supported`.
5. Re-run `pipeline/configs/core.toml` and export static data before updating
   `latest_results/`.

## Static Dashboard

The lab no longer ships a runtime API for the public site. The official
`siderust.github.io` Astro benchmarks page reads the versioned latest bundle
directly from `lab/latest_results/` at build time.

Export a local static tree from the most recent runs for standalone/internal
viewers:

```bash
./run.sh export                                 # → static_export/
# or, explicitly
python3 -m pipeline.export_static --output static_export
```

Build the standalone dashboard:

```bash
cd webapp/frontend
npm install
npm run build:standalone                       # → dist/
```

Develop the dashboard against the exported JSON:

```bash
cd webapp/frontend
npm run dev
```

(The dev server expects the JSON tree to be reachable at `/data/lab/`; use
`npm run build:standalone` when you need a fully self-contained bundle.)

Static layout:

- `/data/lab/index.json` — list of runs + `latest` pointer
- `/data/lab/latest/{scorecard,manifest}.json` + `experiments/<id>.json`
- `/data/lab/runs/<run_id>/{scorecard,manifest}.json` + `experiments/<id>.json`

There is no backend service, no `/api/...` surface, and no benchmark
execution endpoint.

## Validation

Run the pipeline tests:

```bash
python3 -m pytest pipeline/tests/ -v
```

Run a small CI suite:

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/ci.toml
```

Run the Phase B CI leg and refresh static data:

```bash
python3 pipeline/run_phase_b.py --matrix ci
```

Verify the frontend:

```bash
cd webapp/frontend
npm run build
```

Spot-check the exported tree:

```bash
python3 -m pipeline.export_static --output /tmp/lab-check
jq '.latest, (.runs | length)' /tmp/lab-check/index.json
```

## Interpreting Results

Every experiment should state units, frames, time scales, Earth orientation
inputs, geodesy, refraction, light-time/aberration policy, and ephemeris source
where relevant.

Do not treat a global aggregate over mixed models as a claim of correctness. Use
the family scorecards and experiment detail pages to understand:

- which reference/model was used
- which candidates are rankable
- p50, p99, and max error
- valid performance, `ns/op`, and CV
- source provenance such as JPL Horizons body id, center, frame, time scale, and
  cache tag

## Related Documentation

- `USER_MANUAL.md` - result artifacts, fairness rules, and dashboard behavior


cd lab
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
