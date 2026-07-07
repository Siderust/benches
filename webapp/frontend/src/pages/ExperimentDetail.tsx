/**
 * ExperimentDetail — Drill-down view for a single experiment.
 *
 * Sections (tabs):
 *  1. Overview — Key metrics per library with ranking badges
 *  2. Accuracy — Error distribution (percentile chart), all metrics table
 *  3. Performance — Latency / throughput comparison bars
 *  4. Assumptions — Alignment checklist
 */

import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js-dist-min";
import { fetchExperiment } from "../api/client";
import type { ExperimentResult } from "../api/types";
import Header from "../components/layout/Header";
import MetricCard from "../components/cards/MetricCard";
import { CandidateBadges, candidateBaseId, candidateId, isUnavailable, supportReason } from "../components/CandidateBadges";
import {
  getPrimaryMetric,
  getAllAccuracyMetrics,
  fmtValue,
  fmtNs,
  fmtOpsS,
  libColor,
} from "../utils/analytics";
import { measuredNsPerOp, normPerfFlat, perfValid } from "../utils/perf";

const TABS = ["Overview", "Accuracy", "Performance", "Assumptions"] as const;
type Tab = (typeof TABS)[number];

// ─── Component ───────────────────────────────────────────────────────

export default function ExperimentDetail() {
  const { runId, experiment } = useParams<{
    runId: string;
    experiment: string;
  }>();
  const [tab, setTab] = useState<Tab>("Overview");
  /** A7: when true, hide best-available rows from rankings (exact-model only). */
  const [exactOnly, setExactOnly] = useState(false);

  const {
    data: results,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["experiment", runId, experiment],
    queryFn: () => fetchExperiment(runId!, experiment!),
    enabled: !!runId && !!experiment,
  });

  if (isLoading) return <p className="text-gray-500">Loading experiment...</p>;
  if (error || !results)
    return <p className="text-red-400">Failed to load experiment.</p>;

  const ref = results[0]?.reference_library ?? "erfa";
  const refDisplay = ref === "jpl_horizons" ? "JPL Horizons" : ref;
  const mode = results[0]?.alignment?.mode ?? "common_denominator";
  const desc = results[0]?.description as Record<string, string> | undefined;
  const referenceModel = referenceLabel(experiment, results[0]?.reference_model ?? refDisplay);

  return (
    <div>
      <Header
        title={desc?.title ?? experiment!.replace(/_/g, " ")}
        subtitle={`Reference: ${referenceModel} \u2014 Mode: ${mode}`}
        actions={
          <Link
            to={`/runs/${runId}`}
            className="flex items-center gap-2 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            Run Overview
          </Link>
        }
      />

      {/* Experiment description for non-experts */}
      {desc && (desc.what || desc.why) && (
        <div className="rounded-xl border border-blue-800/40 bg-blue-950/20 px-5 py-4 mb-6">
          {desc.what && (
            <p className="text-sm text-blue-200/80 mb-2">
              <span className="font-medium text-blue-200">What:</span> {desc.what}
            </p>
          )}
          {desc.why && (
            <p className="text-sm text-blue-200/70 mb-2">
              <span className="font-medium text-blue-200">Why it matters:</span> {desc.why}
            </p>
          )}
          {desc.units && (
            <p className="text-sm text-blue-200/60 mb-2">
              <span className="font-medium text-blue-200">Units:</span> {desc.units}
            </p>
          )}
          {desc.interpret && (
            <p className="text-sm text-blue-200/60">
              <span className="font-medium text-blue-200">How to interpret:</span> {desc.interpret}
            </p>
          )}
        </div>
      )}

      <div className="rounded-xl border border-gray-800 bg-gray-900/40 px-5 py-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          <div>
            <span className="block text-xs uppercase text-gray-500">Reference</span>
            <span className="text-gray-200" title={referenceTitle(experiment)}>{referenceModel}</span>
          </div>
          <div>
            <span className="block text-xs uppercase text-gray-500">Rank Policy</span>
            <span className="text-gray-200">
              {exactOnly
                ? "Exact-model parity only"
                : "Exact-model + best-available (disclosed)"}
            </span>
          </div>
          <div>
            <span className="block text-xs uppercase text-gray-500">Performance Policy</span>
            <span className="text-gray-200">Invalid timing samples are not ranked</span>
          </div>
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={exactOnly}
            onChange={(e) => setExactOnly(e.target.checked)}
            className="accent-orange-500"
          />
          <span>Show only exact-model parity rows in rankings</span>
        </label>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-gray-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === t
                ? "text-white border-b-2 border-orange-500"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && <OverviewTab results={results} exactOnly={exactOnly} />}
      {tab === "Accuracy" && <AccuracyTab results={results} />}
      {tab === "Performance" && <PerformanceTab results={results} />}
      {tab === "Assumptions" && <AssumptionsTab results={results} />}
    </div>
  );
}

// ─── Overview Tab ────────────────────────────────────────────────────

function OverviewTab({ results, exactOnly = false }: { results: ExperimentResult[]; exactOnly?: boolean }) {
  // Determine primary metric
  const pm = getPrimaryMetric(results[0]?.accuracy as Record<string, unknown>);

  /** A row is admissible for the ranking when it is `rankable_accuracy` AND
   * (if exactOnly) its comparability_class is strictly `exact-model`. The
   * comparability_class is authoritative for ranking semantics — same-family-jpl
   * (DE440 vs the DE441 reference) is rankable in the broad view but excluded
   * from the strict exact-model view (audit issue #4 / critique fix). */
  const isRankableUnderFilter = (r: ExperimentResult): boolean => {
    if (r.rankable_accuracy !== true) return false;
    if (!exactOnly) return true;
    return r.comparability_class === "exact-model";
  };

  // Find best performers
  const accuracyValues = results
    .map((r) => {
      const m = getPrimaryMetric(r.accuracy as Record<string, unknown>);
      return {
        library: displayName(r),
        p99: m.stats?.p99 ?? null,
        rankable: isRankableUnderFilter(r),
      };
    })
    .filter((v) => v.p99 != null && v.rankable);

  const bestAccuracy =
    accuracyValues.length > 0
      ? accuracyValues.reduce((a, b) =>
          Math.abs(a.p99!) < Math.abs(b.p99!) ? a : b,
        ).library
      : null;

  const perfValues = results
    .map((r) => {
      const perf = normPerfFlat(r.performance as Record<string, unknown>);
      return {
        library: displayName(r),
        ns: (perf?.per_op_ns as number) ?? null,
        valid: perfValid(perf),
      };
    })
    .filter((v) => v.ns != null && v.valid);

  const bestPerf =
    perfValues.length > 0
      ? perfValues.reduce((a, b) => (a.ns! < b.ns! ? a : b)).library
      : null;

  return (
    <div className="space-y-6">
      {results.map((r) => {
        const acc = r.accuracy as Record<string, unknown>;
        const metric = getPrimaryMetric(acc);
        const s = metric.stats;
        const nan = (acc.nan_count as number) ?? 0;
        const inf = (acc.inf_count as number) ?? 0;
        const perf = normPerfFlat(r.performance as Record<string, unknown>);
        const nsOp = measuredNsPerOp(perf);
        const opsS = (perf?.throughput_ops_s as number) ?? null;
        const timingValid = perfValid(perf);

        const name = displayName(r);
        const unavailable = isUnavailable(r);
        const reason = supportReason(r);
        const isAccBest = name === bestAccuracy;
        const isPerfBest = name === bestPerf;

        return (
          <div
            key={name}
            className={`rounded-xl border border-gray-800 bg-gray-900/40 p-5 ${unavailable ? "opacity-65" : ""}`}
          >
            <div className="flex items-center gap-3 mb-4">
              <span
                className="inline-block w-3 h-3 rounded-full"
                style={{ backgroundColor: libColor(candidateBaseId(r)) }}
              />
              <h3 className="text-sm font-semibold text-white">
                {name}
              </h3>
              <span className="text-xs text-gray-500">
                vs {referenceLabel(r.experiment, r.reference_library)}
              </span>
              <CandidateBadges row={r} />
              {r.support_status && r.support_status !== "supported" && (
                <span className="rounded-md bg-gray-800 px-2 py-0.5 text-[10px] uppercase text-gray-400" title={reason}>
                  {r.support_status}
                </span>
              )}
              {unavailable && reason && (
                <span className="text-xs text-gray-500" title={reason}>{reason}</span>
              )}
              {r.rankable_accuracy === false && (
                <span className="rounded-full px-2 py-0.5 text-[10px] font-bold bg-amber-900/40 text-amber-400" title={r.rank_exclusion_reason ?? undefined}>
                  NOT RANKED
                </span>
              )}
              {/* A7: comparability_class badge */}
              {r.comparability_class && r.comparability_class !== "exact-model" && (
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  r.comparability_class === "same-family-jpl"
                    ? "bg-amber-900/40 text-amber-300"
                    : r.comparability_class === "best-available"
                    ? "bg-sky-900/40 text-sky-300"
                    : r.comparability_class === "diagnostic-profile"
                    ? "bg-violet-900/40 text-violet-300"
                    : "bg-gray-800 text-gray-400"
                }`} title={r.comparability_class === "same-family-jpl"
                    ? "Same JPL DE family as the reference but a different kernel version (e.g. DE440 vs DE441): ranked broadly, not in the strict exact-model view"
                    : undefined}>
                  {r.comparability_class.toUpperCase().replace(/-/g, " ")}
                </span>
              )}
              {/* A7: selected_model + model_source badges (compact) */}
              {r.model_source && (
                <span className="rounded-md px-2 py-0.5 text-[10px] font-medium bg-gray-800 text-gray-300" title={r.selected_model ?? undefined}>
                  {r.model_source}
                </span>
              )}
              {/* A7: lane badge for ephemeris experiments */}
              {(r.lane ?? (r.alignment?.lane as string | undefined)) && (
                <span className="rounded-md px-2 py-0.5 text-[10px] font-medium bg-indigo-900/30 text-indigo-300">
                  {String(r.lane ?? r.alignment?.lane).replace(/_/g, " ").toUpperCase()}
                </span>
              )}
              {/* A7: skipped/failed badges with reason */}
              {r.status === "skipped" && (
                <span
                  className="rounded-full px-2 py-0.5 text-[10px] font-bold bg-yellow-900/40 text-yellow-300"
                  title={reason}
                >
                  {r.support_status === "runtime-blocked" ? "RUNTIME BLOCKED" : r.support_status === "unsupported" ? "UNSUPPORTED" : r.skip_reason && /spk|bsp/i.test(r.skip_reason) ? "SPK MISSING" : "SKIPPED"}
                </span>
              )}
              {r.status === "failed" && (
                <span
                  className="rounded-full px-2 py-0.5 text-[10px] font-bold bg-red-900/40 text-red-300"
                  title={r.failure_reason ?? undefined}
                >
                  FAILED
                </span>
              )}
              {isAccBest && (
                <span className="rounded-full px-2 py-0.5 text-[10px] font-bold bg-emerald-900/60 text-emerald-300">
                  MOST ACCURATE
                </span>
              )}
              {isPerfBest && (
                <span className="rounded-full px-2 py-0.5 text-[10px] font-bold bg-yellow-900/60 text-yellow-300">
                  FASTEST
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <MetricCard
                label={`${pm.label} p50`}
                value={s?.p50}
                unit={pm.unit}
                accent={isAccBest ? "green" : "default"}
              />
              <MetricCard
                label={`${pm.label} p99`}
                value={s?.p99}
                unit={pm.unit}
                accent={isAccBest ? "green" : "default"}
              />
              <MetricCard
                label={`${pm.label} max`}
                value={s?.max}
                unit={pm.unit}
              />
              <MetricCard
                label={nsOp != null && !timingValid ? "Latency ⚠" : "Latency"}
                value={nsOp != null ? fmtNs(nsOp) : null}
                accent={nsOp != null && !timingValid ? "red" : isPerfBest ? "yellow" : "default"}
                secondary={
                  nsOp != null && !timingValid
                    ? (perf.warnings as string[] | undefined)?.[0] ?? "Timing sample not statistically valid"
                    : undefined
                }
              />
              <MetricCard
                label="Throughput"
                value={opsS != null ? `${fmtOpsS(opsS)} ops/s` : null}
              />
              <MetricCard
                label="NaN / Inf"
                value={`${nan} / ${inf}`}
                accent={nan + inf > 0 ? "red" : "green"}
              />
            </div>
          </div>
        );
      })}

      {/* Parity note */}
      {results[0]?.alignment?.note && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
          <h3 className="text-xs font-medium uppercase text-gray-400 mb-1">
            Parity Note
          </h3>
          <p className="text-sm text-gray-300">{results[0].alignment.note}</p>
        </div>
      )}
    </div>
  );
}

// ─── Accuracy Tab ────────────────────────────────────────────────────

function AccuracyTab({ results }: { results: ExperimentResult[] }) {
  return (
    <div className="space-y-8">
      {/* Percentile comparison chart */}
      <PercentileComparisonChart results={results} />

      {/* Detailed accuracy metrics table */}
      <AccuracyMetricsTable results={results} />
    </div>
  );
}

/** Chart showing percentile distribution per library (p50, p90, p95, p99, max). */
function PercentileComparisonChart({
  results,
}: {
  results: ExperimentResult[];
}) {
  const pm = getPrimaryMetric(results[0]?.accuracy as Record<string, unknown>);
  if (!pm.key) return null;

  const percentiles = ["min", "p50", "p90", "p95", "p99", "max"] as const;
  const percentileLabels = ["Min", "p50", "p90", "p95", "p99", "Max"];

  const traces: Data[] = results.map((r) => {
    const metric = getPrimaryMetric(r.accuracy as Record<string, unknown>);
    const s = metric.stats;
    if (!s) return null;

    const values = percentiles.map((p) => (s as unknown as Record<string, number | null>)[p] ?? null);

    return {
      x: percentileLabels,
      y: values,
      name: displayName(r),
      type: "scatter" as const,
      mode: "lines+markers" as const,
      line: {
        color: libColor(candidateBaseId(r)),
        width: 2.5,
      },
      marker: {
        color: libColor(candidateBaseId(r)),
        size: 8,
      },
      hovertemplate:
        `<b>${displayName(r)}</b><br>` +
        "%{x}: %{y:.4g} " +
        pm.unit +
        "<extra></extra>",
    } as Data;
  }).filter((t): t is Data => t !== null);

  const layout: Partial<Layout> = {
    title: {
      text: `${pm.label} Distribution by Percentile`,
      font: { color: "#e5e7eb", size: 15 },
      x: 0.01,
      xanchor: "left",
    },
    xaxis: { color: "#9ca3af", tickfont: { size: 12 } },
    yaxis: {
      title: { text: `${pm.label} (${pm.unit})`, font: { size: 12 } },
      type: "log",
      color: "#9ca3af",
      gridcolor: "#1f2937",
      zerolinecolor: "#1f2937",
    },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(17,24,39,0.6)",
    font: { color: "#d1d5db", family: "Inter, system-ui, sans-serif" },
    legend: {
      bgcolor: "rgba(0,0,0,0)",
      font: { color: "#d1d5db" },
      orientation: "h",
      y: -0.2,
      x: 0.5,
      xanchor: "center",
    },
    margin: { t: 50, r: 20, b: 70, l: 70 },
    height: 380,
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-2">
      <Plot
        data={traces}
        layout={layout}
        config={{ responsive: true, displayModeBar: false }}
        className="w-full"
      />
      <p className="text-xs text-gray-500 px-3 pb-2">
        Lines show how error grows across percentiles. Flatter = more consistent. Lower = more accurate.
      </p>
    </div>
  );
}

/** Table showing all accuracy metrics for all libraries. */
function AccuracyMetricsTable({
  results,
}: {
  results: ExperimentResult[];
}) {
  // Collect all unique metrics across all results
  const allMetrics = results.flatMap((r) => getAllAccuracyMetrics(r));
  const metricKeys = [...new Set(allMetrics.map((m) => m.key))];

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-800 bg-gray-900/80 text-left text-xs uppercase text-gray-400">
            <th className="px-3 py-2">Metric</th>
            <th className="px-3 py-2">Candidate ID</th>
            <th className="px-3 py-2 text-right">Mean</th>
            <th className="px-3 py-2 text-right">RMS</th>
            <th className="px-3 py-2 text-right">p50</th>
            <th className="px-3 py-2 text-right">p90</th>
            <th className="px-3 py-2 text-right">p95</th>
            <th className="px-3 py-2 text-right">p99</th>
            <th className="px-3 py-2 text-right">Max</th>
            <th className="px-3 py-2">Unit</th>
          </tr>
        </thead>
        <tbody>
          {metricKeys.flatMap((metricKey) => {
            const entries = results
              .map((r) => {
                const metrics = getAllAccuracyMetrics(r);
                const m = metrics.find((x) => x.key === metricKey);
                return m
                   ? { library: displayName(r), baseLibrary: candidateBaseId(r), metric: m, rankable: r.rankable_accuracy === true }
                  : null;
              })
              .filter(
                (e): e is { library: string; baseLibrary: string; metric: (typeof allMetrics)[0]; rankable: boolean } =>
                  e !== null,
              );

            // Find best p99 for this metric
            const p99Values = entries
              .filter((e) => e.metric.stats.p99 != null && e.rankable)
              .map((e) => ({
                library: e.library,
                val: Math.abs(e.metric.stats.p99!),
              }));
            const bestP99Lib =
              p99Values.length > 0
                ? p99Values.reduce((a, b) => (a.val < b.val ? a : b))
                    .library
                : null;

            return entries.map((e, idx) => (
              <tr
                key={`${metricKey}-${e.library}`}
                className="border-t border-gray-800/50 hover:bg-gray-800/30"
              >
                {idx === 0 && (
                  <td
                    className="px-3 py-2 text-gray-300 font-medium"
                    rowSpan={entries.length}
                  >
                    {e.metric.label}
                  </td>
                )}
                <td className="px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: libColor(e.baseLibrary) }}
                    />
                    {e.library}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-gray-400">
                  {fmtStat(e.metric.stats.mean)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-gray-400">
                  {fmtStat(e.metric.stats.rms)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-gray-400">
                  {fmtStat(e.metric.stats.p50)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-gray-400">
                  {fmtStat(e.metric.stats.p90)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-gray-400">
                  {fmtStat(e.metric.stats.p95)}
                </td>
                <td
                  className={`px-3 py-2 text-right font-mono ${
                    e.library === bestP99Lib
                      ? "text-emerald-300 font-semibold"
                      : "text-gray-300"
                  }`}
                >
                  {fmtStat(e.metric.stats.p99)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-gray-400">
                  {fmtStat(e.metric.stats.max)}
                </td>
                <td className="px-3 py-2 text-gray-500">{e.metric.unit}</td>
              </tr>
            ));
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── Performance Tab ─────────────────────────────────────────────────

function PerformanceTab({ results }: { results: ExperimentResult[] }) {
  const bars = results
    .map((r) => {
      const perf = normPerfFlat(r.performance as Record<string, unknown>);
      const ns = perf?.per_op_ns as number | undefined;
      const ops = perf?.throughput_ops_s as number | undefined;
      if (ns == null) return null;
      return {
        library: displayName(r),
        baseLibrary: candidateBaseId(r),
        ns,
        ops: ops ?? null,
        valid: perfValid(perf),
      };
    })
    .filter((b): b is NonNullable<typeof b> => b !== null);

  // Reference performance
  const refPerf = results[0]?.reference_performance as Record<string, unknown>;
  const refNs = (refPerf?.per_op_ns as number) ?? null;
  const refOps = (refPerf?.throughput_ops_s as number) ?? null;
  const refLib = results[0]?.reference_library ?? "erfa";
  const refLabel = referenceLabel(results[0]?.experiment, refLib);

  if (bars.length === 0 && refNs == null) {
    return (
      <p className="text-sm text-gray-500 italic">
        No performance data available for this experiment.
      </p>
    );
  }

  // All bars including reference
  const allBars = refNs != null
    ? [{ library: refLabel, ns: refNs, ops: refOps }, ...bars]
    : bars;

  // Find fastest
  const rankableBars = bars.filter((b) => b.valid);
  const fastest = rankableBars.length > 0
    ? rankableBars.reduce((a, b) => (a.ns < b.ns ? a : b)).library
    : null;

  // Latency bar chart
  const latencyTrace: Data = {
    x: allBars.map((b) => b.library),
    y: allBars.map((b) => b.ns),
    type: "bar" as const,
    marker: {
      color: allBars.map((b) => libColor("baseLibrary" in b ? b.baseLibrary : b.library)),
      opacity: 0.85,
    },
    text: allBars.map((b) => fmtNs(b.ns)),
    textposition: "outside" as const,
    textfont: { size: 11, color: "#9ca3af" },
    hovertemplate: "<b>%{x}</b><br>%{y:,.0f} ns/op<extra></extra>",
  };

  const latencyLayout: Partial<Layout> = {
    title: {
      text: "Execution Time (ns/op)",
      font: { color: "#e5e7eb", size: 15 },
      x: 0.01,
      xanchor: "left",
    },
    xaxis: { color: "#9ca3af" },
    yaxis: {
      title: { text: "ns / op", font: { size: 12 } },
      type: "log",
      color: "#9ca3af",
      gridcolor: "#1f2937",
      zerolinecolor: "#1f2937",
    },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(17,24,39,0.6)",
    font: { color: "#d1d5db", family: "Inter, system-ui, sans-serif" },
    margin: { t: 50, r: 20, b: 50, l: 70 },
    height: 350,
  };

  // Throughput bar chart
  const throughputBars = allBars.filter((b) => b.ops != null);
  let throughputTrace: Data | null = null;
  if (throughputBars.length > 0) {
    throughputTrace = {
      x: throughputBars.map((b) => b.library),
      y: throughputBars.map((b) => b.ops!),
      type: "bar" as const,
      marker: {
        color: throughputBars.map((b) => libColor("baseLibrary" in b ? b.baseLibrary : b.library)),
        opacity: 0.85,
      },
      text: throughputBars.map((b) => `${fmtOpsS(b.ops)} ops/s`),
      textposition: "outside" as const,
      textfont: { size: 11, color: "#9ca3af" },
      hovertemplate: "<b>%{x}</b><br>%{y:,.0f} ops/s<extra></extra>",
    };
  }

  const throughputLayout: Partial<Layout> = {
    title: {
      text: "Throughput (ops/s)",
      font: { color: "#e5e7eb", size: 15 },
      x: 0.01,
      xanchor: "left",
    },
    xaxis: { color: "#9ca3af" },
    yaxis: {
      title: { text: "ops / s", font: { size: 12 } },
      type: "log",
      color: "#9ca3af",
      gridcolor: "#1f2937",
      zerolinecolor: "#1f2937",
    },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(17,24,39,0.6)",
    font: { color: "#d1d5db", family: "Inter, system-ui, sans-serif" },
    margin: { t: 50, r: 20, b: 50, l: 70 },
    height: 350,
  };

  // Speedup table
  const speedups = refNs != null
    ? bars.filter((b) => b.valid).map((b) => ({
        library: b.library,
        baseLibrary: b.baseLibrary,
        speedup: refNs / b.ns,
        isFastest: b.library === fastest,
      }))
    : [];

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-2">
        <Plot
          data={[latencyTrace]}
          layout={latencyLayout}
          config={{ responsive: true, displayModeBar: false }}
          className="w-full"
        />
      </div>

      {throughputTrace && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-2">
          <Plot
            data={[throughputTrace]}
            layout={throughputLayout}
            config={{ responsive: true, displayModeBar: false }}
            className="w-full"
          />
        </div>
      )}

      {/* Speedup relative to reference */}
      {speedups.length > 0 && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-4">
          <h3 className="text-xs font-medium uppercase text-gray-400 mb-3">
            Speedup vs Reference ({refLabel})
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {speedups.map((s) => (
              <div
                key={s.library}
                className={`rounded-lg border px-4 py-3 ${
                  s.isFastest
                    ? "border-yellow-600/40 bg-yellow-950/20"
                    : "border-gray-800"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: libColor(s.baseLibrary) }}
                  />
                  <span className="text-sm font-medium text-gray-200">
                    {s.library}
                  </span>
                  {s.isFastest && (
                    <span className="text-[10px] font-bold text-yellow-300 bg-yellow-900/50 rounded-full px-1.5 py-0.5">
                      FASTEST
                    </span>
                  )}
                </div>
                <p className="mt-1 text-2xl font-bold text-white">
                  {s.speedup >= 1
                    ? `${s.speedup.toFixed(1)}x`
                    : `${(1 / s.speedup).toFixed(1)}x slower`}
                </p>
                <p className="text-xs text-gray-500">
                  {s.speedup >= 1 ? "faster" : "slower"} than {refLabel}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Detailed performance statistics table */}
      <PerfStatsTable results={results} refLib={refLib} refLabel={refLabel} />

      {/* Performance warnings */}
      <PerfWarnings results={results} />
    </div>
  );
}

/** Detailed performance statistics table with multi-sample data. */
function PerfStatsTable({ results, refLib, refLabel }: { results: ExperimentResult[]; refLib: string; refLabel: string }) {
  const allPerf = results.map((r) => {
    const perf = normPerfFlat(r.performance as Record<string, unknown>);
    return { library: displayName(r), baseLibrary: candidateBaseId(r), perf };
  }).filter((p) => p.perf?.per_op_ns != null);

  // Add reference
  const refPerfData = results[0]?.reference_performance as Record<string, unknown>;
  if (refPerfData?.per_op_ns != null) {
    allPerf.unshift({ library: refLabel, baseLibrary: refLib, perf: refPerfData });
  }

  if (allPerf.length === 0) return null;

  // Check if multi-sample data is available
  const hasMultiSample = allPerf.some((p) => p.perf?.rounds != null && (p.perf.rounds as number) > 1);

  return (
    <div className="rounded-xl border border-gray-800 overflow-x-auto">
      <div className="border-b border-gray-800 px-4 py-2.5">
        <h3 className="text-xs font-medium uppercase text-gray-400">
          Performance Statistics {hasMultiSample ? "(Multi-Sample)" : "(Single Pass)"}
        </h3>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-800 bg-gray-900/80 text-left text-xs uppercase text-gray-400">
            <th className="px-3 py-2">Candidate ID</th>
            <th className="px-3 py-2 text-right">Median (ns/op)</th>
            {hasMultiSample && (
              <>
                <th className="px-3 py-2 text-right">Std Dev</th>
                <th className="px-3 py-2 text-right">Min</th>
                <th className="px-3 py-2 text-right">Max</th>
                <th className="px-3 py-2 text-right">CV%</th>
                <th className="px-3 py-2 text-right">95% CI</th>
                <th className="px-3 py-2 text-right">Rounds</th>
              </>
            )}
            <th className="px-3 py-2 text-right">Throughput</th>
          </tr>
        </thead>
        <tbody>
          {allPerf.map((p) => {
            const ns = p.perf.per_op_ns as number;
            const stdDev = p.perf.per_op_ns_std_dev as number | undefined;
            const min = p.perf.per_op_ns_min as number | undefined;
            const max = p.perf.per_op_ns_max as number | undefined;
            const cv = p.perf.per_op_ns_cv_pct as number | undefined;
            const ci95 = p.perf.per_op_ns_ci95 as [number, number] | undefined;
            const rounds = p.perf.rounds as number | undefined;
            const throughput = p.perf.throughput_ops_s as number | undefined;

            return (
              <tr key={p.library} className="border-t border-gray-800/50 hover:bg-gray-800/30">
                <td className="px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: libColor(p.baseLibrary) }} />
                    <span className="text-gray-200 font-medium">{p.library}</span>
                    {p.library === refLabel && (
                      <span className="text-[10px] text-gray-500">(ref)</span>
                    )}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono text-gray-300">
                  {fmtNs(ns)}
                </td>
                {hasMultiSample && (
                  <>
                    <td className="px-3 py-2 text-right font-mono text-gray-400">
                      {stdDev != null ? `\u00B1${fmtNs(stdDev)}` : "\u2014"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-400">
                      {min != null ? fmtNs(min) : "\u2014"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-400">
                      {max != null ? fmtNs(max) : "\u2014"}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${
                      cv != null && cv > 20 ? "text-yellow-400" : "text-gray-400"
                    }`}>
                      {cv != null ? `${cv.toFixed(1)}%` : "\u2014"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-400">
                      {ci95 ? `[${fmtNs(ci95[0])}, ${fmtNs(ci95[1])}]` : "\u2014"}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-gray-400">
                      {rounds ?? "\u2014"}
                    </td>
                  </>
                )}
                <td className="px-3 py-2 text-right font-mono text-gray-400">
                  {throughput != null ? `${fmtOpsS(throughput)} ops/s` : "\u2014"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Show performance measurement warnings. */
function PerfWarnings({ results }: { results: ExperimentResult[] }) {
  const allWarnings: { library: string; warnings: string[] }[] = [];
  for (const r of results) {
    const perf = r.performance as Record<string, unknown>;
    const scalar = perf?.scalar_warm as Record<string, unknown> | undefined;
    const w = (scalar?.warnings ?? perf?.warnings) as string[] | undefined;
    if (w && w.length > 0) {
      allWarnings.push({ library: displayName(r), warnings: w });
    }
  }

  if (allWarnings.length === 0) return null;

  return (
    <div className="rounded-xl border border-yellow-700/40 bg-yellow-950/30 px-4 py-3">
      <p className="text-xs font-medium text-yellow-300 mb-2">Performance Measurement Warnings</p>
      {allWarnings.map(({ library, warnings }) => (
        <div key={library} className="mb-1.5">
          <span className="text-xs font-medium text-yellow-200">{library}:</span>
          {warnings.map((w, i) => (
            <p key={i} className="text-xs text-yellow-200/70 ml-2">{w}</p>
          ))}
        </div>
      ))}
    </div>
  );
}

// ─── Assumptions Tab ─────────────────────────────────────────────────

function AssumptionsTab({ results }: { results: ExperimentResult[] }) {
  const alignment = results[0]?.alignment;
  if (!alignment) {
    return (
      <p className="text-sm text-gray-500 italic">
        No alignment checklist available.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {Object.entries(alignment).map(([key, value]) => {
        if (key === "models" && typeof value === "object" && value !== null) {
          return (
            <div
              key={key}
              className="rounded-xl border border-gray-800 bg-gray-900/40 p-4"
            >
              <h3 className="text-xs font-medium uppercase text-gray-400 mb-2">
                Models per Candidate ID
              </h3>
              <div className="space-y-2">
                {Object.entries(value as Record<string, string>).map(
                  ([lib, model]) => (
                    <div key={lib} className="text-sm">
                      <span className="font-medium text-gray-300">{lib}:</span>{" "}
                      <span className="text-gray-400">{model}</span>
                    </div>
                  ),
                )}
              </div>
            </div>
          );
        }

        if (typeof value === "object" && value !== null) {
          return (
            <div
              key={key}
              className="rounded-xl border border-gray-800 bg-gray-900/40 p-4"
            >
              <h3 className="text-xs font-medium uppercase text-gray-400 mb-2">
                {key.replace(/_/g, " ")}
              </h3>
              <div className="space-y-1">
                {Object.entries(value as Record<string, string>).map(
                  ([k, v]) => (
                    <div key={k} className="text-sm">
                      <span className="text-gray-400">{k}:</span>{" "}
                      <span className="text-gray-300">{String(v)}</span>
                    </div>
                  ),
                )}
              </div>
            </div>
          );
        }

        return (
          <div
            key={key}
            className="rounded-xl border border-gray-800 bg-gray-900/40 p-4"
          >
            <h3 className="text-xs font-medium uppercase text-gray-400 mb-1">
              {key.replace(/_/g, " ")}
            </h3>
            <p className="text-sm text-gray-300">{String(value)}</p>
          </div>
        );
      })}
    </div>
  );
}

// ─── Format helper ───────────────────────────────────────────────────

function displayName(r: ExperimentResult): string {
  return candidateId(r);
}

function referenceLabel(experiment: string | undefined, fallback: string): string {
  return experiment === "kepler_solver" ? "pipeline_python" : fallback;
}

function referenceTitle(experiment: string | undefined): string | undefined {
  return experiment === "kepler_solver"
    ? "Newton-Raphson to machine epsilon (no SOFA/ERFA public Kepler API)"
    : undefined;
}

function fmtStat(v: number | null | undefined): string {
  return fmtValue(v);
}
