/**
 * SummaryTable — Enhanced experiment × library table with:
 * - Primary error metric (p99, max)
 * - Performance (ns/op, throughput)
 * - Ranking badges for fastest & most accurate per experiment
 * - Overall winner highlights
 */

import { Link } from "react-router-dom";
import type { RunAnalytics } from "../../utils/analytics";
import { fmtValue, fmtNs, fmtOpsS, libColor } from "../../utils/analytics";

interface Props {
  runId: string;
  analytics: RunAnalytics;
}

export default function SummaryTable({ runId, analytics }: Props) {
  const { experiments, overallFastest, overallMostAccurate } = analytics;

  return (
    <div className="space-y-3">
      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-400">
        <span>
          <span className="inline-block w-2 h-2 rounded-full bg-yellow-400 mr-1" />
          Fastest
        </span>
        <span>
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 mr-1" />
          Most accurate
        </span>
        {overallFastest && (
          <span className="text-gray-500">
            Overall fastest: <b className="text-yellow-300">{overallFastest}</b>
          </span>
        )}
        {overallMostAccurate && (
          <span className="text-gray-500">
            Overall most accurate: <b className="text-emerald-300">{overallMostAccurate}</b>
          </span>
        )}
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-900/80 text-left text-xs uppercase text-gray-400">
              <th className="px-4 py-3 sticky left-0 bg-gray-900/80 z-10">
                Experiment
              </th>
              <th className="px-4 py-3">Candidate ID</th>
              <th className="px-4 py-3 text-right">p99 Error</th>
              <th className="px-4 py-3 text-right">Max Error</th>
              <th className="px-4 py-3">Unit</th>
              <th className="px-4 py-3 text-right">Latency</th>
              <th className="px-4 py-3 text-right">Throughput</th>
              <th className="px-4 py-3 text-center">Rank</th>
            </tr>
          </thead>
          <tbody>
            {experiments.flatMap((exp, expIdx) =>
              exp.accuracy.map((acc, libIdx) => {
                const perf = exp.performance.find(
                  (p) => p.library === acc.library,
                );
                const isFastest = exp.fastest === acc.library;
                const isMostAccurate = exp.mostAccurate === acc.library;
                const rowKey = `${exp.name}-${acc.library}`;
                const isFirstInGroup = libIdx === 0;
                const groupSize = exp.accuracy.length;

                return (
                  <tr
                    key={rowKey}
                    className={`border-b border-gray-800/50 hover:bg-gray-800/40 ${
                      expIdx % 2 === 0 ? "bg-gray-900/30" : ""
                    }`}
                  >
                    {/* Experiment name — merged across libraries */}
                    {isFirstInGroup && (
                      <td
                        className="px-4 py-2.5 sticky left-0 bg-inherit z-10"
                        rowSpan={groupSize}
                      >
                        <Link
                          to={`/runs/${runId}/experiments/${exp.name}`}
                          className="text-blue-400 hover:underline text-xs font-medium"
                        >
                          {exp.displayName}
                        </Link>
                      </td>
                    )}

                    {/* Candidate ID */}
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: libColor(acc.library) }}
                        />
                        <span className="text-gray-200">{acc.library}</span>
                      </div>
                    </td>

                    {/* p99 Error */}
                    <td
                      className={`px-4 py-2.5 text-right font-mono text-xs ${
                        isMostAccurate
                          ? "text-emerald-300 font-semibold"
                          : "text-gray-300"
                      }`}
                    >
                      {fmtValue(acc.p99)}
                    </td>

                    {/* Max Error */}
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-gray-400">
                      {fmtValue(acc.max)}
                    </td>

                    {/* Unit */}
                    <td className="px-4 py-2.5 text-gray-500 text-xs">
                      {exp.unit}
                    </td>

                    {/* Latency */}
                    <td
                      className={`px-4 py-2.5 text-right font-mono text-xs ${
                        isFastest
                          ? "text-yellow-300 font-semibold"
                          : "text-gray-300"
                      }`}
                    >
                      {fmtNs(perf?.perOpNs)}
                    </td>

                    {/* Throughput */}
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-gray-400">
                      {perf?.throughputOpsS != null
                        ? `${fmtOpsS(perf.throughputOpsS)} ops/s`
                        : "\u2014"}
                    </td>

                    {/* Rank badges */}
                    <td className="px-4 py-2.5 text-center">
                      <div className="flex items-center justify-center gap-1">
                        {isFastest && (
                          <span
                            className="rounded-full px-2 py-0.5 text-[10px] font-bold bg-yellow-900/60 text-yellow-300"
                            title="Fastest in this experiment"
                          >
                            FAST
                          </span>
                        )}
                        {isMostAccurate && (
                          <span
                            className="rounded-full px-2 py-0.5 text-[10px] font-bold bg-emerald-900/60 text-emerald-300"
                            title="Most accurate in this experiment"
                          >
                            ACC
                          </span>
                        )}
                        {!isFastest && !isMostAccurate && (
                          <span className="text-gray-600">\u2014</span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
