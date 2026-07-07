import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, CheckCircle2, Gauge, Info, Target, Zap } from "lucide-react";
import type { ReactNode } from "react";
import { fetchManifest, fetchRun, fetchScorecard } from "../api/client";
import type { RunManifest, RunScorecard, ScorecardExperiment, ScorecardFamily, ScorecardRow } from "../api/types";
import Header from "../components/layout/Header";
import { CandidateBadges, candidateBaseId, candidateId, isUnavailable, provenanceText, supportReason } from "../components/CandidateBadges";
import { fmtNs, fmtValue, libColor } from "../utils/analytics";

export default function RunOverview() {
  const { runId } = useParams<{ runId: string }>();
  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => fetchRun(runId!),
    enabled: !!runId,
  });
  const scorecardQuery = useQuery({
    queryKey: ["scorecard", runId],
    queryFn: () => fetchScorecard(runId!),
    enabled: !!runId,
  });
  const manifestQuery = useQuery({
    queryKey: ["manifest", runId],
    queryFn: () => fetchManifest(runId!),
    enabled: !!runId,
    retry: false,
  });

  if (runQuery.isLoading || scorecardQuery.isLoading || manifestQuery.isLoading) {
    return <p className="text-gray-500">Loading run...</p>;
  }
  if (runQuery.error || scorecardQuery.error || !runQuery.data || !scorecardQuery.data) {
    return <p className="text-red-400">Failed to load run {runId}.</p>;
  }

  const run = runQuery.data;
  const scorecard = scorecardQuery.data;
  const manifest = manifestQuery.data ?? null;
  const evidence = buildSiderustEvidence(scorecard, manifest);
  const publicExperimentCount = scorecard.families.reduce(
    (total, family) => total + family.experiments.length,
    0,
  );
  const resultCount = Object.values(run.experiments).reduce(
    (total, results) => total + results.length,
    0,
  );
  const candidateIds = Array.from(
    new Set(Object.values(run.experiments).flatMap((results) => results.map((r) => candidateId(r)))),
  ).sort();

  return (
    <div className="space-y-7">
      <Header
        title={`Run ${run.id}`}
        subtitle={`${run.timestamp ?? ""} · ${run.machine ?? "unknown machine"}`}
        actions={
          <Link
            to="/"
            className="flex items-center gap-2 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            All Runs
          </Link>
        }
      />

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <RunFact icon={<Target className="h-5 w-5 text-emerald-300" />} label="Public Experiments" value={publicExperimentCount} />
        <RunFact icon={<Gauge className="h-5 w-5 text-blue-300" />} label="Families" value={scorecard.families.length} />
        <RunFact icon={<Zap className="h-5 w-5 text-yellow-300" />} label="References" value={scorecard.references.length} />
      </section>

      {manifest && <ScopePanel manifest={manifest} />}

      <section className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
        <h2 className="text-sm font-semibold text-white mb-2">Reference Policy</h2>
        <div className="flex flex-wrap gap-2">
          {scorecard.references.map((ref) => (
            <span key={ref} className="rounded-md border border-gray-700 px-2.5 py-1 text-xs text-gray-300">
              {ref}
            </span>
          ))}
        </div>
      </section>

      <EvidencePanel evidence={evidence} />
      <BlockersPanel blockers={evidence.blockers} />

      {scorecard.families.map((family) => (
        <FamilyScorecard key={family.family} family={family} runId={run.id} />
      ))}

      <section className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
        <h2 className="text-xs font-medium uppercase text-gray-400 mb-3">
          Run Configuration & Environment
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <Fact label="Experiments in artifact" value={run.experiments ? Object.keys(run.experiments).length : 0} />
          <Fact label="Result files" value={resultCount} />
          <Fact label="Candidate IDs" value={candidateIds.join(", ")} />
          <Fact label="Machine" value={run.machine ?? "unknown"} />
        </div>
      </section>
    </div>
  );
}

interface EvidenceBlocker {
  key: string;
  severity: "accuracy" | "performance" | "timing" | "coverage";
  title: string;
  detail: string;
}

interface SiderustEvidence {
  accuracyCompared: number;
  accuracyWins: number;
  accuracyCoWins: number;
  accuracyLosses: number;
  aniseAccuracyWins: number;
  aniseAccuracyCoWins: number;
  aniseAccuracyLosses: number;
  performanceCompared: number;
  performanceWins: number;
  performanceLosses: number;
  anisePerformanceWins: number;
  anisePerformanceLosses: number;
  invalidSiderustPerf: number;
  blockers: EvidenceBlocker[];
}

function ScopePanel({ manifest }: { manifest: RunManifest }) {
  const scope = manifest.scope ?? {};
  const config = manifest.config ?? {};
  const completeness = manifest.completeness ?? {};
  const missing = scope.missing_core_experiments ?? completeness.missing ?? [];
  const tags = scope.run_tags ?? (Array.isArray(config.run_tags) ? config.run_tags.map(String) : []);
  const partial = Boolean(scope.partial);
  const publication = manifest.publication;
  const pubGrade = publication?.grade;
  const notPublicationGrade = partial || pubGrade === "draft" || Boolean(publication?.publish_blockers?.length);
  const requested = completeness.requested ?? (Array.isArray(config.experiments) ? config.experiments.length : "?");
  const completed = completeness.completed ?? manifest.experiment_count ?? "?";
  const dirty = (publication?.git_dirty ?? manifest.metadata?.git_dirty) as Record<string, unknown> | undefined;
  const dirtyRepos = dirty ? Object.entries(dirty).filter(([, value]) => value === true).map(([repo]) => repo) : [];
  const missingRequested = scope.missing_requested_experiments ?? [];

  return (
    <section className={`rounded-lg border p-4 ${notPublicationGrade ? "border-amber-800/70 bg-amber-950/20" : "border-gray-800 bg-gray-900/40"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {notPublicationGrade ? <AlertTriangle className="mt-0.5 h-5 w-5 text-amber-300" /> : <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-300" />}
          <div>
            <h2 className="text-sm font-semibold text-white">Run Scope</h2>
            <p className="mt-1 text-xs text-gray-400">
              {partial
                ? `Partial ${scope.suite_label ?? "suite"} run — missing requested experiments or incomplete core coverage (${scope.core_experiments_covered ?? "?"}/${scope.core_experiments_total ?? "?"} core).`
                : `${scope.suite_label ?? "Complete"} run with all requested experiments finished.`}
              {pubGrade ? ` Publication grade: ${pubGrade}.` : ""}
            </p>
          </div>
        </div>
        <span className={`rounded-md px-2 py-1 text-[10px] uppercase ${notPublicationGrade ? "bg-amber-900/50 text-amber-200" : "bg-emerald-900/40 text-emerald-300"}`}>
          {pubGrade ?? (partial ? "partial" : "complete")}
        </span>
      </div>

      {publication?.publish_blockers && publication.publish_blockers.length > 0 && (
        <p className="mt-3 text-xs text-amber-100/80">
          Not publication-grade: {publication.publish_blockers.join("; ")}
        </p>
      )}

      {partial && missingRequested.length > 0 && (
        <p className="mt-2 text-xs text-amber-100/80">
          Missing requested: {missingRequested.slice(0, 8).join(", ")}
          {missingRequested.length > 8 ? `, +${missingRequested.length - 8} more` : ""}
        </p>
      )}

      {partial && missing.length > 0 && (
        <p className="mt-3 text-xs text-amber-100/80">
          Missing core experiments: {missing.slice(0, 10).join(", ")}
          {missing.length > 10 ? `, +${missing.length - 10} more` : ""}
        </p>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
        <Fact label="Completed" value={`${completed}/${requested}`} />
        <Fact label="Sample Count" value={scalarText(config.n)} />
        <Fact label="Seed" value={scalarText(config.seed)} />
        <Fact label="Perf Rounds" value={config.perf_enabled === false ? "disabled" : scalarText(config.perf_rounds)} />
        <Fact label="Horizons Cache" value={boolText(config.horizons_use_cache)} />
        <Fact label="Horizons Network" value={boolText(config.horizons_allow_network)} />
        <Fact label="Run Label" value={scalarText(scope.run_label ?? config.run_label)} />
        <Fact label="Dirty Repos" value={dirtyRepos.length ? dirtyRepos.join(", ") : "none"} />
      </div>
      {tags.length > 0 && <p className="mt-3 text-xs text-gray-500">Tags: {tags.join(", ")}</p>}
    </section>
  );
}

function EvidencePanel({ evidence }: { evidence: SiderustEvidence }) {
  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Info className="h-4 w-4 text-sky-300" />
        <h2 className="text-sm font-semibold text-white">Siderust Evidence</h2>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <EvidenceStat
          label="Accuracy"
          value={`${evidence.accuracyWins} wins, ${evidence.accuracyCoWins} co-wins`}
          detail={`${evidence.accuracyLosses} losses across ${evidence.accuracyCompared} rankable experiment rows`}
        />
        <EvidenceStat
          label="Performance"
          value={`${evidence.performanceWins}/${evidence.performanceCompared} valid wins`}
          detail={`${evidence.performanceLosses} valid losses; invalid Siderust timings: ${evidence.invalidSiderustPerf}`}
        />
        <EvidenceStat
          label="Versus ANISE"
          value={`${evidence.aniseAccuracyWins} accuracy wins, ${evidence.aniseAccuracyCoWins} co-wins`}
          detail={`${evidence.aniseAccuracyLosses} accuracy losses; ${evidence.anisePerformanceWins} performance wins, ${evidence.anisePerformanceLosses} losses`}
        />
      </div>
    </section>
  );
}

function BlockersPanel({ blockers }: { blockers: EvidenceBlocker[] }) {
  if (blockers.length === 0) {
    return (
      <section className="rounded-lg border border-emerald-900/60 bg-emerald-950/20 p-4">
        <h2 className="text-sm font-semibold text-white">Unresolved Blockers</h2>
        <p className="mt-1 text-xs text-emerald-200/80">No rankable Siderust losses or excluded candidates are present in this run.</p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
      <div className="mb-3 flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-300" />
        <h2 className="text-sm font-semibold text-white">Unresolved Blockers</h2>
      </div>
      <div className="space-y-2">
        {blockers.slice(0, 8).map((blocker) => (
          <div key={blocker.key} className="rounded-md border border-gray-800 bg-gray-950/40 px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded px-2 py-0.5 text-[10px] uppercase ${blockerClass(blocker.severity)}`}>
                {blocker.severity}
              </span>
              <span className="text-xs font-medium text-gray-200">{blocker.title}</span>
            </div>
            <p className="mt-1 text-xs text-gray-500">{blocker.detail}</p>
          </div>
        ))}
      </div>
      {blockers.length > 8 && (
        <p className="mt-3 text-xs text-gray-500">Showing 8 of {blockers.length} blockers.</p>
      )}
    </section>
  );
}

function EvidenceStat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950/30 p-3">
      <p className="text-xs uppercase text-gray-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-white">{value}</p>
      <p className="mt-1 text-xs text-gray-500">{detail}</p>
    </div>
  );
}

function FamilyScorecard({ family, runId }: { family: ScorecardFamily; runId: string }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold text-white">{family.family.replace(/_/g, " ")}</h2>
        <p className="text-xs text-gray-500">
          Accuracy wins only count rankable rows. Performance wins ignore invalid timing samples.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <WinsCard title="Accuracy" wins={family.accuracy_wins} />
        <WinsCard title="Performance" wins={family.performance_wins} />
      </div>

      <div className="space-y-4">
        {family.experiments.map((experiment) => (
          <div key={experiment.experiment} className="rounded-lg border border-gray-800 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 bg-gray-900/70 px-4 py-3">
              <div>
                <Link
                  to={`/runs/${runId}/experiments/${experiment.experiment}`}
                  className="text-sm font-semibold text-orange-300 hover:underline"
                >
                  {experiment.title}
                </Link>
                <p className="text-xs text-gray-500">
                  <span title={referenceTitle(experiment.experiment)}>{referenceLabel(experiment.experiment, experiment.reference_model ?? experiment.reference_library)}</span> · {experiment.metric.label} ({experiment.metric.unit})
                </p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {experiment.reference_lane && (
                    <span
                      className={`rounded-md px-2 py-0.5 text-[10px] uppercase ${
                        experiment.reference_lane === "geometric_vector"
                          ? "bg-sky-900/40 text-sky-300"
                          : "bg-fuchsia-900/40 text-fuchsia-300"
                      }`}
                      title="Reference lane (Horizons mode)"
                    >
                      {experiment.reference_lane.replace(/_/g, " ")}
                    </span>
                  )}
                  {experiment.tier && experiment.tier !== "public" && (
                    <span className="rounded-md bg-amber-900/30 px-2 py-0.5 text-[10px] uppercase text-amber-300">
                      {experiment.tier}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-[10px] uppercase">
                {experiment.best_accuracy && (
                  <span className="rounded-md bg-emerald-900/40 px-2 py-1 text-emerald-300" title="Best across exact-model + same-family-jpl + best-available rankable rows">
                    Accuracy: {experiment.best_accuracy}
                  </span>
                )}
                {experiment.best_accuracy_exact &&
                  experiment.best_accuracy_exact !== experiment.best_accuracy && (
                    <span className="rounded-md bg-teal-900/40 px-2 py-1 text-teal-300" title="Best when restricted to strict exact-model parity rows only (excludes same-family-jpl)">
                      Exact-model: {experiment.best_accuracy_exact}
                    </span>
                  )}
                {experiment.best_performance && (
                  <span className="rounded-md bg-yellow-900/40 px-2 py-1 text-yellow-300" title="Statistically valid fastest (perf_valid: finite ns ≥ 10ns/op, CV ≤ 20%)">
                    Perf (valid): {experiment.best_performance}
                  </span>
                )}
                {experiment.raw_fastest &&
                  experiment.raw_fastest !== experiment.best_performance && (
                    <span className="rounded-md bg-gray-800 px-2 py-1 text-gray-400" title="Raw minimum ns/op regardless of timing validity — NOT a statistically valid winner">
                      Raw fastest: {experiment.raw_fastest}
                    </span>
                  )}
              </div>
            </div>
            <ExperimentRows rows={experiment.rows} unit={experiment.metric.unit} />
          </div>
        ))}
      </div>
    </section>
  );
}

function ExperimentRows({ rows, unit }: { rows: ScorecardRow[]; unit: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-800 bg-gray-950/40 text-left uppercase text-gray-500">
            <th className="px-4 py-2">Candidate ID</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2">Provenance</th>
            <th className="px-4 py-2 text-right">p50</th>
            <th className="px-4 py-2 text-right">p99</th>
            <th className="px-4 py-2 text-right">Max</th>
            <th className="px-4 py-2 text-right">Delta vs Best</th>
            <th className="px-4 py-2 text-right">Latency</th>
            <th className="px-4 py-2 text-right">Perf Delta</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const unavailable = isUnavailable(row);
            const reason = supportReason(row);
            return (
            <tr key={candidateId(row)} className={`border-b border-gray-800/50 hover:bg-gray-800/30 ${unavailable ? "opacity-65" : ""}`}>
              <td className="px-4 py-2 text-gray-200">
                <span className="inline-flex flex-wrap items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: libColor(candidateBaseId(row)) }} />
                  <span>{candidateId(row)}</span>
                  <CandidateBadges row={row} />
                  {row.support_status && row.support_status !== "supported" && (
                    <span className="rounded-md bg-gray-800 px-2 py-0.5 text-[10px] uppercase text-gray-400" title={reason}>
                      {row.support_status}
                    </span>
                  )}
                </span>
                {unavailable && reason && <div className="mt-1 text-[11px] text-gray-500">{reason}</div>}
              </td>
              <td className="px-4 py-2">
                {row.status === "skipped" || row.support_status === "unsupported" || row.support_status === "runtime-blocked" ? (
                  <span
                    className="rounded-md bg-yellow-900/40 px-2 py-0.5 text-yellow-300"
                    title={reason}
                  >
                    {row.support_status === "runtime-blocked" ? "runtime-blocked" : row.support_status === "unsupported" ? "unsupported" : row.skip_reason && /spk|bsp|kernel/i.test(row.skip_reason) ? "SPK missing" : "skipped"}
                  </span>
                ) : row.status === "failed" ? (
                  <span className="rounded-md bg-red-900/40 px-2 py-0.5 text-red-300" title={row.failure_reason ?? undefined}>
                    failed
                  </span>
                ) : row.comparability_class === "exact-model" ? (
                  <span className="rounded-md bg-emerald-900/30 px-2 py-0.5 text-emerald-300" title={row.selected_model ?? undefined}>
                    exact-model{row.model_source ? ` · ${row.model_source}` : ""}
                  </span>
                ) : row.comparability_class === "same-family-jpl" ? (
                  <span className="rounded-md bg-amber-900/30 px-2 py-0.5 text-amber-300" title={`Same JPL DE family, different kernel version than the reference (e.g. DE440 vs DE441)${row.selected_model ? ` · ${row.selected_model}` : ""}`}>
                    same-family-jpl{row.model_source ? ` · ${row.model_source}` : ""}
                  </span>
                ) : row.comparability_class === "best-available" ? (
                  <span className="rounded-md bg-sky-900/30 px-2 py-0.5 text-sky-300" title={row.selected_model ?? undefined}>
                    best-available{row.model_source ? ` · ${row.model_source}` : ""}
                  </span>
                ) : row.comparability_class === "diagnostic-profile" ? (
                  <span className="rounded-md bg-violet-900/30 px-2 py-0.5 text-violet-300" title={row.rank_exclusion_reason ?? undefined}>
                    diagnostic
                  </span>
                ) : row.rankable_accuracy ? (
                  <span className="rounded-md bg-emerald-900/30 px-2 py-0.5 text-emerald-300">rankable</span>
                ) : (
                  <span className="rounded-md bg-amber-900/30 px-2 py-0.5 text-amber-300" title={row.rank_exclusion_reason ?? undefined}>
                    not comparable
                  </span>
                )}
              </td>
              <td className="px-4 py-2 text-gray-400" title={provenanceText(row)}>
                {provenanceText(row) ?? "—"}
              </td>
              <td className="px-4 py-2 text-right font-mono text-gray-400">{unavailable ? "n/a" : fmtValue(row.p50)}</td>
              <td className="px-4 py-2 text-right font-mono text-gray-200">{unavailable ? "n/a" : fmtValue(row.p99)}</td>
              <td className="px-4 py-2 text-right font-mono text-gray-400">{unavailable ? "n/a" : fmtValue(row.max)}</td>
              <td
                className="px-4 py-2 text-right font-mono text-gray-400"
                title={
                  unavailable
                    ? row.skip_reason ?? undefined
                    : row.accuracy_delta_vs_best == null && row.accuracy_delta_diagnostic != null
                    ? row.rank_exclusion_reason ?? "Diagnostic delta — not rankable for accuracy crowns"
                    : row.rank_exclusion_reason ?? undefined
                }
              >
                {unavailable
                  ? "n/a"
                  : row.accuracy_delta_vs_best != null
                  ? `${fmtValue(row.accuracy_delta_vs_best)} ${unit}`
                  : row.accuracy_delta_diagnostic != null
                  ? `${fmtValue(row.accuracy_delta_diagnostic)} ${unit} (diag)`
                  : "—"}
              </td>
              <td
                className={`px-4 py-2 text-right font-mono ${(row.perf_valid_display ?? row.perf_valid) ? "text-gray-300" : "text-gray-500"}`}
                title={
                  unavailable
                    ? row.skip_reason ?? undefined
                    : !(row.perf_valid_display ?? row.perf_valid) && (row.ns_per_op_display ?? row.ns_per_op) != null
                    ? row.perf_warnings?.join("; ") || "Measured timing — not statistically valid for performance crowns"
                    : undefined
                }
              >
                {unavailable ? "n/a" : fmtNs(row.ns_per_op_display ?? row.ns_per_op)}
                {!unavailable && !(row.perf_valid_display ?? row.perf_valid) && (row.ns_per_op_display ?? row.ns_per_op) != null && (
                  <span className="ml-1 text-amber-400" title="High CV or invalid scalar sample">⚠</span>
                )}
              </td>
              <td
                className="px-4 py-2 text-right font-mono text-gray-400"
                title={
                  unavailable
                    ? row.skip_reason ?? undefined
                    : row.performance_delta_vs_best_pct != null && !(row.perf_valid_display ?? row.perf_valid)
                    ? "Delta vs valid winner — this row is not perf-valid"
                    : undefined
                }
              >
                {unavailable ? "n/a" : row.performance_delta_vs_best_pct == null ? "—" : `+${row.performance_delta_vs_best_pct.toFixed(1)}%`}
              </td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function WinsCard({ title, wins }: { title: string; wins: Record<string, number> }) {
  const entries = Object.entries(wins).sort((a, b) => b[1] - a[1]);
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
      <h3 className="text-xs font-medium uppercase text-gray-400 mb-2">{title} by Family</h3>
      {entries.length === 0 ? (
        <p className="text-xs text-gray-600">No rankable data</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {entries.map(([name, count]) => (
            <span key={name} className="rounded-md border border-gray-700 px-2.5 py-1 text-xs text-gray-300">
              {name}: {count}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function RunFact({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-4">
      <div className="flex items-center gap-2 text-gray-400">
        {icon}
        <span className="text-xs uppercase">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
    </div>
  );
}

function referenceLabel(experiment: string | undefined, fallback: string): string {
  return experiment === "kepler_solver" ? "pipeline_python" : fallback;
}

function referenceTitle(experiment: string | undefined): string | undefined {
  return experiment === "kepler_solver"
    ? "Newton-Raphson to machine epsilon (no SOFA/ERFA public Kepler API)"
    : undefined;
}

function buildSiderustEvidence(scorecard: RunScorecard, manifest: RunManifest | null): SiderustEvidence {
  const evidence: SiderustEvidence = {
    accuracyCompared: 0,
    accuracyWins: 0,
    accuracyCoWins: 0,
    accuracyLosses: 0,
    aniseAccuracyWins: 0,
    aniseAccuracyCoWins: 0,
    aniseAccuracyLosses: 0,
    performanceCompared: 0,
    performanceWins: 0,
    performanceLosses: 0,
    anisePerformanceWins: 0,
    anisePerformanceLosses: 0,
    invalidSiderustPerf: 0,
    blockers: [],
  };

  for (const experiment of allScorecardExperiments(scorecard)) {
    const siderustRows = experiment.rows.filter((row) => rowIsSiderust(row));
    const aniseRows = experiment.rows.filter((row) => rowIsAnise(row));
    const rankableSiderust = siderustRows.filter((row) => row.rankable_accuracy && row.p99 != null && !isUnavailable(row));
    const rankableAnise = aniseRows.filter((row) => row.rankable_accuracy && row.p99 != null && !isUnavailable(row));
    const coWinners = experiment.best_accuracy_co_winners ?? (experiment.best_accuracy ? [experiment.best_accuracy] : []);
    const siderustAccuracyWinner = coWinners.some(isSiderustLabel);
    const aniseAccuracyWinner = coWinners.some(isAniseLabel);

    if (experiment.best_accuracy && rankableSiderust.length > 0) {
      evidence.accuracyCompared += 1;
      if (siderustAccuracyWinner && coWinners.length > 1) {
        evidence.accuracyCoWins += 1;
      } else if (siderustAccuracyWinner) {
        evidence.accuracyWins += 1;
      } else {
        evidence.accuracyLosses += 1;
        const bestRow = rowForLabel(experiment.rows, experiment.best_accuracy);
        const siderustBest = bestMetricRow(rankableSiderust, "p99");
        evidence.blockers.push({
          key: `accuracy:${experiment.experiment}`,
          severity: "accuracy",
          title: `${experiment.title}: accuracy leader is ${experiment.best_accuracy}`,
          detail: `Best Siderust p99 ${metricText(siderustBest?.p99, experiment.metric.unit)}; winning p99 ${metricText(bestRow?.p99, experiment.metric.unit)}.`,
        });
      }
    }

    if (experiment.best_accuracy && rankableSiderust.length > 0 && rankableAnise.length > 0) {
      if (siderustAccuracyWinner && !aniseAccuracyWinner) evidence.aniseAccuracyWins += 1;
      else if (siderustAccuracyWinner && aniseAccuracyWinner) evidence.aniseAccuracyCoWins += 1;
      else if (aniseAccuracyWinner) evidence.aniseAccuracyLosses += 1;
    }

    const siderustPerfRows = siderustRows.filter((row) => row.ns_per_op != null && !isUnavailable(row));
    const anisePerfRows = aniseRows.filter((row) => row.ns_per_op != null && !isUnavailable(row));
    const invalidPerfRows = siderustPerfRows.filter((row) => !row.perf_valid);
    evidence.invalidSiderustPerf += invalidPerfRows.length;
    for (const row of invalidPerfRows) {
      evidence.blockers.push({
        key: `timing:${experiment.experiment}:${candidateId(row)}`,
        severity: "timing",
        title: `${experiment.title}: ${row.display_name} timing invalid`,
        detail: timingReason(row),
      });
    }

    if (experiment.best_performance && siderustPerfRows.length > 0) {
      evidence.performanceCompared += 1;
      if (isSiderustLabel(experiment.best_performance)) {
        evidence.performanceWins += 1;
      } else {
        evidence.performanceLosses += 1;
        const bestRow = rowForLabel(experiment.rows, experiment.best_performance);
        const siderustBest = bestMetricRow(siderustPerfRows.filter((row) => row.perf_valid), "ns_per_op");
        evidence.blockers.push({
          key: `performance:${experiment.experiment}`,
          severity: "performance",
          title: `${experiment.title}: valid fastest is ${experiment.best_performance}`,
          detail: `Best Siderust latency ${fmtNs(siderustBest?.ns_per_op ?? null)}; winning latency ${fmtNs(bestRow?.ns_per_op ?? null)}.`,
        });
      }
    }

    if (experiment.best_performance && siderustPerfRows.length > 0 && anisePerfRows.length > 0) {
      if (isSiderustLabel(experiment.best_performance)) evidence.anisePerformanceWins += 1;
      else if (isAniseLabel(experiment.best_performance)) evidence.anisePerformanceLosses += 1;
    }
  }

  const perExperiment = manifest?.completeness?.per_experiment ?? {};
  for (const [experiment, completeness] of Object.entries(perExperiment)) {
    for (const excluded of completeness.excluded_candidates ?? []) {
      if (!isSiderustLabel(excluded.candidate_id)) continue;
      evidence.blockers.push({
        key: `coverage:${experiment}:${excluded.candidate_id}`,
        severity: "coverage",
        title: `${experiment}: ${excluded.candidate_id} excluded`,
        detail: excluded.reason,
      });
    }
  }

  return evidence;
}

function allScorecardExperiments(scorecard: RunScorecard): ScorecardExperiment[] {
  return scorecard.families.flatMap((family) => family.experiments);
}

function rowIsSiderust(row: ScorecardRow): boolean {
  return isSiderustLabel(row.display_name) || isSiderustLabel(row.candidate_id) || candidateBaseId(row) === "siderust";
}

function rowIsAnise(row: ScorecardRow): boolean {
  return isAniseLabel(row.display_name) || isAniseLabel(row.candidate_id) || candidateBaseId(row) === "anise";
}

function isSiderustLabel(value: string | null | undefined): boolean {
  return (value ?? "").toLowerCase().startsWith("siderust");
}

function isAniseLabel(value: string | null | undefined): boolean {
  return (value ?? "").toLowerCase().startsWith("anise");
}

function rowForLabel(rows: ScorecardRow[], label: string | null | undefined): ScorecardRow | undefined {
  if (!label) return undefined;
  return rows.find((row) => row.display_name === label || row.candidate_id === label || candidateId(row) === label);
}

function bestMetricRow(rows: ScorecardRow[], key: "p99" | "ns_per_op"): ScorecardRow | undefined {
  return rows
    .filter((row) => row[key] != null)
    .sort((a, b) => (a[key] ?? Number.POSITIVE_INFINITY) - (b[key] ?? Number.POSITIVE_INFINITY))[0];
}

function metricText(value: number | null | undefined, unit: string): string {
  return value == null ? "missing" : `${fmtValue(value)} ${unit}`;
}

function timingReason(row: ScorecardRow): string {
  if (row.perf_warnings?.length) return row.perf_warnings.join("; ");
  if (row.perf_cv_pct != null) return `CV ${row.perf_cv_pct.toFixed(1)}% exceeds the valid timing threshold.`;
  return "Timing sample did not meet the valid-performance criteria.";
}

function scalarText(value: unknown): string {
  if (value == null || value === "") return "none";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number" || typeof value === "string") return String(value);
  if (Array.isArray(value)) return value.map(String).join(", ");
  return "set";
}

function boolText(value: unknown): string {
  if (typeof value === "boolean") return value ? "yes" : "no";
  return scalarText(value);
}

function blockerClass(severity: EvidenceBlocker["severity"]): string {
  if (severity === "accuracy") return "bg-rose-900/40 text-rose-300";
  if (severity === "performance") return "bg-yellow-900/40 text-yellow-300";
  if (severity === "timing") return "bg-sky-900/40 text-sky-300";
  return "bg-gray-800 text-gray-300";
}

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span className="block text-gray-500">{label}</span>
      <span className="text-gray-300">{value}</span>
    </div>
  );
}
