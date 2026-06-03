# Siderust Lab User Manual

This document describes the current lab workflow: run experiments locally with a
configuration file, publish result artifacts, and inspect them in a read-only
dashboard.

## Goals

The lab answers two questions with reproducible evidence:

- Accuracy: how close is each candidate to a trusted reference for a defined
  model/source?
- Performance: what is the latency or throughput cost under a reproducible
  workload?

The lab should also explain why results differ. A visible model mismatch is more
useful than a misleading ranking.

## Terminology

- **Run**: one pipeline execution, with machine and environment metadata.
- **Experiment**: one measured task such as `gmst_era` or
  `solar_position`.
- **Family**: public grouping used by the dashboard, such as time, frames,
  pointing, ephemerides, or orbital primitives.
- **Reference model**: the model/source used for scoring, for example
  `SOFA pnm06a` or `JPL Horizons`.
- **Candidate profile**: a named implementation mode for a candidate, for
  example `siderust/iau2000b`.
- **Rankable row**: a candidate result that can be compared fairly for accuracy.

## Running Experiments

Run the main public suite:

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/core.toml
```

Run the reduced CI suite:

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/ci.toml
```

Run the full suite (public + diagnostic, all profiles):

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/full.toml
```

The wrapper accepts either a config path or a suite alias:

```bash
./run.sh core
./run.sh ci
./run.sh diagnostic
./run.sh full
./run.sh phase-b ci
```

Important config fields:

- `suite`: `core`, `ci`, or `diagnostic`
- `experiments`: optional explicit experiment ids
- `n` and `seed`: accuracy input size and deterministic random seed. Note that `n` affects accuracy cases only.
- `adapters`: enabled candidate adapters
- `siderust_profiles`: enabled Siderust model profiles
- `performance`: enable timing and choose workload sizes. Quick runs use smaller `scalar_n` and `batch_n` for diagnostics; publication runs must use standardized defaults (see `pipeline/PERFORMANCE_BENCHMARKING.md`).
- `horizons`: cache and offline/network policy
- `output_dir`: where timestamped runs are written
- `publish_latest`: copy the completed run to `latest_results/` locally (blocked
  unless publication-grade; see below). The parent Astro site consumes the
  committed `latest_results/` static bundle at build time.
- `allow_dirty_publish` / `allow_partial_publish`: copy to `latest_results/`
  even when the manifest would be `draft` (dashboard shows the override)
- `run_label`, `phase`, and `tags`: optional manifest labels used by the
  Phase B baseline matrix

### Publication-grade runs

A run is **publication-grade** only when the manifest has `publication.grade =
"publication"` (no blockers). The orchestrator refuses `--publish-latest` when:

- `git_dirty.lab` is true (uncommitted lab changes), unless
  `--allow-dirty-publish`
- any **requested** experiment did not complete (`scope.partial`), unless
  `--allow-partial-publish`

The manifest also records `scope.core_complete` / `scope.core_partial` separately
from `scope.partial` so a `core+extra` run that finishes every requested
experiment is not labelled partial merely for including diagnostics.

**Checklist before citing benchmarks:**

1. Clean git tree (`git_dirty.lab` false) or document the override.
2. Full requested experiment list completed (`scope.partial` false).
3. `latest_results_merge.is_merge` is false (not a surgical merge of partial runs).
4. Public planet positions are **planet-system barycenter** experiments
   (`*_barycenter_position`), not physical centers.
5. Catalog truth tests pass (`pytest pipeline/tests/test_catalog_truth.py`).

### Phase B Baseline Matrix

Phase B presets are checked in as `pipeline/configs/phase_b_*.toml` and can be
run through the matrix wrapper:

```bash
python3 pipeline/run_phase_b.py --matrix ci
python3 pipeline/run_phase_b.py --matrix public
python3 pipeline/run_phase_b.py --matrix ephemeris
python3 pipeline/run_phase_b.py --matrix anise
python3 pipeline/run_phase_b.py --matrix performance
python3 pipeline/run_phase_b.py --matrix large
```

`--matrix all` runs every Phase B leg. The public, ephemeris, performance, and
large legs are long-running and require live or cached JPL Horizons reference
data. Every Phase B manifest records its label, phase, tags, seed, sample count,
Horizons policy, and scope so partial runs remain distinguishable.

### Full Preset

`pipeline/configs/full.toml` is the comprehensive preset intended for full
report generation:

- `suite = "all"` (public + diagnostic experiments)
- all adapters enabled (`siderust`, `astropy`, `libnova`, `anise`)
- all Siderust profiles enabled (`iau2006a`, `iau2000a`, `iau2000b`,
  `precession_only`)
- performance timing enabled (`rounds = 10`)
- Horizons cache enabled with network fallback
- `publish_latest = true` so the run is mirrored into `latest_results/`

For deterministic reruns, keep `seed` fixed. For broader stress testing,
increase `n`.

## Public Suite

The public dashboard should focus on a small suite:

- `gmst_era`: time and Earth rotation, SOFA/ERFA reference
- `frame_rotation_bpn`: ICRS to true-of-date orientation, SOFA `pnm06a`
- `equ_ecl`: ecliptic of date
- `equ_horizontal`: topocentric Alt/Az pointing
- `solar_position`, `lunar_position`, and **planet-system barycenters**
  (`*_barycenter_position`): JPL Horizons geometric VECTORS reference
- `kepler_solver`: numerical primitive and invariant benchmark

Lower-level transforms, inverse transforms, duplicated ecliptic views, and the
FROMxTO matrix belong in `diagnostic` unless a specific development task needs
them.

## Result Artifacts

The pipeline writes machine-readable JSON files:

```text
results/<run_id>/<experiment>/<candidate>.json
```

If publishing is enabled, the same completed run is exposed as:

```text
latest_results/
```

Each result contains the original metrics plus public scorecard metadata:

- `family`
- `tier`
- `candidate_profile`
- `reference_model`
- `rankable_accuracy`
- `rank_exclusion_reason`
- `source_provenance`

`source_provenance` is especially important for JPL-backed experiments. It
should record body id, center, frame, time scale, cache key/source tag, and
query policy when available.

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

Accuracy ranking is allowed only when:

- candidates use the same SOFA/IAU model, or
- the reference is an external source such as JPL Horizons, or
- the experiment is explicitly an invariant/self-consistency benchmark.

Rows with model mismatch remain visible, but they are excluded from the
accuracy winner calculation.

Performance ranking ignores invalid timings:

- `valid = false`
- CV too high
- `ns/op` below the measurable threshold

## Dashboard Behavior

The webapp is a result viewer.

The first screen for a run should show:

- latest run metadata
- reference models/sources used
- public experiment families
- neutral scorecards by family
- model parity and rankability notes

The dashboard should avoid global "overall wins" over mixed models. It should
show family tables for accuracy and performance, and show Siderust as one row
among the candidates with deltas to the best rankable candidate.

Comparability is shown per row via a **comparability class**: `exact-model`
(identical model/kernel as the reference), `same-family-jpl` (a JPL DE kernel of
a different version than the reference, e.g. DE440 vs the DE441 reference —
ranked broadly but **excluded from the strict exact-model view**),
`best-available`, `diagnostic-profile`, or `not-comparable`. The overview
exposes three distinct accuracy/performance crowns that must never be conflated:
the broad accuracy winner, the strict **exact-model-only** winner, and — for
performance — the statistically valid `best_performance` versus the diagnostic
`raw_fastest` (raw minimum ns/op, not a valid winner).

The experiment detail page should show:

- reference library and reference model/source
- candidate profile for each row
- rankability and exclusion reason
- p50, p99, and max accuracy
- `ns/op`, CV, and timing warnings
- assumptions and provenance

The public flow does not include the old Performance Matrix.

## Static Export And Frontend

The public dashboard is rendered by the parent Astro site from
`lab/latest_results/` at build time. The React frontend is an internal
standalone viewer. There is no backend.

Export benchmark data:

```bash
./run.sh export
# or
python3 -m pipeline.export_static
```

Build the dashboard:

```bash
cd webapp/frontend
npm install
npm run build:standalone # → dist/
```

## Full Pipeline To Full Reports

Use this sequence to produce complete benchmark outputs and publishable static
reports:

```bash
# 1) Build adapters and Python runtime dependencies
./run.sh build

# 2) Run the complete benchmark suite
./run.sh full

# 3) (Optional explicit export) write local static JSON report tree
./run.sh export

# 4) Build standalone frontend report app
cd webapp/frontend
npm install
npm run build:standalone
```

Artifacts produced:

- Raw run outputs in `results/<run_id>/...`
- Latest mirror in `latest_results/`
- Static data reports in `static_export/`
- Static dashboard bundle in `webapp/frontend/dist/`

Develop locally:

```bash
cd webapp/frontend
npm run dev
```

`pipeline/export_static.py` reads timestamped `results/<id>/` directories plus
the `latest_results/` mirror and writes:

- `<output>/index.json`
- `<output>/latest/{scorecard,manifest}.json`, `latest/experiments/<id>.json`
- `<output>/runs/<id>/{scorecard,manifest}.json`, `runs/<id>/experiments/<id>.json`

## Validation Checklist

- `python3 -m pytest pipeline/tests/ -v`
- `python3 pipeline/run_pipeline.py --config pipeline/configs/ci.toml`
- `python3 pipeline/run_phase_b.py --matrix ci`
- `python3 -m pipeline.export_static --output /tmp/lab-check` and inspect
  `index.json` + a `scorecard.json` for the expected lanes and source tags
- `npm run build:standalone` in `webapp/frontend` (emits to `dist/`)
