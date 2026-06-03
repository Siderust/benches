import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { fetchRuns, fetchCompare } from "../api/client";
import type { MetricDelta } from "../api/types";
import Header from "../components/layout/Header";

function fmt(v: number | null): string {
  if (v == null) return "\u2014";
  if (Math.abs(v) < 0.001 && v !== 0) return v.toExponential(3);
  return v.toFixed(4);
}

function pctFmt(v: number | null): string {
  if (v == null) return "";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

export default function CompareRuns() {
  const [searchParams] = useSearchParams();
  const [runA, setRunA] = useState(searchParams.get("run_a") ?? "");
  const [runB, setRunB] = useState(searchParams.get("run_b") ?? "");
  const [doCompare, setDoCompare] = useState(false);

  const { data: runs } = useQuery({
    queryKey: ["runs"],
    queryFn: fetchRuns,
  });

  const { data: comparison, isLoading: comparing } = useQuery({
    queryKey: ["compare", runA, runB],
    queryFn: () => fetchCompare(runA, runB),
    enabled: doCompare && !!runA && !!runB && runA !== runB,
  });

  const runIds = runs?.map((r) => r.id) ?? [];

  // Group deltas by experiment
  const grouped: Record<string, MetricDelta[]> = {};
  if (comparison) {
    for (const d of comparison.deltas) {
      (grouped[d.experiment] ??= []).push(d);
    }
  }

  return (
    <div>
      <Header
        title="Compare Runs"
        subtitle="Pick two runs and view metric deltas with regression highlights."
      />

      {/* Selectors */}
      <div className="flex flex-wrap items-end gap-4 mb-8">
        <div>
          <label className="block text-xs font-medium uppercase text-gray-400 mb-1">
            Run A (baseline)
          </label>
          <select
            value={runA}
            onChange={(e) => {
              setRunA(e.target.value);
              setDoCompare(false);
            }}
            className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white min-w-[180px]"
          >
            <option value="">Select run...</option>
            {runIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium uppercase text-gray-400 mb-1">
            Run B (new)
          </label>
          <select
            value={runB}
            onChange={(e) => {
              setRunB(e.target.value);
              setDoCompare(false);
            }}
            className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white min-w-[180px]"
          >
            <option value="">Select run...</option>
            {runIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={() => setDoCompare(true)}
          disabled={!runA || !runB || runA === runB}
          className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Compare
        </button>
      </div>

      {comparing && <p className="text-gray-500 text-sm">Computing deltas...</p>}

      {runA && runB && runA === runB && (
        <p className="text-yellow-400 text-sm">
          Select two different runs to compare.
        </p>
      )}

      {/* Delta tables */}
      {comparison && Object.keys(grouped).length > 0 && (
        <div className="space-y-8">
          {Object.entries(grouped).map(([exp, deltas]) => (
            <div key={exp}>
              <h3 className="text-sm font-semibold text-gray-200 mb-2">
                {exp}
              </h3>
              <div className="overflow-x-auto rounded-xl border border-gray-800">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 bg-gray-900/80 text-left text-xs uppercase text-gray-400">
                      <th className="px-4 py-3">Candidate ID</th>
                      <th className="px-4 py-3">Metric</th>
                      <th className="px-4 py-3">Run A</th>
                      <th className="px-4 py-3">Run B</th>
                      <th className="px-4 py-3">Delta</th>
                      <th className="px-4 py-3">%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deltas.map((d, i) => (
                      <tr
                        key={`${d.library}-${d.metric}`}
                        className={`border-b border-gray-800/50 ${
                          i % 2 === 0 ? "bg-gray-900/30" : ""
                        }`}
                      >
                        <td className="px-4 py-2.5">{d.library}</td>
                        <td className="px-4 py-2.5 text-gray-400">
                          {d.metric}
                        </td>
                        <td className="px-4 py-2.5 font-mono">
                          {fmt(d.value_a)}
                        </td>
                        <td className="px-4 py-2.5 font-mono">
                          {fmt(d.value_b)}
                        </td>
                        <td
                          className={`px-4 py-2.5 font-mono font-medium ${
                            d.regression
                              ? "text-red-400"
                              : d.delta != null && d.delta < 0
                              ? "text-green-400"
                              : "text-gray-400"
                          }`}
                        >
                          {d.delta != null ? fmt(d.delta) : "\u2014"}
                        </td>
                        <td
                          className={`px-4 py-2.5 font-mono text-xs ${
                            d.regression
                              ? "text-red-400"
                              : d.delta_pct != null && d.delta_pct < 0
                              ? "text-green-400"
                              : "text-gray-500"
                          }`}
                        >
                          {pctFmt(d.delta_pct)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      {comparison && comparison.deltas.length === 0 && (
        <p className="text-gray-500 text-sm">
          No comparable metrics found between these runs.
        </p>
      )}
    </div>
  );
}
