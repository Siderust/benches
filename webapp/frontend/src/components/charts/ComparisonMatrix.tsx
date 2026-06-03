/**
 * ComparisonMatrix — Pairwise library comparison rendered as
 * styled HTML tables with color gradients.
 *
 * Two views:
 * 1. Pairwise wins matrix (libraries x libraries)
 * 2. Experiment heatmap (experiments x libraries, colored by metric)
 */

import { useState } from "react";
import type { RunAnalytics, PairwiseCell } from "../../utils/analytics";
import { computePairwiseMatrix, libColor, fmtValue, fmtNs } from "../../utils/analytics";

interface Props {
  analytics: RunAnalytics;
}

type View = "pairwise" | "accuracy" | "performance";

export default function ComparisonMatrix({ analytics }: Props) {
  const [view, setView] = useState<View>("pairwise");

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden">
      {/* View selector */}
      <div className="flex items-center gap-1 border-b border-gray-800 px-4 py-2">
        <span className="text-xs font-medium uppercase text-gray-400 mr-3">
          Matrix View
        </span>
        {(
          [
            ["pairwise", "Pairwise Wins"],
            ["accuracy", "Accuracy Heatmap"],
            ["performance", "Performance Heatmap"],
          ] as [View, string][]
        ).map(([v, label]) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              view === v
                ? "bg-gray-700 text-white"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="p-4">
        {view === "pairwise" && <PairwiseWinsTable analytics={analytics} />}
        {view === "accuracy" && (
          <ExperimentHeatmap
            analytics={analytics}
            mode="accuracy"
          />
        )}
        {view === "performance" && (
          <ExperimentHeatmap
            analytics={analytics}
            mode="performance"
          />
        )}
      </div>
    </div>
  );
}

// ─── Pairwise wins table ─────────────────────────────────────────────

function PairwiseWinsTable({ analytics }: { analytics: RunAnalytics }) {
  const cells = computePairwiseMatrix(analytics);
  const libs = analytics.candidateLibraries;
  const totalExp = analytics.experiments.length;

  const getCell = (row: string, col: string): PairwiseCell | undefined =>
    cells.find((c) => c.libRow === row && c.libCol === col);

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-400">
        Each cell shows how many experiments the <b>row</b> candidate ID beats the{" "}
        <b>column</b> candidate ID.{" "}
        <span className="text-emerald-400">Green</span> = dominant,{" "}
        <span className="text-red-400">Red</span> = subordinate.
      </p>

      {/* Accuracy wins */}
      <div>
        <h4 className="text-xs font-medium uppercase text-gray-400 mb-2">
          Accuracy Wins (of {totalExp} experiments)
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-3 py-2 text-left text-xs text-gray-500" />
                {libs.map((lib) => (
                  <th
                    key={lib}
                    className="px-3 py-2 text-center text-xs font-medium"
                    style={{ color: libColor(lib) }}
                  >
                    {lib}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {libs.map((rowLib) => (
                <tr key={rowLib} className="border-t border-gray-800/50">
                  <td
                    className="px-3 py-2 text-xs font-medium"
                    style={{ color: libColor(rowLib) }}
                  >
                    {rowLib}
                  </td>
                  {libs.map((colLib) => {
                    if (rowLib === colLib) {
                      return (
                        <td
                          key={colLib}
                          className="px-3 py-2 text-center text-gray-600"
                        >
                          —
                        </td>
                      );
                    }
                    const cell = getCell(rowLib, colLib);
                    const wins = cell?.accuracyWins ?? 0;
                    const total = cell?.totalExperiments ?? totalExp;
                    const ratio = total > 0 ? wins / total : 0;
                    const bg = winsColor(ratio);

                    return (
                      <td
                        key={colLib}
                        className="px-3 py-2 text-center font-mono text-xs font-semibold"
                        style={{ backgroundColor: bg, color: "#fff" }}
                      >
                        {wins}/{total}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Performance wins */}
      <div>
        <h4 className="text-xs font-medium uppercase text-gray-400 mb-2">
          Performance Wins (of {totalExp} experiments)
        </h4>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-3 py-2 text-left text-xs text-gray-500" />
                {libs.map((lib) => (
                  <th
                    key={lib}
                    className="px-3 py-2 text-center text-xs font-medium"
                    style={{ color: libColor(lib) }}
                  >
                    {lib}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {libs.map((rowLib) => (
                <tr key={rowLib} className="border-t border-gray-800/50">
                  <td
                    className="px-3 py-2 text-xs font-medium"
                    style={{ color: libColor(rowLib) }}
                  >
                    {rowLib}
                  </td>
                  {libs.map((colLib) => {
                    if (rowLib === colLib) {
                      return (
                        <td
                          key={colLib}
                          className="px-3 py-2 text-center text-gray-600"
                        >
                          —
                        </td>
                      );
                    }
                    const cell = getCell(rowLib, colLib);
                    const wins = cell?.performanceWins ?? 0;
                    const total = cell?.totalExperiments ?? totalExp;
                    const ratio = total > 0 ? wins / total : 0;
                    const bg = winsColor(ratio);

                    return (
                      <td
                        key={colLib}
                        className="px-3 py-2 text-center font-mono text-xs font-semibold"
                        style={{ backgroundColor: bg, color: "#fff" }}
                      >
                        {wins}/{total}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── Experiment heatmap table ────────────────────────────────────────

function ExperimentHeatmap({
  analytics,
  mode,
}: {
  analytics: RunAnalytics;
  mode: "accuracy" | "performance";
}) {
  const libs = analytics.candidateLibraries;
  const experiments = analytics.experiments;

  // For each experiment, find the range of values for normalization
  const rows = experiments.map((exp) => {
    const values: { library: string; value: number | null; display: string; isBest: boolean }[] = [];
    let best: string | null = null;

    if (mode === "accuracy") {
      best = exp.mostAccurate;
      for (const lib of libs) {
        const entry = exp.accuracy.find((a) => a.library === lib);
        const val = entry?.p99 ?? null;
        values.push({
          library: lib,
          value: val,
          display: val != null ? fmtValue(val) : "\u2014",
          isBest: lib === best,
        });
      }
    } else {
      best = exp.fastest;
      for (const lib of libs) {
        const entry = exp.performance.find((p) => p.library === lib);
        const val = entry?.perOpNs ?? null;
        values.push({
          library: lib,
          value: val,
          display: val != null ? fmtNs(val) : "\u2014",
          isBest: lib === best,
        });
      }
    }

    // Normalize for coloring (0 = best, 1 = worst)
    const numericValues = values
      .map((v) => v.value)
      .filter((v): v is number => v != null && v > 0);
    const minVal = Math.min(...numericValues);
    const maxVal = Math.max(...numericValues);
    const range = maxVal - minVal;

    const colored = values.map((v) => {
      let intensity = 0.5;
      if (v.value != null && v.value > 0 && range > 0) {
        intensity = (v.value - minVal) / range;
      } else if (v.value != null && numericValues.length === 1) {
        intensity = 0; // only one value -> treat as best
      }
      return { ...v, intensity };
    });

    return { experiment: exp, values: colored };
  });

  return (
    <div>
      <p className="text-xs text-gray-400 mb-3">
        {mode === "accuracy"
          ? "Cell color intensity: green (best) to red (worst) per row. Values show p99 error."
          : "Cell color intensity: green (fastest) to red (slowest) per row. Values show latency."}
        {" "}<span className="font-semibold text-white">Bold</span> = best per experiment.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-400">
                Experiment
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase text-gray-400">
                Unit
              </th>
              {libs.map((lib) => (
                <th
                  key={lib}
                  className="px-3 py-2 text-center text-xs font-medium"
                  style={{ color: libColor(lib) }}
                >
                  {lib}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.experiment.name}
                className="border-t border-gray-800/50"
              >
                <td className="px-3 py-2 text-xs text-gray-200">
                  {row.experiment.displayName}
                </td>
                <td className="px-3 py-2 text-xs text-gray-500">
                  {mode === "accuracy" ? row.experiment.unit : "ns/op"}
                </td>
                {row.values.map((v) => (
                  <td
                    key={v.library}
                    className="px-3 py-2 text-center font-mono text-xs"
                    style={{
                      backgroundColor:
                        v.value != null
                          ? heatColor(v.intensity)
                          : "transparent",
                      color: v.value != null ? "#fff" : "#4b5563",
                      fontWeight: v.isBest ? 700 : 400,
                    }}
                  >
                    {v.display}
                    {v.isBest && (
                      <span className="ml-1 text-yellow-300">{"\u2605"}</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Color helpers ───────────────────────────────────────────────────

/** Map 0..1 ratio of wins to a background color (green → red). */
function winsColor(ratio: number): string {
  // ratio = 1 → all wins (green), ratio = 0 → no wins (red)
  const r = Math.round(220 - ratio * 180);
  const g = Math.round(40 + ratio * 140);
  const b = Math.round(40 + ratio * 20);
  return `rgba(${r}, ${g}, ${b}, 0.7)`;
}

/** Map 0..1 intensity to heatmap color (green=0 → red=1). */
function heatColor(intensity: number): string {
  // 0 = best (green), 1 = worst (red)
  const r = Math.round(30 + intensity * 190);
  const g = Math.round(160 - intensity * 120);
  const b = Math.round(60 - intensity * 20);
  return `rgba(${r}, ${g}, ${b}, 0.6)`;
}
