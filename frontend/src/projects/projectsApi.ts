// Lane A projects area module: view names plus pure view models for the
// project extended views. HTTP stays in wave-1 src/api/projectsApi.ts
// (single fetch truth, frozen); this module re-exports its schemas and the
// client-driven view helpers the views mount, and adds pure builders whose
// every number traces to a served record row. Ledger shapes follow the K02
// NEW side (PackageLedgerRow row-shape, auto_push false); routing and budget
// shapes follow K04 (ReasonText, BudgetState).

import type {
  BudgetState,
  LedgerRow,
  PackageLedgerRow,
  PackageReport,
  PartRow,
  ProjectCreate,
  ProjectPatch,
  ProjectRecord,
  ReasonText,
  RoutingWhy,
  TaskCreate,
  TaskRecord,
} from "../api/iface";
import {
  BudgetStateSchema,
  ChatCancelSchema,
  ChatChunkSchema,
  ChatOpenSchema,
  LedgerRowSchema,
  PackageLedgerRowSchema,
  PackageReportSchema,
  ProjectCreateSchema,
  ProjectPatchSchema,
  ProjectRecordSchema,
  ReasonTextSchema,
  RoutingWhySchema,
  TaskCreateSchema,
  TaskRecordSchema,
  exportProjectReport,
  parsePackageReport,
  readProjectOverview,
  readProjectRuns,
  readProjectTime,
  readWhyThisModel,
} from "../api/projectsApi";
import { z } from "zod";
import { requestJson } from "../api/errors";
import { ENDPOINTS } from "../api/endpoints";
import { placementForRow } from "../agents/agentsApi";
import type { Placement } from "../agents/agentsApi";

export type {
  BudgetState,
  LedgerRow,
  PackageLedgerRow,
  PackageReport,
  PartRow,
  ProjectCreate,
  ProjectPatch,
  ProjectRecord,
  ReasonText,
  RoutingWhy,
  TaskCreate,
  TaskRecord,
};
export {
  BudgetStateSchema,
  ChatCancelSchema,
  ChatChunkSchema,
  ChatOpenSchema,
  LedgerRowSchema,
  PackageLedgerRowSchema,
  PackageReportSchema,
  ProjectCreateSchema,
  ProjectPatchSchema,
  ProjectRecordSchema,
  ReasonTextSchema,
  RoutingWhySchema,
  TaskCreateSchema,
  TaskRecordSchema,
  exportProjectReport,
  parsePackageReport,
  readProjectOverview,
  readProjectRuns,
  readProjectTime,
  readWhyThisModel,
};

export const PROJECT_VIEWS = [
  "overview",
  "tasks",
  "runs",
  "time",
  "ai-usage",
  "tokens",
  "cost",
  "local-ai",
  "cloud-ai",
  "models",
  "routing-decisions",
  "audits",
  "errors",
  "reports",
  "tests",
] as const;
export type ProjectViewName = (typeof PROJECT_VIEWS)[number];

const VIEW_TITLE_KEYS: Record<ProjectViewName, string> = {
  overview: "projects.overview.title",
  tasks: "tasks.list.title",
  runs: "projects.runs.title",
  time: "projects.time.title",
  "ai-usage": "projects.ai_usage.title",
  tokens: "projects.tokens.title",
  cost: "projects.cost.title",
  "local-ai": "projects.local_ai.title",
  "cloud-ai": "projects.cloud_ai.title",
  models: "projects.models.title",
  "routing-decisions": "projects.routing.title",
  audits: "projects.audits.title",
  errors: "projects.errors.title",
  reports: "projects.reports.title",
  // FXLOCALE2: `projects.tests.title` landed, so the tests view uses it.
  tests: "projects.tests.title",
};

export function projectViewTitleKey(view: ProjectViewName): string {
  return VIEW_TITLE_KEYS[view];
}

export function projectMenuTestId(view: ProjectViewName): string {
  return `project-menu-${view}`;
}

export interface LedgerSums {
  packages: number;
  agents: number;
  peak: number;
  wall: number;
}

// Every sum below adds served LedgerRow cells only.
export function sumLedger(rows: LedgerRow[]): LedgerSums {
  let agents = 0;
  let wall = 0;
  let peak = 0;
  for (const row of rows) {
    agents += row.agents;
    wall += row.wall_time_s;
    if (row.peak_concurrency > peak) {
      peak = row.peak_concurrency;
    }
  }
  return { packages: rows.length, agents, peak, wall };
}

// K04 budget rule: remaining is derived, never stored truth.
export function remainingBudget(budget: BudgetState): number {
  return budget.hard_limit - budget.spent - budget.reserved;
}

// M-P4-159 context card: remaining context of the served budget total. Both
// numbers trace to the served BudgetState (hard_limit stored, remaining
// derived by the K04 rule); the view labels them with the serving route so
// no number is ever invented.
export interface ContextUsage {
  remaining: number;
  total: number;
}

export function contextUsage(budget: BudgetState): ContextUsage {
  return { remaining: remainingBudget(budget), total: budget.hard_limit };
}

export const CONTEXT_SOURCE = ENDPOINTS.budget;

// Age in whole days from the stored created_at stamp; null when the stamp
// does not parse, so the view shows an empty state instead of a guess.
export function computeAgeDays(
  createdAt: string,
  nowMs: number,
): number | null {
  const started = Date.parse(createdAt);
  if (Number.isNaN(started)) {
    return null;
  }
  const days = Math.floor((nowMs - started) / 86400000);
  return days < 0 ? 0 : days;
}

export interface ReportNarrativeInput {
  tasks: TaskRecord[];
  ledger: LedgerRow[];
  budget: BudgetState;
}

// Derived narrative lines computed from measured rows only; the Reports view
// labels them with projects.derived.label and never lets them override the
// measured rows.
export function buildReportNarrative(input: ReportNarrativeInput): string[] {
  const sums = sumLedger(input.ledger);
  return [
    `packages=${sums.packages} tasks=${input.tasks.length}`,
    `agents=${sums.agents} peak=${sums.peak} wall_s=${sums.wall}`,
    `spent=${input.budget.spent} reserved=${input.budget.reserved} remaining=${remainingBudget(input.budget)}`,
  ];
}

export interface DerivedAllocation {
  packageId: string;
  wallTimeS: number;
  derivedCost: number;
  currency: string;
  labelKey: string;
}

// ARCH-683: extended allocations beyond the named menus are a derived
// display split from authoritative telemetry, never measured truth. The
// served ledger carries wall_time_s per package but no per-package cost,
// so the measured budget spent is split across packages proportionally
// by served wall time. Every row carries the DERIVED label key; an empty
// ledger yields no rows (never invented zeros presented as measured);
// a zero wall total yields zero allocations, still labeled derived.
// Sum of derivedCost equals budget.spent up to float rounding.
export const DERIVED_SPLIT_LABEL_KEY = "projects.derived.label";

export function buildDerivedSplit(input: {
  ledger: LedgerRow[];
  budget: BudgetState;
}): DerivedAllocation[] {
  if (input.ledger.length === 0) {
    return [];
  }
  let totalWall = 0;
  for (const row of input.ledger) {
    totalWall += row.wall_time_s;
  }
  return input.ledger.map((row) => ({
    packageId: row.package_id,
    wallTimeS: row.wall_time_s,
    derivedCost:
      totalWall > 0
        ? (input.budget.spent * row.wall_time_s) / totalWall
        : 0,
    currency: input.budget.currency,
    labelKey: DERIVED_SPLIT_LABEL_KEY,
  }));
}

export type RowsByPlacement = Record<Placement, PartRow[]>;

// Buckets served agent rows with the placement truth from agentsApi;
// rows without a sourced placement read UNKNOWN, never a status guess.
export function splitRowsByPlacement(rows: PartRow[]): RowsByPlacement {
  const out: RowsByPlacement = { LOCAL: [], SPLIT: [], CLOUD: [], UNKNOWN: [] };
  for (const row of rows) {
    out[placementForRow(row)].push(row);
  }
  return out;
}

// FXTESTSUI merged teststage wire (backend read-only, never edited here).
// Paths and served shapes mirror the merged backend lanes verbatim:
// GET+POST /api/v1/teststage/local-tests plus GET plans/latest,
// runs/latest, tests-view and result-output (read_routes.py k03ver2 +
// k03fxtests1). No frozen api/* file is touched; session tokens travel in
// the x-ui-session-token header via kind "write", never the URL or body.
export const TESTS_LOCAL_TESTS_PATH = "/api/v1/teststage/local-tests";
export const TESTS_PLANS_LATEST_PATH = "/api/v1/teststage/plans/latest";
export const TESTS_RUNS_LATEST_PATH = "/api/v1/teststage/runs/latest";
export const TESTS_VIEW_PATH = "/api/v1/teststage/tests-view";
export const TEST_RESULT_OUTPUT_PATH = "/api/v1/teststage/result-output";

const LocalTestsStateSchema = z.object({
  project_id: z.string().min(1),
  enabled: z.boolean(),
});

export type LocalTestsState = z.infer<typeof LocalTestsStateSchema>;

const LocalTestsSavedSchema = z.object({
  project_id: z.string().min(1),
  enabled: z.boolean(),
  updated_at: z.string(),
});

export type LocalTestsSaved = z.infer<typeof LocalTestsSavedSchema>;

const LatestPlanSchema = z.object({
  project_id: z.string().min(1),
  plan_id: z.string().min(1),
});

export type LatestPlan = z.infer<typeof LatestPlanSchema>;

const LatestRunSchema = z.object({
  project_id: z.string().min(1),
  plan_id: z.string().min(1),
  run_id: z.string().min(1),
});

export type LatestRun = z.infer<typeof LatestRunSchema>;

// Served per-test row: test_id, status and output_ref always; kind and
// reason ride along only when the serving lane records them (record_result
// requires a reason for BLOCKED rows). Absent kind reads as UNKNOWN;
// absent reason renders no reason line (never invented).
const TestStatusRowSchema = z.object({
  test_id: z.string().min(1),
  status: z.string().min(1),
  output_ref: z.string().nullable(),
  kind: z.string().optional(),
  reason: z.string().nullable().optional(),
});

export type TestStatusRow = z.infer<typeof TestStatusRowSchema>;

const TestsViewSchema = z.object({
  plan_id: z.string().min(1),
  run_id: z.string().min(1),
  active: z.number().int().min(0),
  passed: z.number().int().min(0),
  remaining: z.number().int().min(0),
  rows: z.array(TestStatusRowSchema),
  settings_controls: z.array(z.string()),
});

export type TestsView = z.infer<typeof TestsViewSchema>;

const ResultOutputSchema = z.object({
  ref: z.string().min(1),
  project_id: z.string().min(1),
  output: z.string(),
  size: z.number().min(0),
});

export type ResultOutput = z.infer<typeof ResultOutputSchema>;

export function localTestsPath(projectId: string): string {
  return `${TESTS_LOCAL_TESTS_PATH}?project_id=${encodeURIComponent(projectId)}`;
}

export function latestPlanPath(projectId: string): string {
  return `${TESTS_PLANS_LATEST_PATH}?project_id=${encodeURIComponent(projectId)}`;
}

export function latestRunPath(projectId: string): string {
  return `${TESTS_RUNS_LATEST_PATH}?project_id=${encodeURIComponent(projectId)}`;
}

export function testsViewPath(planId: string, runId: string): string {
  return `${TESTS_VIEW_PATH}?plan_id=${encodeURIComponent(planId)}&run_id=${encodeURIComponent(runId)}`;
}

export function resultOutputPath(ref: string): string {
  return `${TEST_RESULT_OUTPUT_PATH}?ref=${encodeURIComponent(ref)}`;
}

// Switch default is the GET answer; the single POST below carries the
// session token via kind "write" and the caller reads back after it.
export async function readLocalTests(
  projectId: string,
): Promise<LocalTestsState> {
  return requestJson(
    localTestsPath(projectId),
    { method: "GET", kind: "read" },
    LocalTestsStateSchema,
  );
}

export async function saveLocalTests(
  projectId: string,
  enabled: boolean,
): Promise<LocalTestsSaved> {
  return requestJson(
    TESTS_LOCAL_TESTS_PATH,
    {
      method: "POST",
      kind: "write",
      body: { project_id: projectId, enabled },
    },
    LocalTestsSavedSchema,
  );
}

export async function readLatestPlan(projectId: string): Promise<LatestPlan> {
  return requestJson(
    latestPlanPath(projectId),
    { method: "GET", kind: "read" },
    LatestPlanSchema,
  );
}

export async function readLatestRun(projectId: string): Promise<LatestRun> {
  return requestJson(
    latestRunPath(projectId),
    { method: "GET", kind: "read" },
    LatestRunSchema,
  );
}

export async function readTestsView(
  planId: string,
  runId: string,
): Promise<TestsView> {
  return requestJson(
    testsViewPath(planId, runId),
    { method: "GET", kind: "read" },
    TestsViewSchema,
  );
}

export async function readResultOutput(ref: string): Promise<ResultOutput> {
  return requestJson(
    resultOutputPath(ref),
    { method: "GET", kind: "read" },
    ResultOutputSchema,
  );
}

// Execution kinds (CODE/AI/HUMAN) in plain words; an unserved kind is
// UNKNOWN (no record), never guessed.
export function testKindLabel(kind: string | undefined): string {
  if (kind === "CODE") {
    return "code";
  }
  if (kind === "AI") {
    return "AI";
  }
  if (kind === "HUMAN") {
    return "human";
  }
  if (kind !== undefined && kind !== "") {
    return kind;
  }
  return "unknown";
}
