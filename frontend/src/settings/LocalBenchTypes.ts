// K07C LocalBench settings sub-lane: client types for the frozen K05 M3
// STEP1e route table (RECORDS/day1/K05_M3/test_iface_m3.py:100-114) and the
// M4 EvidenceTier union. Scan/estimate/runs/pause/resume/stop/results follow
// the in-workspace M3 surface exactly; there are no /levels, /run or
// /results/{id} routes upstream. Settings-side aggregates (scan result with
// path, accepted run with estimate) keep the tab flow intact.

import { z } from "zod";

// K05 M4 capability-store EvidenceTier, verbatim union.
export type EvidenceTier = "UNKNOWN" | "PROXY" | "MEASURED";

// Benchmark depth selected in the tab flow (path -> scan -> level -> run).
export type BenchmarkLevel = "quick" | "standard" | "deep";

// K05 M3 BenchLevel wire values (RECORDS/day1/K05_M3/bench_protocol.py:
// Quick | Standard | Deep; test_iface_m3.py drives level "Quick").
export type BenchWireLevel = "Quick" | "Standard" | "Deep";

export const BENCH_WIRE_LEVEL: Record<BenchmarkLevel, BenchWireLevel> = {
  quick: "Quick",
  standard: "Standard",
  deep: "Deep",
};

export function toWireLevel(level: BenchmarkLevel): BenchWireLevel {
  return BENCH_WIRE_LEVEL[level];
}

export function fromWireLevel(level: BenchWireLevel): BenchmarkLevel {
  if (level === "Quick") {
    return "quick";
  }
  if (level === "Standard") {
    return "standard";
  }
  return "deep";
}

export type PcLoad = "low" | "normal" | "high";

// Settings-side default PC load per level (no M3 counterpart; keeps the
// tab loadWarning live on estimate data).
export const LEVEL_PC_LOAD: Record<BenchmarkLevel, PcLoad> = {
  quick: "low",
  standard: "normal",
  deep: "high",
};

// K05 M3 ResultKind (bench_protocol.py: PROXY | MEASURED).
export type ResultKind = "PROXY" | "MEASURED";

const ResultKindSchema: z.ZodType<ResultKind> = z.enum(["PROXY", "MEASURED"]);

export function kindToTier(kind: ResultKind): EvidenceTier {
  return kind;
}

export interface LocalBenchHardwareProfile {
  gpu_vendor: string;
  gpu_model: string | null;
  vram_mb: number | null;
  ram_mb: number;
  cpu_only: boolean;
}

export interface LocalBenchModel {
  model_id: string;
  display_name: string;
  evidence: EvidenceTier;
}

export interface LocalBenchScanResult {
  path: string;
  models: LocalBenchModel[];
}

// K05 M3 BenchEstimate (bench_protocol.py): estimate for one model + level.
export interface LocalBenchEstimate {
  model_id: string;
  level: BenchmarkLevel;
  minutes_min: number;
  minutes_max: number;
}

// K05 M3 runs request body (test_iface_m3.py:103): {model_id, level}.
export interface LocalBenchRunRequest {
  model_id: string;
  level: BenchmarkLevel;
}

export interface LocalBenchRunAccepted {
  run_id: string;
  estimated_duration_s: number;
  pc_load: PcLoad;
}

// K05 M3 BenchResultRow (bench_protocol.py): one case row of a finished run.
export interface LocalBenchResultRow {
  case_id: string;
  kind: ResultKind;
  model_id: string;
  hardware: LocalBenchHardwareProfile;
  score?: number | null;
}

// 111-UI per-change decision record shown in the tab: one entry per
// finished benchmark run.
export interface LocalBenchDecisionRecord {
  decision_id: string;
  change: "run";
  run_id: string;
  model_id: string;
  level: BenchmarkLevel;
  evidence: EvidenceTier;
  duration_s: number;
  recorded_at: string;
}

// Frozen K05 M3 STEP1e route table (test_iface_m3.py:100-114: POST runs,
// pause, resume, stop; GET scan, estimate, results).
export const LOCALBENCH_ENDPOINTS = {
  scan: "/api/v1/local/bench/scan",
  estimate: "/api/v1/local/bench/estimate",
  runs: "/api/v1/local/bench/runs",
  pause: "/api/v1/local/bench/runs/pause",
  resume: "/api/v1/local/bench/runs/resume",
  stop: "/api/v1/local/bench/runs/stop",
  results: "/api/v1/local/bench/results",
  status: "/api/v1/local/bench/runs/status",
} as const;

export type LocalBenchEndpointKey = keyof typeof LOCALBENCH_ENDPOINTS;

export function expandBenchScan(template: string, path: string): string {
  // The folder the user typed is the allowlist entry: scan_models stays
  // allowlist-first and still refuses drive roots and forbidden segments.
  const folder = encodeURIComponent(path);
  return `${template}?path=${folder}&allowlist=${folder}`;
}

export function expandBenchEstimate(
  template: string,
  modelId: string,
  level: BenchmarkLevel,
): string {
  const query =
    `model_id=${encodeURIComponent(modelId)}` +
    `&level=${encodeURIComponent(toWireLevel(level))}`;
  return `${template}?${query}`;
}

export function expandBenchResults(template: string, runId: string): string {
  return `${template}?run_id=${encodeURIComponent(runId)}`;
}

const BenchmarkLevelSchema: z.ZodType<BenchmarkLevel> = z.enum([
  "quick",
  "standard",
  "deep",
]);

export const LocalBenchHardwareSchema: z.ZodType<LocalBenchHardwareProfile> =
  z.object({
    gpu_vendor: z.string().min(1),
    gpu_model: z.string().min(1).nullable(),
    vram_mb: z.number().min(0).nullable(),
    ram_mb: z.number().min(0),
    cpu_only: z.boolean(),
  });

// Wire: scan_route returns a bare list of model ids (localbench_routes.py).
export const LocalBenchScanIdsSchema = z.array(z.string().min(1));

// Wire: estimate_route returns BenchEstimate (bench_protocol.py).
export const BenchEstimateWireSchema = z.object({
  level: z.enum(["Quick", "Standard", "Deep"]),
  model_id: z.string().min(1),
  minutes_min: z.number().min(0),
  minutes_max: z.number().min(0),
});

export type BenchEstimateWire = z.infer<typeof BenchEstimateWireSchema>;

// Wire: runs_route answers {"run_id": ...} (localbench_routes.py _post_runs);
// a bare id string is still read.
export const BenchRunIdSchema = z.union([
  z.string().min(1),
  z.object({ run_id: z.string().min(1) }).transform((body) => body.run_id),
]);

// Wire: GET runs/status (localbench_routes.py _get_run_status).
export const BenchRunStatusSchema = z.object({
  run_id: z.string().min(1),
  state: z.enum(["running", "completed", "aborted", "stopped"]),
  reason: z.string(),
  done_cases: z.number().min(0),
  total_cases: z.number().min(0),
});

export type BenchRunStatus = z.infer<typeof BenchRunStatusSchema>;

// Wire: results_route returns BenchResultRow list (bench_protocol.py).
export const LocalBenchResultRowSchema: z.ZodType<LocalBenchResultRow> =
  z.object({
    case_id: z.string().min(1),
    kind: ResultKindSchema,
    model_id: z.string().min(1),
    hardware: LocalBenchHardwareSchema,
    score: z.number().nullable().optional(),
  });

export const LocalBenchResultRowsSchema = z.array(LocalBenchResultRowSchema);

export const LocalBenchRunRequestSchema: z.ZodType<LocalBenchRunRequest> =
  z.object({
    model_id: z.string().min(1),
    level: BenchmarkLevelSchema,
  });

export function toWireRunBody(request: LocalBenchRunRequest): {
  model_id: string;
  level: BenchWireLevel;
} {
  return { model_id: request.model_id, level: toWireLevel(request.level) };
}

export const BENCHMARK_LEVELS: readonly BenchmarkLevel[] = [
  "quick",
  "standard",
  "deep",
];

export const LEVEL_LOCALE_KEYS: Record<BenchmarkLevel, string> = {
  quick: "settings.localbench.levelQuick",
  standard: "settings.localbench.levelStandard",
  deep: "settings.localbench.levelDeep",
};

export const EVIDENCE_LOCALE_KEYS: Record<EvidenceTier, string> = {
  UNKNOWN: "settings.localbench.evidenceUnknown",
  PROXY: "settings.localbench.evidenceProxy",
  MEASURED: "settings.localbench.evidenceMeasured",
};

// Estimated durations at or above this many seconds raise the
// duration warning in the tab.
export const DURATION_WARNING_S = 600;

export function estimateSeconds(estimate: LocalBenchEstimate): number {
  return Math.round(estimate.minutes_max * 60);
}
