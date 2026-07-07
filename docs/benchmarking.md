# Benchmarking And Publication Policy

This document is the source of truth for benchmark validity and publication
rules.

## Accuracy Scope

The top-level config field `n` controls the number of accuracy cases. Keep
`seed` fixed for deterministic reruns. Increase `n` only when you need broader
stress coverage and can afford the runtime.

Accuracy rows are rankable only when the catalog and orchestrator agree that the
candidate is comparable to the reference. Model mismatches stay visible, but
they do not receive accuracy crowns when the observable is not fairly
comparable.

## Performance Workloads

Performance benchmarks use workload sizes separate from accuracy tests:

| Field | Meaning | Publication default |
| --- | --- | ---: |
| `rounds` | Scalar timing rounds. | `10` |
| `scalar_n` | Per-call latency workload size. | `5000` |
| `batch_n` | Bulk throughput workload size. | `100000` |
| `batch_rounds` | Batch timing rounds. | `5` |
| `warmup` | Iterations before each round. | `100` |

`pipeline/configs/publication.toml` and `pipeline/configs/core.toml` use the
standard publication workload sizes. Fast configs such as
`pipeline/configs/full_fast.toml` are diagnostic only.

## Performance Validity

The dashboard exposes two separate performance labels:

- `best_performance`: statistically valid fastest candidate.
- `raw_fastest`: raw minimum `ns/op`, diagnostic only.

`best_performance` requires:

- `status == "ok"`
- `support_status == "supported"`
- `api_surface == "public"`
- `perf_valid == true`
- finite `ns/op >= 10`
- coefficient of variation `<= 20%`
- `valid != false`

If an adapter times fewer cases than requested, the workload is marked invalid
with an explicit warning so skipped cases cannot make a candidate look faster.
Partial rows are never rankable for accuracy or performance.

## Baseline Reuse

Baseline reuse lets the lab skip recomputing stable non-Siderust candidates while
keeping Siderust rows fresh. Baselines are **not** an ad-hoc merge of
`latest_results`; each artifact is fingerprinted, validated, and written to an
inspectable store (default: `.benches_cache/baseline_results/`).

### When reuse is safe

- **Accuracy reuse** (`reuse_accuracy = true`): allowed only when input,
  reference, catalog entry, benchmark contract, and candidate adapter fingerprints
  all match the stored artifact.
- **Performance reuse** (`reuse_performance = false | true | "same-machine-only"`):
  disabled by default. When enabled, workload and machine/toolchain fingerprints
  must also match. `same-machine-only` is the recommended publication setting.

### What invalidates a baseline

Accuracy reuse invalidates when any of these change:

- experiment inputs (`n`, `seed`, dataset fingerprint)
- reference model/source/lane
- catalog entry or `catalog.toml` content
- candidate library version or adapter binary hash
- kernel hash for JPL/SPK-backed candidates
- benchmark timing contract or result schema version

Performance reuse additionally invalidates when CPU model, platform, compiler,
or performance workload sizes change.

### Running delta configs

Normal Siderust development:

```bash
./run.sh dev-delta
python3 pipeline/run_pipeline.py --config pipeline/configs/dev_delta.toml
```

Publication-grade delta (strict baseline completeness):

```bash
./run.sh publication-delta
python3 pipeline/run_pipeline.py --config pipeline/configs/publication_delta.toml
```

Force a full refresh (equivalent to legacy full recomputation):

```bash
python3 pipeline/run_pipeline.py --config pipeline/configs/dev_delta.toml --refresh-baselines
# or disable baselines in config, or use pipeline/configs/publication.toml
```

### Dashboard badges

- `fresh`: computed in the current run.
- `baseline accuracy` / `baseline combined`: reused row with validated fingerprints.
- `stale baseline`: reuse was rejected; row must not win accuracy or performance crowns.
- `raw_fastest` remains diagnostic only and is never equivalent to `best_performance`.

## Progressive Convergence (Schema)

Optional `[convergence]` config documents progressive sample counts for future
per-experiment stopping rules. It is **disabled by default** and is not wired into
publication paths yet:

```toml
[convergence]
enabled = false
stages = [50, 100, 250, 1000]
primary_metric = "p99"
relative_tolerance = 0.02
absolute_tolerance = 1e-12
stop_after_stable_stages = 2
```

Recommended dev signal tiers: `n = 50` smoke, `100` quick, `250` stable dev,
`1000` publication.

## Diagnostic Versus Publication Runs

Diagnostic runs are useful for development and regression hunting. They may use
small sample counts, reduced timing rounds, offline-only cache policies, or
partial adapter coverage. Do not cite them as official benchmark numbers.

Publication-grade runs must satisfy the manifest publication gates:

- clean lab git tree, unless a dirty publish override was intentional
- no missing requested experiments, unless a partial publish override was
  intentional
- no surgical `latest_results` merge
- real submodule SHAs in `metadata.git_shas`
- public planet-position benchmarks use `*_barycenter_position`

Use this validation set before publishing:

```bash
python3 -m pytest pipeline/tests -v
./run.sh ci
python3 -m pytest pipeline/tests/test_catalog_truth.py -v
python3 -m pipeline.export_static --lab-root . --output /tmp/lab-check
```

For frontend validation, also run:

```bash
cd webapp/frontend
npm install
npm run build:standalone
```

## Citing Results

When citing a result, include:

- run id and manifest publication grade
- config file or matrix leg
- reference model/source
- comparability class
- sample count and seed
- performance workload sizes, if citing timing
- Horizons or kernel provenance for ephemeris rows
