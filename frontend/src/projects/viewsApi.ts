// FXVIEWS project extended-views helpers: every row below traces to a
// served record cell; anything unserved reads UNKNOWN, never invented.
// Pure builders (humanRunRef, formatServedDate, dedupeLiveRows,
// buildTokenRows, buildRunRecords, changedFiles) plus the optional
// analytics-telemetry read (same served route the telemetry summary uses,
// ?project_id= form). Own module: ProjectView and the project tabs import
// from here, never the reverse.

import { z } from "zod";
import { ENDPOINTS, withProject } from "../api/endpoints";
import { requestJson } from "../api/errors";
import type {
  BudgetState,
  LedgerRow,
  PartRow,
  TaskRecord,
} from "../api/iface";
import { placementForRow } from "../agents/agentsApi";
import type { Placement } from "../agents/agentsApi";
import type { SupportedLocale } from "../locale/index";
import { formatDate, formatScreenTime, pluralUnit, t } from "../locale/index";

export interface ShortRef {
  text: string;
  title?: string;
}

// Human short ref for served run/package/deliverable ids. Strips the
// fxdevrun:<id>: prefix and artifact://run/<id>/ paths to the last segment;
// the full value rides the title when shortened. Plain ids pass through.
export function humanRunRef(value: unknown): ShortRef {
  if (value === undefined || value === null || value === "") {
    return { text: "–" };
  }
  const full = String(value);
  let text = full;
  let stripped = false;
  if (text.startsWith("fxdevrun:")) {
    const parts = text.split(":");
    text = parts[parts.length - 1] ?? text;
    stripped = true;
  }
  const artifact = /^artifact:\/\/run\/[^/]+\/(.+)$/.exec(text);
  if (artifact !== null) {
    text = artifact[1] ?? text;
    stripped = true;
  }
  if (stripped) {
    const segments = text.split("/");
    text = segments[segments.length - 1] ?? text;
  }
  if (text === "") {
    return { text: "–" };
  }
  if (text === full) {
    return { text };
  }
  return { text, title: full };
}

// Served ISO stamps render as locale dates; stamps that do not parse (test
// ids such as t-9) render raw so provenance assertions keep working.
// Served ISO stamps render as locale dates. Only strings that look like
// a real stamp (leading YYYY-MM-DD or a pure epoch number) are parsed:
// short test ids such as t-9 would otherwise parse as stray dates and
// provenance assertions would lose their served refs.
const STAMP_LIKE = /^\d{4}-\d{2}-\d{2}|^\d{10,}$/;

export function formatServedDate(
  value: string,
  locale: SupportedLocale,
): string {
  if (!STAMP_LIKE.test(value.trim())) {
    return value;
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return formatDate(new Date(parsed), locale);
}

export interface LiveExtras {
  role?: string;
  model?: string;
  provider?: string;
  tokensTotal: number | null;
  costText: string | null;
  file?: string;
  errors: string[];
}

type LiveRowLoose = PartRow & {
  role?: unknown;
  model?: unknown;
  provider?: unknown;
  tokens?: unknown;
  cost?: unknown;
  file?: unknown;
  errors?: unknown;
  context?: unknown;
};

function readText(value: unknown): string | undefined {
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  return undefined;
}

function readTokensTotal(value: unknown): number | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const record = value as Record<string, unknown>;
  const input = record.input;
  const output = record.output;
  const hasInput = typeof input === "number" && Number.isFinite(input);
  const hasOutput = typeof output === "number" && Number.isFinite(output);
  if (!hasInput && !hasOutput) {
    return null;
  }
  return (hasInput ? (input as number) : 0) + (hasOutput ? (output as number) : 0);
}

// Every extra is optional: rows served before the extras upgrade parse
// unchanged, and absent cells read null (UNKNOWN in the view).
export function readLiveExtras(row: PartRow): LiveExtras {
  const loose = row as LiveRowLoose;
  const tokensTotal = readTokensTotal(loose.tokens);
  const costRaw = readText(loose.cost);
  const errorsRaw = loose.errors;
  const errors =
    Array.isArray(errorsRaw)
      ? errorsRaw.map((item) => String(item)).filter((item) => item !== "")
      : [];
  return {
    role: readText(loose.role),
    model: readText(loose.model),
    provider: readText(loose.provider),
    tokensTotal,
    costText: costRaw ?? null,
    file: readText(loose.file),
    errors,
  };
}

// FXFACTS F2: the run id a live row belongs to, read from the served
// deliverable ("artifact://run/<run_id>/...") or context
// ("artifact:run/<run_id>/...") the engine writes. Rows without either
// (older register rows) read null: unattributed, never guessed.
export function liveRowRunId(row: PartRow): string | null {
  const loose = row as LiveRowLoose;
  const deliverable =
    typeof row.deliverable === "string" ? row.deliverable : "";
  const context =
    typeof loose.context === "string" ? loose.context : "";
  const fromDeliverable =
    /^artifact:\/\/run\/([^/]+)\//.exec(deliverable)?.[1] ?? null;
  if (fromDeliverable !== null) {
    return fromDeliverable;
  }
  const fromContext =
    /^artifact:run\/([^/]+)\//.exec(context)?.[1] ?? null;
  return fromContext;
}

// FXFACTS F2: rows of the latest run only. Runs ride newest-first
// (FXCARDS C1), so runs[0] is the latest; rows parsing to an older run
// id drop out, so an earlier failed run never marks current state.
// Unattributed rows stay: only evidence filters, never a guess. With no
// served runs the live rows pass through unchanged.
export function latestRunRows(
  live: PartRow[],
  runs: Array<{ run_id: string }> | null,
): PartRow[] {
  if (runs === null || runs.length === 0) {
    return live;
  }
  const latest = runs[0]?.run_id;
  if (typeof latest !== "string" || latest === "") {
    return live;
  }
  return live.filter((row) => {
    const runId = liveRowRunId(row);
    return runId === null || runId === latest;
  });
}

// FXFACTS F3: served role names read through the locale, never raw.
// Unknown role strings read null (UNKNOWN in the view).
export function translateRoleName(role: unknown): string | null {
  if (typeof role !== "string") {
    return null;
  }
  const key = role.toLowerCase();
  if (
    key === "director" ||
    key === "manager" ||
    key === "worker" ||
    key === "auditor" ||
    key === "watcher"
  ) {
    return t(`providers.role.${key}`);
  }
  return null;
}

export interface DedupedRow {
  agent: string;
  role?: string;
  model?: string;
  provider?: string;
  placement: Placement;
  status: PartRow["status"];
  attempts: number;
  tokensTotal: number | null;
  costText: string | null;
  files: string[];
  scopes: string[];
  errors: string[];
}

// FXTABS T6: attempts of one agent fold into ONE row with an attempt
// count and the agent's last status. A terminal end (BLOCKED, REJECTED,
// RETURNED, ACCEPTED) wins over a stale RUNNING attempt served beside
// it, so at run end nothing stays Running; otherwise the last served
// status wins. Tokens add up, files unite.
function statusRank(status: PartRow["status"]): number {
  switch (status) {
    case "BLOCKED":
    case "REJECTED":
    case "RETURNED":
    case "ACCEPTED":
      return 3;
    case "RUNNING":
      return 2;
    default:
      return 1;
  }
}

export function dedupeLiveRows(rows: PartRow[]): DedupedRow[] {
  const byKey = new Map<string, DedupedRow>();
  for (const row of rows) {
    const extras = readLiveExtras(row);
    const key = row.agent;
    const seen = byKey.get(key);
    if (seen === undefined) {
      byKey.set(key, {
        agent: row.agent,
        role: extras.role,
        model: extras.model,
        provider: extras.provider,
        placement: placementForRow(row),
        status: row.status,
        attempts: 1,
        tokensTotal: extras.tokensTotal,
        costText: extras.costText,
        files: extras.file === undefined ? [] : [extras.file],
        scopes: [row.scope],
        errors: [...extras.errors],
      });
      continue;
    }
    seen.attempts += 1;
    const nextRank = statusRank(row.status);
    const seenRank = statusRank(seen.status);
    if (nextRank > seenRank || nextRank === seenRank) {
      seen.status = row.status;
      if (extras.role !== undefined) {
        seen.role = extras.role;
      }
      if (extras.model !== undefined) {
        seen.model = extras.model;
      }
      if (extras.provider !== undefined) {
        seen.provider = extras.provider;
      }
      seen.placement = placementForRow(row);
    }
    if (extras.tokensTotal !== null) {
      seen.tokensTotal = (seen.tokensTotal ?? 0) + extras.tokensTotal;
    }
    if (seen.costText === null) {
      seen.costText = extras.costText;
    }
    if (extras.file !== undefined && !seen.files.includes(extras.file)) {
      seen.files.push(extras.file);
    }
    for (const error of extras.errors) {
      if (!seen.errors.includes(error)) {
        seen.errors.push(error);
      }
    }
    if (!seen.scopes.includes(row.scope)) {
      seen.scopes.push(row.scope);
    }
  }
  return [...byKey.values()];
}

// Finished work says finished: RETURNED and ACCEPTED are terminal pass
// states, so the tabs label them with projectView.finished instead of the
// raw code. All other statuses keep their tasks.status.* label.
export function isFinishedStatus(status: PartRow["status"]): boolean {
  return status === "RETURNED" || status === "ACCEPTED";
}

const TelemetryCountSchema = z.union([z.number().int(), z.null()]);

const TelemetryMoneySchema = z.union([z.number(), z.literal("UNAVAILABLE")]);

const TelemetryModelRowSchema = z.object({
  model: z.string(),
  calls: z.number().int(),
  tokens: TelemetryMoneySchema,
  cost: TelemetryMoneySchema,
});

export type TelemetryModelRow = z.infer<typeof TelemetryModelRowSchema>;

const TelemetryRoleRowSchema = z.object({
  role: z.string(),
  model: z.string(),
  calls: z.number().int(),
  tokens: TelemetryMoneySchema,
  cost: TelemetryMoneySchema,
});

export type TelemetryRoleRow = z.infer<typeof TelemetryRoleRowSchema>;

const TelemetrySummarySchema = z.object({
  project: z
    .object({ tasks: TelemetryCountSchema, audits: TelemetryCountSchema })
    .optional(),
  models: z.array(TelemetryModelRowSchema).optional(),
  providers: z
    .array(
      z.object({
        provider: z.string(),
        calls: z.number().int(),
        tokens: TelemetryMoneySchema,
        cost: TelemetryMoneySchema,
      }),
    )
    .optional(),
  roles: z.array(TelemetryRoleRowSchema).optional(),
  unavailable: z.array(z.string()).optional(),
});

export type TelemetrySummary = z.infer<typeof TelemetrySummarySchema>;

export const TELEMETRY_PATH = "/api/v1/analytics/telemetry";

// Optional enrichment: a missing/unparseable telemetry doc reads null and
// the tabs stay honestly empty, never an error panel over missing extras.
export async function readTelemetrySummary(
  projectId?: string,
): Promise<TelemetrySummary | null> {
  const path =
    projectId === undefined || projectId === ""
      ? TELEMETRY_PATH
      : `${TELEMETRY_PATH}?project_id=${encodeURIComponent(projectId)}`;
  try {
    return await requestJson(
      path,
      { method: "GET", kind: "read" },
      TelemetrySummarySchema,
    );
  } catch {
    return null;
  }
}

export interface TokenRow {
  role?: string;
  model?: string;
  tokens: number | null;
  calls: number | null;
}

// Per-role+model token facts. When the telemetry doc serves per-role
// rows (recorded at record time, same events as the model aggregates),
// role rows carry the served numbers and "Other calls" holds only calls
// with no role (role ""). Live rows plus model rows are the legacy gap
// fill for stores without roles. No served cell anywhere reads null
// (UNKNOWN in the view), never zero invented as measured.
export function buildTokenRows(
  live: PartRow[],
  telemetry: TelemetrySummary | null,
): TokenRow[] {
  const roles = telemetry?.roles ?? [];
  // FXTABS (b): role rows count only when at least one serves a number.
  // All-UNKNOWN roles beside a counted model aggregate used to render as
  // "Unknown" rows plus a counted "Other calls" row; now the legacy path
  // below gives the one honest total instead.
  if (
    roles.length > 0 &&
    roles.some((row) => typeof row.tokens === "number")
  ) {
    return roles
      .map((row) => ({
        role: row.role === "" ? undefined : row.role,
        model: row.model,
        tokens: typeof row.tokens === "number" ? row.tokens : null,
        calls: row.calls,
      }))
      .filter(
        (row) =>
          row.role !== undefined ||
          row.model !== undefined ||
          row.tokens !== null ||
          row.calls !== null,
      );
  }
  const byKey = new Map<string, TokenRow>();
  for (const row of dedupeLiveRows(live)) {
    const key = `${row.role ?? ""}\u0000${row.model ?? ""}`;
    const seen = byKey.get(key);
    if (seen === undefined) {
      byKey.set(key, {
        role: row.role,
        model: row.model,
        tokens: row.tokensTotal,
        calls: null,
      });
      continue;
    }
    if (row.tokensTotal !== null) {
      seen.tokens = (seen.tokens ?? 0) + row.tokensTotal;
    }
  }
  const models = telemetry?.models ?? [];
  for (const model of models) {
    const key = `\u0000${model.model}`;
    const tokens = typeof model.tokens === "number" ? model.tokens : null;
    const seen = byKey.get(key);
    if (seen === undefined) {
      byKey.set(key, {
        role: undefined,
        model: model.model,
        tokens,
        calls: model.calls,
      });
      continue;
    }
    if (seen.tokens === null) {
      seen.tokens = tokens;
    }
    if (seen.calls === null) {
      seen.calls = model.calls;
    }
  }
  // XOR: rows that carry no served cell at all (no role, no model, no
  // tokens, no calls) never render as noise rows; the tab then reads as
  // one honest empty state instead.
  return [...byKey.values()].filter(
    (row) =>
      row.role !== undefined ||
      row.model !== undefined ||
      row.tokens !== null ||
      row.calls !== null,
  );
}

export function sumTokenRows(rows: TokenRow[]): number | null {
  let total = 0;
  let served = false;
  for (const row of rows) {
    if (row.tokens !== null) {
      total += row.tokens;
      served = true;
    }
  }
  return served ? total : null;
}

export interface RunRecord {
  packageId: string;
  agents: number;
  peak: number;
  wallTimeS: number;
  verdict: string;
  files: string[];
}

// Engine record read from served rows only: ledger cells for the numbers,
// served live file extras for changed files. Tasks and budget ride along
// when the caller already serves them; start/end stamps and verdicts have
// no served cell on these rows, so they read UNKNOWN, never guessed.
export function buildRunRecords(input: {
  ledger: LedgerRow[];
  live: PartRow[];
  tasks?: TaskRecord[];
  budget?: BudgetState;
}): RunRecord[] {
  const files = changedFiles(input.live);
  return input.ledger.map((row) => ({
    packageId: row.package_id,
    agents: row.agents,
    peak: row.peak_concurrency,
    wallTimeS: row.wall_time_s,
    verdict: "UNKNOWN",
    files,
  }));
}

// Distinct served file extras across live rows: the changed-files list the
// Reports tab reads. Empty when no row serves a file cell.
export function changedFiles(live: PartRow[]): string[] {
  const out: string[] = [];
  for (const row of live) {
    const file = readLiveExtras(row).file;
    if (file !== undefined && !out.includes(file)) {
      out.push(file);
    }
  }
  return out;
}

// FXVIEWS3: devrun run rows served on the same runs ledger route (app.py
// runs_ledger "runs" key, FXVIEWS2 additions-only). The ledger row path
// keeps reading rows only; readRuns reads the runs key. Every cell is
// served: run id, start/end stamps, parts, verdicts, tokens, cost or
// UNKNOWN, files, success, summary.

const DevrunPartSchema = z.object({
  part_id: z.string(),
  verdict: z.union([z.string(), z.null()]).optional(),
  attempts: z.number().int().optional(),
  reason: z.string().optional(),
});

export type DevrunPart = z.infer<typeof DevrunPartSchema>;

const DevrunRunSchema = z.object({
  run_id: z.string(),
  folder: z.string().optional(),
  start: z.string(),
  end: z.string(),
  // FXR2B: short per-run title (first 80 chars of the user task),
  // served on the runs row so the UI shows it instead of a hash.
  title: z.string().optional(),
  parts: z.array(DevrunPartSchema),
  verdicts: z.record(z.string(), z.union([z.string(), z.null()])),
  tokens: z.union([z.number().int(), z.literal("UNKNOWN")]),
  cost: z.union([z.string(), z.literal("UNKNOWN")]),
  files: z.array(z.string()),
  success: z.boolean(),
  summary: z.string(),
  manager_why: z.string().optional(),
  manager_count: z.number().int().optional(),
  managers: z
    .array(
      z.object({
        manager_id: z.string(),
        goal: z.string().optional(),
        parts: z.array(z.string()),
      }),
    )
    .optional(),
});

export type DevrunRun = z.infer<typeof DevrunRunSchema>;

const RunsLedgerResponseSchema = z.object({
  rows: z.array(z.unknown()).optional(),
  runs: z.array(DevrunRunSchema).optional(),
});

// Same route the row readers use; a missing/unparseable runs doc reads []
// (honestly empty tabs) so one failing enrichment never hides siblings.
export async function readRuns(projectId: string): Promise<DevrunRun[]> {
  try {
    return await requestJson(
      withProject(ENDPOINTS.ledger, projectId),
      { method: "GET", kind: "read" },
      RunsLedgerResponseSchema,
    ).then((body) => body.runs ?? []);
  } catch {
    return [];
  }
}

// Wall seconds from served start/end stamps; UNKNOWN or inverted stamps
// read null (UNKNOWN in the view), never a guessed duration.
export function runWallS(run: DevrunRun): number | null {
  const start = Date.parse(run.start);
  const end = Date.parse(run.end);
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return null;
  }
  return Math.round((end - start) / 1000);
}

export function sumRunsWall(runs: DevrunRun[]): number | null {
  let total = 0;
  let served = false;
  for (const run of runs) {
    const wall = runWallS(run);
    if (wall !== null) {
      total += wall;
      served = true;
    }
  }
  return served ? total : null;
}

// Served stamps render through the one screen-time helper; UNKNOWN or
// unparseable stamps stay raw so provenance assertions keep working.
export function formatRunMoment(
  value: string,
  locale: SupportedLocale,
): string {
  if (value === "UNKNOWN" || !STAMP_LIKE.test(value.trim())) {
    return value;
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return formatScreenTime(new Date(parsed), locale);
}

// Human wall-clock units from served seconds (rounded), in the active
// locale (FXFACTS F4: uk reads хв and с, never raw min/s). Served cells
// only; null stays null.
export function humanDuration(totalS: number | null): string | null {
  if (totalS === null) {
    return null;
  }
  const total = Math.max(0, Math.round(totalS));
  const second = pluralUnit("projectView.time.second", total);
  if (total < 60) {
    return `${total} ${second}`;
  }
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  const minute = pluralUnit("projectView.time.minute", minutes);
  if (minutes < 60) {
    return rest === 0
      ? `${minutes} ${minute}`
      : `${minutes} ${minute} ${rest} ${pluralUnit("projectView.time.second", rest)}`;
  }
  const hours = Math.floor(minutes / 60);
  const restMin = minutes % 60;
  const hour = pluralUnit("projectView.time.hour", hours);
  return restMin === 0
    ? `${hours} ${hour}`
    : `${hours} ${hour} ${restMin} ${pluralUnit("projectView.time.minute", restMin)}`;
}

// Plain run status from the served cells: any FAIL part forces "failed"
// even when a legacy success cell says true, so `done` never sits beside
// a FAIL verdict on any surface (served run row, header, final card).
// One shared map: every surface reads this word for the same run.
export const RUN_WORD_DONE = "done" as const;
export const RUN_WORD_FAILED = "failed" as const;

export type RunWord = typeof RUN_WORD_DONE | typeof RUN_WORD_FAILED;

export function runStatusWord(input: {
  success: boolean;
  parts: Array<{ verdict?: string | null; part_id?: string; reason?: string }>;
  verdicts?: Record<string, string | null>;
}): RunWord {
  const seen: Array<string | null | undefined> = [
    ...input.parts.map((part) => part.verdict),
    ...Object.values(input.verdicts ?? {}),
  ];
  for (const verdict of seen) {
    if (verdict !== undefined && verdict !== null && verdict !== "" && verdict !== "PASS") {
      return RUN_WORD_FAILED;
    }
  }
  if (input.parts.length > 0) {
    const allPass =
      input.parts.length > 0 &&
      input.parts.every((part) => part.verdict === "PASS");
    if (!allPass) {
      return RUN_WORD_FAILED;
    }
  }
  return input.success ? RUN_WORD_DONE : RUN_WORD_FAILED;
}

// Plain run status from the served cells, in the active locale
// (FXTABS U5b: no raw English "done"/"failed" in the uk build).
export function runStatusText(run: DevrunRun): string {
  return runStatusWord(run) === RUN_WORD_DONE
    ? t("projectView.runs.done")
    : t("projectView.runs.failed");
}

// FXTABS U5b: served part verdicts read as localized status words in the
// tabs that judge rows (audits, errors). The runs-tab card keeps the raw
// served code as provenance. Parts that never started read "not run".
export function partVerdictText(part: {
  verdict?: string | null;
  attempts?: number;
}): string {
  const verdict = part.verdict ?? null;
  if (verdict === "PASS") {
    return t("projectView.runs.verdictPass");
  }
  if (verdict === "PENDING") {
    return t("projectView.runs.verdictPending");
  }
  if (verdict !== null && verdict !== "") {
    return verdict;
  }
  return (part.attempts ?? 0) > 0
    ? t("shell.common.unknown")
    : t("projectView.runs.notRun");
}
