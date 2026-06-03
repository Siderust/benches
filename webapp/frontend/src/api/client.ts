/**
 * Static JSON client for the internal standalone dashboard.
 *
 * Layout (see pipeline/export_static.py):
 *   /data/benches/index.json
 *   /data/benches/latest/{scorecard,manifest}.json
 *   /data/benches/latest/experiments/<id>.json
 *   /data/benches/runs/<run_id>/{scorecard,manifest}.json
 *   /data/benches/runs/<run_id>/experiments/<id>.json
 */

import type {
  CompareResult,
  ExperimentResult,
  LabIndex,
  MetricDelta,
  RunDetail,
  RunManifest,
  RunScorecard,
  RunSummary,
} from "./types";

const DATA_ROOT = (() => {
  // Resolved at build time by Vite's `base` config.
  // Standalone builds ship data inside the bundle under <base>/data/lab.
  const base = (import.meta.env?.BASE_URL ?? "/").replace(/\/+$/, "");
  return `${base || ""}/data/lab`;
})();

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${path}`);
  return (await res.json()) as T;
}

function runBase(runId: string): string {
  return runId === "latest" ? `${DATA_ROOT}/latest` : `${DATA_ROOT}/runs/${runId}`;
}

export function dataUrlForRun(runId: string, file = "manifest.json"): string {
  const cleanFile = file.replace(/^\/+/, "");
  return `${runBase(runId)}/${cleanFile}`;
}

// ----- Runs ----- //

export async function fetchRuns(): Promise<RunSummary[]> {
  const index = await getJson<LabIndex>(`${DATA_ROOT}/index.json`);
  const out: RunSummary[] = [...(index.runs ?? [])];
  if (index.latest) {
    out.unshift({
      id: "latest",
      timestamp: index.latest.timestamp,
      git_shas: {},
      machine: index.latest.machine,
      experiments: [],
      libraries: [],
      result_count: 0,
    });
  }
  return out;
}

export async function fetchRun(runId: string): Promise<RunDetail> {
  // Synthesise RunDetail from scorecard + experiment files: we read the
  // scorecard, then load each experiment JSON.
  const card = await fetchScorecard(runId);
  const experiments: Record<string, ExperimentResult[]> = {};
  const fams = card.families ?? [];
  await Promise.all(
    fams.flatMap((f) =>
      f.experiments.map(async (e) => {
        try {
          const payload = await getJson<{ rows: ExperimentResult[] }>(
            `${runBase(runId)}/experiments/${e.experiment}.json`
          );
          experiments[e.experiment] = payload.rows ?? [];
        } catch {
          experiments[e.experiment] = [];
        }
      })
    )
  );
  return {
    id: runId,
    timestamp: card.timestamp ?? null,
    git_shas: card.git_shas ?? {},
    machine: card.machine ?? null,
    experiments,
  };
}

export async function fetchScorecard(runId: string): Promise<RunScorecard> {
  return getJson<RunScorecard>(`${runBase(runId)}/scorecard.json`);
}

export async function fetchManifest(runId: string): Promise<RunManifest> {
  return getJson<RunManifest>(`${runBase(runId)}/manifest.json`);
}

export async function fetchExperiment(
  runId: string,
  experiment: string
): Promise<ExperimentResult[]> {
  const payload = await getJson<{ rows: ExperimentResult[] }>(
    `${runBase(runId)}/experiments/${experiment}.json`
  );
  return payload.rows ?? [];
}

export async function reloadRuns(): Promise<{ status: string }> {
  // Static mode: nothing to reload server-side. Returning OK keeps the
  // call sites that only react to success unchanged.
  return { status: "static" };
}

// ----- Compare (client-side delta against two run scorecards) ----- //

export async function fetchCompare(runA: string, runB: string): Promise<CompareResult> {
  const [a, b] = await Promise.all([fetchScorecard(runA), fetchScorecard(runB)]);

  type IndexedRow = { p99: number | null; max: number | null; metricKey: string };
  function index(card: RunScorecard): Map<string, IndexedRow> {
    const m = new Map<string, IndexedRow>();
    for (const fam of card.families ?? []) {
      for (const exp of fam.experiments ?? []) {
        for (const row of exp.rows ?? []) {
          m.set(`${exp.experiment}::${row.candidate_id ?? row.display_name ?? row.library}`, {
            p99: row.p99 ?? null,
            max: row.max ?? null,
            metricKey: exp.metric?.key ?? "",
          });
        }
      }
    }
    return m;
  }

  const ia = index(a);
  const ib = index(b);
  const keys = new Set([...ia.keys(), ...ib.keys()]);

  const deltas: MetricDelta[] = [];
  for (const key of keys) {
    const [exp, lib] = key.split("::");
    const ra = ia.get(key);
    const rb = ib.get(key);
    for (const field of ["p99", "max"] as const) {
      const va = ra ? ra[field] : null;
      const vb = rb ? rb[field] : null;
      if (va == null && vb == null) continue;
      const delta = va != null && vb != null ? vb - va : null;
      const delta_pct = delta != null && va !== 0 && va != null ? (delta / Math.abs(va)) * 100 : null;
      deltas.push({
        experiment: exp,
        library: lib,
        metric: `${(ra?.metricKey ?? rb?.metricKey ?? "metric")}.${field}`,
        value_a: va,
        value_b: vb,
        delta,
        delta_pct,
        regression: delta != null && delta > 0,
      });
    }
  }
  return { run_a: runA, run_b: runB, deltas };
}
