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

export type RowsByPlacement = Record<Placement, PartRow[]>;

// Buckets served agent rows with the documented placement rule from
// agentsApi; bucket sizes are exact row counts.
export function splitRowsByPlacement(rows: PartRow[]): RowsByPlacement {
  const out: RowsByPlacement = { LOCAL: [], SPLIT: [], CLOUD: [] };
  for (const row of rows) {
    out[placementForRow(row)].push(row);
  }
  return out;
}
