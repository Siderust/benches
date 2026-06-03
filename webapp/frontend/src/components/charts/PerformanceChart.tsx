/**
 * PerformanceChart — Grouped bar chart comparing execution time
 * across experiments and libraries. Log-scale Y-axis.
 * Includes reference library performance where available.
 */

import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js-dist-min";
import type { ExperimentAnalytics } from "../../utils/analytics";
import { libColor } from "../../utils/analytics";

interface Props {
  experiments: ExperimentAnalytics[];
  /** If true, include reference library bars. */
  showReference?: boolean;
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

export default function PerformanceChart({
  experiments,
  showReference = true,
  height = 380,
}: Props) {
  // Collect unique libraries across all experiments
  const libSet = new Set<string>();
  for (const exp of experiments) {
    for (const p of exp.performance) {
      if (showReference || !p.isReference) {
        libSet.add(p.library);
      }
    }
  }
  const libraries = Array.from(libSet).sort();

  if (libraries.length === 0) {
    return (
      <div className="flex h-[280px] items-center justify-center rounded-xl border border-gray-800 text-sm text-gray-500">
        No performance data available.
      </div>
    );
  }

  const expNames = experiments.map((e) => e.displayName);

  const traces: Data[] = libraries.map((lib) => {
    const yValues = experiments.map((exp) => {
      const entry = exp.performance.find((p) => p.library === lib);
      return entry?.perOpNs ?? null;
    });

    // Mark fastest per experiment
    const textValues = experiments.map((exp) => {
      if (exp.fastest === lib) return "\u2605"; // star
      return "";
    });

    return {
      x: expNames,
      y: yValues,
      name: lib,
      type: "bar" as const,
      marker: {
        color: libColor(lib),
        opacity: libraries.length > 1 ? 0.85 : 1,
        line: { color: libColor(lib), width: 1 },
      },
      text: textValues,
      textposition: "outside" as const,
      textfont: { size: 14, color: "#facc15" },
      hovertemplate:
        `<b>${lib}</b><br>` +
        "%{x}<br>" +
        "Latency: %{y:,.0f} ns/op<br>" +
        "<extra></extra>",
    } as Data;
  });

  const layout: Partial<Layout> = {
    barmode: "group",
    title: {
      text: "Execution Time by Experiment",
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
      title: { text: "ns / op (log scale)", font: { size: 12 } },
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
        <span className="text-yellow-400">{"\u2605"}</span> = fastest candidate per experiment. Lower is better.
      </p>
    </div>
  );
}
