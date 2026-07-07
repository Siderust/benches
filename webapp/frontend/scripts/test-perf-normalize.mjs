/**
 * Smoke test: Phase-6 performance normalization (libnova equ_horizontal).
 * Run: node scripts/test-perf-normalize.mjs
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..", "..");

function normPerfFlat(raw) {
  if (!raw) return {};
  const scalar = raw.scalar_warm;
  const batch = raw.batch_throughput;
  if (!scalar && !batch) return raw;
  return {
    ...raw,
    per_op_ns: scalar?.ns_per_op ?? null,
    throughput_ops_s: batch?.items_per_sec ?? null,
    valid: scalar?.valid ?? true,
  };
}

function measuredNsPerOp(perf) {
  const flat = normPerfFlat(perf);
  const ns = flat.per_op_ns;
  return ns != null && Number.isFinite(ns) ? ns : null;
}

const equHorizontal = JSON.parse(
  readFileSync(join(repoRoot, "latest_results/experiments/equ_horizontal.json"), "utf8"),
);
const libnova = equHorizontal.rows.find((r) => r.candidate_library === "libnova");
if (!libnova) {
  console.error("FAIL: libnova row missing in equ_horizontal.json");
  process.exit(1);
}

const ns = measuredNsPerOp(libnova.performance);
if (ns == null || !Number.isFinite(ns) || ns <= 0) {
  console.error(`FAIL: expected finite positive libnova perOpNs, got ${ns}`);
  process.exit(1);
}

console.log("OK: libnova equ_horizontal perOpNs =", ns);
