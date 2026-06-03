/**
 * AccuracyChart — Grouped bar chart comparing p99 error
 * across experiments and libraries. Log-scale Y-axis.
 * Error whiskers from p50 (lower) to max (upper).
 */

import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js-dist-min";
import type { ExperimentAnalytics } from "../../utils/analytics";
import { libColor } from "../../utils/analytics";

interface Props {
  experiments: ExperimentAnalytics[];
  height?: number;
}

const DARK = {
  paper: "rgba(0,0,0,0)",
  plot: "rgba(17,24,39,0.6)",
  grid: "#1f2937",
  text: "#d1d5db",
  muted: "#9ca3af",
  accent: "#e5e7eb",
};

export default function AccuracyChart({ experiments, height = 380 }: Props) {
  // Collect unique candidate libraries
  const libSet = new Set<string>();
  for (const exp of experiments) {
    for (const a of exp.accuracy) {
      libSet.add(a.library);
    }
  }
  const libraries = Array.from(libSet).sort();

  if (libraries.length === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center rounded-xl border border-gray-800 text-sm text-gray-500">
        No accuracy data available.
      </div>
    );
  }

  // Group experiments by unit for proper Y-axis labeling
  // If all same unit, one chart; otherwise note mixed units
  const units = new Set(experiments.map((e) => e.unit).filter(Boolean));
  const unitLabel =
    units.size === 1 ? `p99 Error (${[...units][0]})` : "p99 Error (mixed units)";

  const expNames = experiments.map((e) => e.displayName);

  const traces: Data[] = libraries.map((lib) => {
    const yValues = experiments.map((exp) => {
      const entry = exp.accuracy.find((a) => a.library === lib);
      return entry?.p99 ?? null;
    });

    // Error bars: from p50 to max
    const errorBelow = experiments.map((exp) => {
      const entry = exp.accuracy.find((a) => a.library === lib);
      if (entry?.p99 != null && entry?.p50 != null) {
        return Math.max(0, entry.p99 - entry.p50);
      }
      return 0;
    });

    const errorAbove = experiments.map((exp) => {
      const entry = exp.accuracy.find((a) => a.library === lib);
      if (entry?.p99 != null && entry?.max != null) {
        return Math.max(0, entry.max - entry.p99);
      }
      return 0;
    });

    // Mark most accurate per experiment
    const textValues = experiments.map((exp) => {
      if (exp.mostAccurate === lib) return "\u2605";
      return "";
    });

    return {
      x: expNames,
      y: yValues,
      name: lib,
      type: "bar" as const,
      marker: {
        color: libColor(lib),
        opacity: 0.85,
        line: { color: libColor(lib), width: 1 },
      },
      error_y: {
        type: "data" as const,
        symmetric: false,
        array: errorAbove,
        arrayminus: errorBelow,
        visible: true,
        color: "#6b7280",
        thickness: 1.5,
        width: 3,
      },
      text: textValues,
      textposition: "outside" as const,
      textfont: { size: 14, color: "#34d399" },
      hovertemplate:
        `<b>${lib}</b><br>` +
        "%{x}<br>" +
        "p99: %{y:.4g}<br>" +
        "<extra></extra>",
    } as Data;
  });

  const layout: Partial<Layout> = {
    barmode: "group",
    title: {
      text: "Accuracy: p99 Error by Experiment",
      font: { color: DARK.accent, size: 15, family: "Inter, system-ui, sans-serif" },
      x: 0.01,
      xanchor: "left",
    },
    xaxis: {
      color: DARK.muted,
      tickangle: -30,
      tickfont: { size: 11 },
    },
    yaxis: {
      title: { text: unitLabel, font: { size: 12 } },
      type: "log",
      color: DARK.muted,
      gridcolor: DARK.grid,
      zerolinecolor: DARK.grid,
      tickfont: { size: 11 },
    },
    paper_bgcolor: DARK.paper,
    plot_bgcolor: DARK.plot,
    font: { color: DARK.text, family: "Inter, system-ui, sans-serif" },
    legend: {
      bgcolor: "rgba(0,0,0,0)",
      font: { color: DARK.text, size: 12 },
      orientation: "h",
      y: -0.25,
      x: 0.5,
      xanchor: "center",
    },
    margin: { t: 50, r: 20, b: 90, l: 70 },
    height,
    bargap: 0.15,
    bargroupgap: 0.05,
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
        <span className="text-emerald-400">{"\u2605"}</span> = most accurate candidate per experiment.
        Whiskers: p50 (lower) to max (upper). Lower is better.
      </p>
    </div>
  );
}
