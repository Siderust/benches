/**
 * Analytics utilities — process RunDetail into structured summaries
 * for performance charts, accuracy charts, ranking tables, and
 * pairwise comparison matrices.
 */

import type { ExperimentResult, PercentileStats, RunDetail } from "../api/types";
import { LIBRARY_COLORS } from "../api/types";
import { candidateId } from "../components/CandidateBadges";

// ─── Primary metric detection ────────────────────────────────────────

interface PrimaryMetric {
  key: string;
  label: string;
  unit: string;
  stats: PercentileStats | null;
}

const METRIC_PRIORITY: [string, string, string][] = [
  ["angular_error_mas", "Angular Error", "mas"],
  ["gmst_error_arcsec", "GMST Error", "arcsec"],
  ["angular_sep_arcsec", "Angular Separation", "arcsec"],
  ["E_error_rad", "Kepler E Error", "rad"],
  ["consistency_error_rad", "Consistency Error", "rad"],
  ["nu_error_rad", "True Anomaly Error", "rad"],
];

export function getPrimaryMetric(
  accuracy: Record<string, unknown>,
): PrimaryMetric {
  for (const [key, label, unit] of METRIC_PRIORITY) {
    const val = accuracy[key];
    if (val && typeof val === "object") {
      return { key, label, unit, stats: val as PercentileStats };
    }
  }
  return { key: "", label: "Error", unit: "", stats: null };
}

// ─── Structured analytics ────────────────────────────────────────────

export interface LibPerformance {
  library: string;
  perOpNs: number | null;
  throughputOpsS: number | null;
  isReference: boolean;
}

export interface LibAccuracy {
  library: string;
  p50: number | null;
  p90: number | null;
  p95: number | null;
  p99: number | null;
  max: number | null;
  min: number | null;
  mean: number | null;
  rms: number | null;
  rankable: boolean;
}

export interface ExperimentAnalytics {
  name: string;
  displayName: string;
  referenceLibrary: string;
  metricLabel: string;
  unit: string;
  performance: LibPerformance[];
  accuracy: LibAccuracy[];
  fastest: string | null;
  mostAccurate: string | null;
}

export interface RunAnalytics {
  experiments: ExperimentAnalytics[];
  candidateLibraries: string[];
  allLibraries: string[];
  referenceLibrary: string;
  overallFastest: string | null;
  overallMostAccurate: string | null;
  overallBestTradeoff: string | null;
}

/** Human-readable experiment display names. */
const DISPLAY_NAMES: Record<string, string> = {
  frame_rotation_bpn: "Frame Rotation (BPN)",
  gmst_era: "GMST / ERA",
  equ_ecl: "Equ → Ecl",
  equ_horizontal: "Equ → Horizontal",
  solar_position: "Solar Position",
  lunar_position: "Lunar Position",
  mercury_position: "Mercury Position",
  venus_position: "Venus Position",
  mars_position: "Mars Position",
  jupiter_position: "Jupiter Position",
  saturn_position: "Saturn Position",
  uranus_position: "Uranus Position",
  neptune_position: "Neptune Position",
  kepler_solver: "Kepler Solver",
  frame_bias: "Frame Bias",
  precession: "Precession",
  nutation: "Nutation",
  icrs_ecl_j2000: "ICRS → Ecl J2000",
  icrs_ecl_tod: "ICRS → Ecl of Date",
  horiz_to_equ: "Horiz → Equatorial",
};

export function analyzeRun(run: RunDetail): RunAnalytics {
  const candidateLibs = new Set<string>();
  const allLibs = new Set<string>();
  const referenceLibraries = new Set<string>();
  const experiments: ExperimentAnalytics[] = [];

  for (const [expName, results] of Object.entries(run.experiments)) {
    const refLib = results[0]?.reference_library ?? "erfa";
    referenceLibraries.add(refLib);
    allLibs.add(refLib);

    const performance: LibPerformance[] = [];
    const accuracy: LibAccuracy[] = [];
    let metricLabel = "Error";
    let unit = "";

    // Reference performance (from first result that has it)
    for (const r of results) {
      const refPerf = r.reference_performance as Record<string, unknown>;
      if (refPerf?.per_op_ns != null) {
        performance.push({
          library: refLib,
          perOpNs: refPerf.per_op_ns as number,
          throughputOpsS: (refPerf.throughput_ops_s as number) ?? null,
          isReference: true,
        });
        break;
      }
    }

    for (const r of results) {
      const id = candidateId(r);
      candidateLibs.add(id);
      allLibs.add(id);

      // Performance
      const perf = r.performance as Record<string, unknown>;
      if (perf?.per_op_ns != null) {
        performance.push({
          library: id,
          perOpNs: perf.per_op_ns as number,
          throughputOpsS: (perf.throughput_ops_s as number) ?? null,
          isReference: false,
        });
      }

      // Accuracy
      const metric = getPrimaryMetric(
        r.accuracy as Record<string, unknown>,
      );
      // First-valid-wins: only update the metric label/unit when we haven't
      // found a row with real accuracy data yet.
      if (metricLabel === "Error" && metric.stats !== null) {
        metricLabel = metric.label;
        unit = metric.unit;
      }

      if (metric.stats) {
        accuracy.push({
          library: id,
          p50: metric.stats.p50,
          p90: metric.stats.p90,
          p95: metric.stats.p95,
          p99: metric.stats.p99,
          max: metric.stats.max,
          min: metric.stats.min,
          mean: metric.stats.mean,
          rms: metric.stats.rms,
          rankable: r.rankable_accuracy === true,
        });
      }
    }

    // Rankings
    const candPerf = performance.filter(
      (p) => !p.isReference && p.perOpNs != null,
    );
    const fastest =
      candPerf.length > 0
        ? candPerf.reduce((a, b) => (a.perOpNs! < b.perOpNs! ? a : b))
            .library
        : null;

    // Rank tuple: p99 → max → rms → mean → p50 → library name (all lower-is-better).
    // Only include candidates that are marked rankable.
    const _v = (x: number | null | undefined): [number, number] =>
      x == null ? [1, 0] : [0, Math.abs(x)];
    const _rankKey = (
      a: LibAccuracy,
    ): [
      [number, number],
      [number, number],
      [number, number],
      [number, number],
      [number, number],
      string,
    ] => [
      _v(a.p99),
      _v(a.max),
      _v(a.rms),
      _v(a.mean),
      _v(a.p50),
      a.library,
    ];
    const _isMoreAccurate = (a: LibAccuracy, b: LibAccuracy): boolean => {
      const ka = _rankKey(a);
      const kb = _rankKey(b);
      for (let i = 0; i < ka.length; i++) {
        const ai = ka[i] as unknown;
        const bi = kb[i] as unknown;
        if (typeof ai === "string")
          return (ai as string) < (bi as string);
        const [af, av] = ai as [number, number];
        const [bf, bv] = bi as [number, number];
        if (af !== bf) return af < bf;
        if (av !== bv) return av < bv;
      }
      return false;
    };

    const candAcc = accuracy.filter((a) => a.rankable && a.p99 != null);
    const mostAccurate =
      candAcc.length > 0
        ? candAcc.reduce((a, b) => (_isMoreAccurate(a, b) ? a : b)).library
        : null;

    experiments.push({
      name: expName,
      displayName: DISPLAY_NAMES[expName] ?? expName,
      referenceLibrary: refLib,
      metricLabel,
      unit,
      performance,
      accuracy,
      fastest,
      mostAccurate,
    });
  }

  // Overall rankings (count wins across experiments)
  const perfWins: Record<string, number> = {};
  const accWins: Record<string, number> = {};
  for (const exp of experiments) {
    if (exp.fastest)
      perfWins[exp.fastest] = (perfWins[exp.fastest] ?? 0) + 1;
    if (exp.mostAccurate)
      accWins[exp.mostAccurate] = (accWins[exp.mostAccurate] ?? 0) + 1;
  }

  const overallFastest =
    Object.entries(perfWins).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  const overallMostAccurate =
    Object.entries(accWins).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;

  // Best tradeoff: library that appears most in combined (fastest + most accurate)
  const combined: Record<string, number> = {};
  for (const [lib, count] of Object.entries(perfWins)) {
    combined[lib] = (combined[lib] ?? 0) + count;
  }
  for (const [lib, count] of Object.entries(accWins)) {
    combined[lib] = (combined[lib] ?? 0) + count;
  }
  const overallBestTradeoff =
    Object.entries(combined).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;

  // Determine global reference library ("erfa" if uniform, else mixed)
  const referenceLibrary = referenceLibraries.size === 1
    ? Array.from(referenceLibraries)[0]
    : "mixed";

  return {
    experiments: experiments.sort((a, b) => a.name.localeCompare(b.name)),
    candidateLibraries: Array.from(candidateLibs).sort(),
    allLibraries: Array.from(allLibs).sort(),
    referenceLibrary,
    overallFastest,
    overallMostAccurate,
    overallBestTradeoff,
  };
}

// ─── Pairwise comparison matrix ──────────────────────────────────────

export interface PairwiseCell {
  libRow: string;
  libCol: string;
  accuracyWins: number;
  performanceWins: number;
  totalExperiments: number;
}

export function computePairwiseMatrix(
  analytics: RunAnalytics,
): PairwiseCell[] {
  const libs = analytics.candidateLibraries;
  const cells: PairwiseCell[] = [];

  for (const libA of libs) {
    for (const libB of libs) {
      if (libA === libB) {
        cells.push({
          libRow: libA,
          libCol: libB,
          accuracyWins: 0,
          performanceWins: 0,
          totalExperiments: 0,
        });
        continue;
      }

      let accWins = 0;
      let perfWins = 0;
      let total = 0;

      for (const exp of analytics.experiments) {
        const accA = exp.accuracy.find((a) => a.library === libA);
        const accB = exp.accuracy.find((a) => a.library === libB);

        if (accA?.p99 != null && accB?.p99 != null) {
          total++;
          if (Math.abs(accA.p99) < Math.abs(accB.p99)) accWins++;
        }

        const perfA = exp.performance.find((p) => p.library === libA);
        const perfB = exp.performance.find((p) => p.library === libB);
        if (perfA?.perOpNs != null && perfB?.perOpNs != null) {
          if (perfA.perOpNs < perfB.perOpNs) perfWins++;
        }
      }

      cells.push({
        libRow: libA,
        libCol: libB,
        accuracyWins: accWins,
        performanceWins: perfWins,
        totalExperiments: total,
      });
    }
  }

  return cells;
}

// ─── Formatting helpers ──────────────────────────────────────────────

/** Format a numeric value for display with appropriate precision. */
export function fmtValue(v: number | null | undefined, prec = 4): string {
  if (v == null) return "\u2014";
  if (v === 0) return "0";
  const abs = Math.abs(v);
  if (abs < 1e-3) return v.toExponential(2);
  if (abs >= 1e6) return v.toExponential(2);
  return v.toFixed(prec);
}

/** Format ns as human-readable duration. */
export function fmtNs(ns: number | null | undefined): string {
  if (ns == null) return "\u2014";
  if (ns < 1000) return `${ns.toFixed(0)} ns`;
  if (ns < 1e6) return `${(ns / 1e3).toFixed(1)} \u00B5s`;
  if (ns < 1e9) return `${(ns / 1e6).toFixed(1)} ms`;
  return `${(ns / 1e9).toFixed(2)} s`;
}

/** Format throughput as human-readable ops/s. */
export function fmtOpsS(ops: number | null | undefined): string {
  if (ops == null) return "\u2014";
  if (ops >= 1e6) return `${(ops / 1e6).toFixed(1)}M`;
  if (ops >= 1e3) return `${(ops / 1e3).toFixed(1)}K`;
  return `${ops.toFixed(0)}`;
}

/** Get color for a library, with fallback. */
export function libColor(lib: string): string {
  return LIBRARY_COLORS[lib] ?? "#9ca3af";
}

/** Get all accuracy metrics from ExperimentResult (not just primary). */
export function getAllAccuracyMetrics(
  r: ExperimentResult,
): { key: string; label: string; unit: string; stats: PercentileStats }[] {
  const acc = r.accuracy as Record<string, unknown>;
  const metrics: {
    key: string;
    label: string;
    unit: string;
    stats: PercentileStats;
  }[] = [];

  for (const [key, label, unit] of METRIC_PRIORITY) {
    const val = acc[key];
    if (val && typeof val === "object") {
      metrics.push({ key, label, unit, stats: val as PercentileStats });
    }
  }

  // Also check signed bias metrics
  const biasMetrics: [string, string, string][] = [
    ["signed_ra_error_arcsec", "RA Bias", "arcsec"],
    ["signed_dec_error_arcsec", "Dec Bias", "arcsec"],
    ["era_error_rad", "ERA Error", "rad"],
    ["gmst_error_rad", "GMST Error (rad)", "rad"],
    ["closure_error_rad", "Closure Error", "rad"],
    ["matrix_frobenius", "Frobenius Norm", ""],
  ];
  for (const [key, label, unit] of biasMetrics) {
    const val = acc[key];
    if (val && typeof val === "object") {
      metrics.push({ key, label, unit, stats: val as PercentileStats });
    }
  }

  return metrics;
}
