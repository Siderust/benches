# Performance benchmarking

Performance crowns use **statistically valid** timings only:

- `best_performance` requires `status == "ok"`, `support_status == "supported"`,
  `api_surface == "public"`, and `perf_valid == true` (finite `ns/op ≥ 10`,
  coefficient of variation ≤ 20%, `valid != false`).
- `raw_fastest` records the minimum `ns/op` regardless of validity and is shown as
  a diagnostic only — it never receives the performance crown.

## Workload Sizes

Performance benchmarks use separate workload sizes from accuracy tests:

- `scalar_n`: Steady-state per-call latency workload size (default: 5000).
- `batch_n`: Bulk evaluation workload size for throughput (default: 100,000).
- `batch_rounds`: Number of timing rounds for batch throughput (default: 5).
- `warmup`: Iterations before each round to ensure caches are hot (default: 100).

Note that the top-level `n` parameter in the pipeline configuration controls the number of cases for **accuracy** tests only.

## Diagnostic vs Publication Runs

Quick runs (e.g., using `pipeline/configs/full_fast.toml`) use reduced workload sizes to allow for rapid iteration. These runs are strictly **diagnostic** and their performance results should not be cited as official benchmarks.

Official **publication** runs must use the standardized defaults (e.g., `pipeline/configs/publication.toml`):
- `rounds = 10`
- `scalar_n = 5000`
- `batch_n = 100000`
- `batch_rounds = 5`
- `warmup = 100`

If an adapter times fewer cases than requested (`n_per_round` / batch `n` mismatch),
the workload is marked `valid: false` with an explicit warning so skipped cases
cannot make a candidate look faster.

Accuracy and performance share the same publication gates: partial rows
(`status == "partial"`) are never rankable.
