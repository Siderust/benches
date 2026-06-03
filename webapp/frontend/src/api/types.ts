/** TypeScript interfaces matching the backend Pydantic schemas. */

export interface PercentileStats {
  p50: number | null;
  p90: number | null;
  p95: number | null;
  p99: number | null;
  max: number | null;
  min: number | null;
  mean: number | null;
  rms: number | null;
}

export interface WorstCase {
  jd_tt: number | null;
  angular_error_mas: number | null;
}

export interface PerformanceData {
  per_op_ns: number | null;
  per_op_ns_mean: number | null;
  per_op_ns_median: number | null;
  per_op_ns_std_dev: number | null;
  per_op_ns_min: number | null;
  per_op_ns_max: number | null;
  per_op_ns_ci95: [number, number] | null;
  per_op_ns_cv_pct: number | null;
  throughput_ops_s: number | null;
  total_ns: number | null;
  total_ns_median: number | null;
  batch_size: number | null;
  rounds: number | null;
  samples: number[] | null;
  valid: boolean | null;
  warnings: string[] | null;
}

export interface ExperimentDescription {
  title?: string;
  what?: string;
  why?: string;
  units?: string;
  interpret?: string;
}

export interface BenchmarkConfig {
  perf_rounds?: number;
  perf_warmup?: number;
  perf_enabled?: boolean;
}

export interface AlignmentChecklist {
  units?: Record<string, string>;
  time_input?: string;
  time_scales?: string;
  leap_seconds?: string;
  earth_orientation?: Record<string, string>;
  geodesy?: string;
  refraction?: string;
  ephemeris_source?: string;
  models?: Record<string, string>;
  model_parity_class?: string;
  candidate_parity?: string;
  mode?: string;
  note?: string;
  [key: string]: unknown;
}

export interface RunMetadata {
  date: string | null;
  git_shas: Record<string, string>;
  git_branch: string | null;
  cpu: string | null;
  cpu_model: string | null;
  cpu_count: number | null;
  os: string | null;
  platform_detail: string | null;
  toolchain: Record<string, string>;
}

export interface ExperimentResult {
  experiment: string;
  candidate_library: string;
  candidate_id?: string | null;
  reference_library: string;
  description: ExperimentDescription | Record<string, unknown>;
  alignment: AlignmentChecklist | null;
  inputs: Record<string, unknown>;
  accuracy: Record<string, unknown>;
  performance: PerformanceData | Record<string, unknown>;
  reference_performance: PerformanceData | Record<string, unknown>;
  benchmark_config: BenchmarkConfig | Record<string, unknown>;
  run_metadata: RunMetadata | null;
  family?: string | null;
  tier?: string | null;
  candidate_profile?: string | null;
  reference_model?: string | null;
  rankable_accuracy?: boolean | null;
  rank_exclusion_reason?: string | null;
  source_provenance?: Record<string, unknown>;
  /** A1 / rankability audit additions. */
  comparability_class?: "exact-model" | "same-family-jpl" | "best-available" | "diagnostic-profile" | "not-comparable" | string | null;
  selected_model?: string | null;
  model_source?: string | null;
  lane?: string | null;
  api_surface?: "public" | "internal" | "reference" | string | null;
  support_status?: "supported" | "unsupported" | "runtime-blocked" | string | null;
  catalog_model?: string | null;
  catalog_source?: string | null;
  catalog_lane?: "geometric" | "apparent" | string | null;
  catalog_parity?: string | null;
  catalog_exclusion_reason?: string | null;
  status?: "ok" | "skipped" | "failed" | string | null;
  skip_reason?: string | null;
  failure_reason?: string | null;
}

export interface RunSummary {
  id: string;
  timestamp: string | null;
  git_shas: Record<string, string>;
  machine: string | null;
  experiments: string[];
  libraries: string[];
  result_count: number;
}

export interface RunDetail {
  id: string;
  timestamp: string | null;
  git_shas: Record<string, string>;
  machine: string | null;
  experiments: Record<string, ExperimentResult[]>;
}

export interface MetricDelta {
  experiment: string;
  library: string;
  metric: string;
  value_a: number | null;
  value_b: number | null;
  delta: number | null;
  delta_pct: number | null;
  regression: boolean;
}

export interface CompareResult {
  run_a: string;
  run_b: string;
  deltas: MetricDelta[];
}

export interface ScorecardRow {
  library: string;
  candidate_id?: string | null;
  display_name: string;
  profile: string | null;
  rankable_accuracy: boolean;
  rank_exclusion_reason: string | null;
  candidate_parity: string | null;
  /** A1 additive fields */
  comparability_class?: "exact-model" | "same-family-jpl" | "best-available" | "diagnostic-profile" | "not-comparable" | string | null;
  model_parity_class?: string | null;
  selected_model?: string | null;
  model_source?: string | null;
  lane?: string | null;
  api_surface?: "public" | "internal" | "reference" | string | null;
  support_status?: "supported" | "unsupported" | "runtime-blocked" | string | null;
  catalog_model?: string | null;
  catalog_source?: string | null;
  catalog_lane?: "geometric" | "apparent" | string | null;
  catalog_parity?: string | null;
  catalog_exclusion_reason?: string | null;
  status?: "ok" | "skipped" | "failed" | string;
  skip_reason?: string | null;
  failure_reason?: string | null;
  p50: number | null;
  p99: number | null;
  max: number | null;
  ns_per_op: number | null;
  perf_valid: boolean;
  perf_cv_pct: number | null;
  perf_warnings: string[];
  accuracy_delta_vs_best: number | null;
  performance_delta_vs_best_pct: number | null;
  source_provenance: Record<string, unknown>;
  reference_source_tag?: string | null;
}

export interface ScorecardExperiment {
  experiment: string;
  title: string;
  reference_library: string;
  reference_model: string | null;
  reference_lane?: string | null;
  tier?: string | null;
  metric: { key: string; label: string; unit: string };
  rows: ScorecardRow[];
  best_accuracy: string | null;
  best_accuracy_exact?: string | null;
  best_accuracy_co_winners?: string[] | null;
  best_accuracy_exact_co_winners?: string[] | null;
  best_performance: string | null;
  /** Audit issue #3: raw minimum ns/op regardless of timing validity. Never
   * equivalent to the statistically valid winner in `best_performance`. */
  raw_fastest?: string | null;
}

export interface ScorecardFamily {
  family: string;
  experiments: ScorecardExperiment[];
  accuracy_wins: Record<string, number>;
  performance_wins: Record<string, number>;
}

export interface RunScorecard {
  run_id: string;
  timestamp: string | null;
  machine: string | null;
  references: string[];
  families: ScorecardFamily[];
  git_shas?: Record<string, string>;
}

export interface RunPublication {
  grade?: "publication" | "draft" | string;
  publish_blockers?: string[];
  git_dirty?: Record<string, boolean | null>;
  allow_dirty_override?: boolean;
  allow_partial_override?: boolean;
}

export interface RunScope {
  suite_label?: string;
  partial?: boolean;
  core_complete?: boolean;
  core_partial?: boolean;
  core_experiments_total?: number;
  core_experiments_covered?: number;
  missing_core_experiments?: string[];
  missing_requested_experiments?: string[];
  extra_experiments?: string[];
  run_label?: string | null;
  run_phase?: string | null;
  run_tags?: string[];
}

export interface ExcludedCandidate {
  candidate_id: string;
  support_status: string;
  reason: string;
}

export interface RunManifest {
  run_id?: string;
  config?: Record<string, unknown>;
  scope?: RunScope;
  publication?: RunPublication;
  latest_results_merge?: { is_merge?: boolean };
  labels?: {
    run_label?: string | null;
    run_phase?: string | null;
    run_tags?: string[];
  };
  metadata?: Record<string, unknown>;
  completeness?: {
    requested?: number;
    completed?: number;
    missing?: string[];
    completed_experiments?: string[];
    libraries?: string[];
    per_experiment?: Record<string, {
      requested_adapters: string[];
      ok: number;
      skipped: number;
      failed: number;
      lane: string | null;
      reference_lane: string | null;
      reference_source_tag: string | null;
      excluded_candidates?: ExcludedCandidate[];
      rows: Array<{
        library: string;
        candidate_id?: string | null;
        status: string;
        skip_reason: string | null;
        failure_reason: string | null;
        rankable: boolean | null;
        rankability_reason: string | null;
      }>;
    }>;
  };
  experiment_count?: number;
  total_results?: number;
}

export interface LabIndex {
  schema_version: number;
  latest: { run_id?: string; timestamp: string | null; machine: string | null } | null;
  runs: RunSummary[];
}

/** Consistent color mapping for libraries. */
export const LIBRARY_COLORS: Record<string, string> = {
  erfa: "#3b82f6",       // blue
  siderust: "#f97316",   // orange
  astropy: "#22c55e",    // green
  libnova: "#ef4444",    // red
  anise: "#06b6d4",      // cyan
  jpl_horizons: "#a855f7", // purple
};

export const ALL_EXPERIMENTS = [
  "frame_rotation_bpn",
  "gmst_era",
  "equ_ecl",
  "equ_horizontal",
  "solar_position",
  "lunar_position",
  "mercury_position",
  "venus_position",
  "mars_position",
  "jupiter_position",
  "saturn_position",
  "uranus_position",
  "neptune_position",
  "kepler_solver",
] as const;
