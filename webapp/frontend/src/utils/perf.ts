/**
 * Phase-6 performance normalization.
 * Raw experiment JSON stores workloads under scalar_warm / batch_throughput;
 * legacy consumers expect flat per_op_ns / throughput_ops_s.
 */

export function normPerfFlat(
  raw: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  if (!raw) return {};
  const scalar = raw.scalar_warm as Record<string, unknown> | undefined;
  const batch = raw.batch_throughput as Record<string, unknown> | undefined;
  if (!scalar && !batch) return raw;
  return {
    ...raw,
    per_op_ns: scalar?.ns_per_op ?? null,
    throughput_ops_s: batch?.items_per_sec ?? null,
    valid: scalar?.valid ?? true,
    rounds: scalar?.rounds ?? null,
    per_op_ns_cv_pct: scalar?.cv ?? null,
    warnings: scalar?.warnings ?? [],
  };
}

export function normRefPerfFlat(
  raw: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  return normPerfFlat(raw);
}

/** Statistically valid perf per publication policy (matches scorecard _perf_valid). */
export function perfValid(perf: Record<string, unknown> | null | undefined): boolean {
  const flat = normPerfFlat(perf ?? undefined);
  const ns = flat.per_op_ns as number | undefined;
  const cv = flat.per_op_ns_cv_pct as number | undefined;
  if (ns == null) return false;
  if (flat.valid === false) return false;
  if (ns < 10) return false;
  if (cv != null && cv > 20) return false;
  return true;
}

/** Measured ns/op even when perf is not rank-valid (never hide raw timing). */
export function measuredNsPerOp(
  perf: Record<string, unknown> | null | undefined,
): number | null {
  const flat = normPerfFlat(perf ?? undefined);
  const ns = flat.per_op_ns as number | undefined;
  return ns != null && Number.isFinite(ns) ? ns : null;
}
