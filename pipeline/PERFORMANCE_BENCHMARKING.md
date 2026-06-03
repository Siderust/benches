# Performance benchmarking

Performance crowns use **statistically valid** timings only:

- `best_performance` requires `status == "ok"`, `support_status == "supported"`,
  `api_surface == "public"`, and `perf_valid == true` (finite `ns/op ≥ 10`,
  coefficient of variation ≤ 20%, `valid != false`).
- `raw_fastest` records the minimum `ns/op` regardless of validity and is shown as
  a diagnostic only — it never receives the performance crown.

If an adapter times fewer cases than requested (`n_per_round` / batch `n` mismatch),
the workload is marked `valid: false` with an explicit warning so skipped cases
cannot make a candidate look faster.

Accuracy and performance share the same publication gates: partial rows
(`status == "partial"`) are never rankable.
