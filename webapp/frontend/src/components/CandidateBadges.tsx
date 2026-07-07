import type { AlignmentChecklist } from "../api/types";

export interface CandidateLike {
  candidate_id?: string | null;
  display_name?: string | null;
  library?: string | null;
  candidate_library?: string | null;
  api_surface?: string | null;
  support_status?: string | null;
  catalog_model?: string | null;
  catalog_source?: string | null;
  catalog_lane?: string | null;
  catalog_parity?: string | null;
  catalog_exclusion_reason?: string | null;
  selected_model?: string | null;
  model_source?: string | null;
  lane?: string | null;
  comparability_class?: string | null;
  model_parity_class?: string | null;
  alignment?: AlignmentChecklist | null;
  status?: string | null;
  skip_reason?: string | null;
  failure_reason?: string | null;
  rank_exclusion_reason?: string | null;
}

export function candidateId(row: CandidateLike): string {
  return row.candidate_id ?? row.display_name ?? row.library ?? row.candidate_library ?? "unknown";
}

export function candidateBaseId(row: CandidateLike): string {
  return row.candidate_library ?? row.library ?? candidateId(row).split(":")[0];
}

export function catalogLane(row: CandidateLike): string | null | undefined {
  return row.catalog_lane ?? row.lane ?? (row.alignment?.lane as string | undefined);
}

/** Authoritative parity badge: comparability_class from the pipeline. */
export function catalogParity(row: CandidateLike): string | null | undefined {
  return row.comparability_class ?? row.catalog_parity ?? row.model_parity_class;
}

export function provenanceText(row: CandidateLike): string | undefined {
  const model = row.catalog_model ?? row.selected_model;
  const source = row.catalog_source ?? row.model_source;
  return [model, source].filter(Boolean).join(" · ") || undefined;
}

export function supportReason(row: CandidateLike): string | undefined {
  return row.catalog_exclusion_reason ?? row.skip_reason ?? row.failure_reason ?? row.rank_exclusion_reason ?? undefined;
}

export function isUnavailable(row: CandidateLike): boolean {
  return row.support_status === "unsupported" || row.support_status === "runtime-blocked" || row.status === "skipped";
}

function badgeClass(kind: "surface" | "lane" | "parity"): string {
  if (kind === "surface") return "border-gray-700 bg-gray-800/70 text-gray-300";
  if (kind === "lane") return "border-indigo-800/60 bg-indigo-950/50 text-indigo-300";
  return "border-sky-800/60 bg-sky-950/50 text-sky-300";
}

export function CandidateBadges({ row }: { row: CandidateLike }) {
  const title = provenanceText(row);
  const lane = catalogLane(row);
  const parity = catalogParity(row);

  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {row.api_surface && (
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${badgeClass("surface")}`} title={title}>
          {row.api_surface}
        </span>
      )}
      {lane && (
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${badgeClass("lane")}`} title={title}>
          {lane.replace(/_/g, " ")}
        </span>
      )}
      {parity && (
        <span
          className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${badgeClass("parity")}`}
          title={[title, row.catalog_parity && row.catalog_parity !== parity ? `catalog: ${row.catalog_parity}` : null].filter(Boolean).join(" · ") || undefined}
        >
          {parity.replace(/_/g, " ")}
        </span>
      )}
    </span>
  );
}
