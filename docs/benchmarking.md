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
