// Lane A projects area module: zod schemas plus requestJson calls for
// project views (overview, runs, time, routing decisions with
// WHY_THIS_MODEL, reports export) and the underlying project, task,
// ledger, nudge, routing and budget endpoints. Ledger shapes follow the
// K02 NEW side (PackageLedgerRow row-shape, auto_push false); routing and
// budget shapes follow K04 (ReasonText, BudgetState).

import { z } from "zod";
import type {
  ApiClient,
  BudgetState,
  ChatChunk,
  ChatOpen,
  LedgerRow,
  PackageLedgerRow,
  PackageReport,
  ProjectCreate,
  ProjectPatch,
  ProjectRecord,
  ReasonText,
  RoutingAssignment,
  RoutingDecision,
  RoutingEvidenceSnapshot,
  RoutingWhy,
  TaskCreate,
  TaskRecord,
} from "./iface";
import { ENDPOINTS, expandEndpoint, withPackage, withProject } from "./endpoints";
import {
  parseOrThrow,
  requestJson,
  requestVoid,
} from "./errors";
import { readWithSharedRetry } from "./retry";

export type {
  BudgetState,
  LedgerRow,
  PackageLedgerRow,
  PackageReport,
  ProjectCreate,
  ProjectPatch,
  ProjectRecord,
  ReasonText,
  RoutingWhy,
  TaskCreate,
  TaskRecord,
};

export const ProjectRecordSchema: z.ZodType<ProjectRecord> = z.object({
  project_id: z.string().min(1),
  name: z.string().min(1),
  created_at: z.string().min(1),
});

export const ProjectCreateSchema: z.ZodType<ProjectCreate> = z.object({
  name: z.string().min(1),
  folder_ref: z.string().min(1),
});

export const ProjectPatchSchema: z.ZodType<ProjectPatch> = z.object({
  name: z.string().min(1).nullable(),
});

export const TaskRecordSchema: z.ZodType<TaskRecord> = z.object({
  task_id: z.string().min(1),
  project_id: z.string().min(1),
  title: z.string().min(1),
  status: z.string().min(1),
  created_at: z.string().min(1),
});

export const TaskCreateSchema: z.ZodType<TaskCreate> = z.object({
  title: z.string().min(1),
  scope: z.array(z.string()),
});

export const LedgerRowSchema: z.ZodType<LedgerRow> = z.object({
  package_id: z.string().min(1),
  agents: z.number().int().min(0),
  peak_concurrency: z.number().int().min(0),
  wall_time_s: z.number().min(0),
});

export const PackageLedgerRowSchema: z.ZodType<PackageLedgerRow> =
  z.object({
    package_id: z.string().min(1),
    agents: z.number().int().min(0),
    peak_concurrency: z.number().int().min(0),
    wall_time_s: z.number().min(0),
  });

const ServedPackageReportSchema = z.object({
  package_id: z.string().min(1),
  load: PackageLedgerRowSchema,
  nudge: z.string().min(1),
  auto_push: z.literal(false),
});

const LegacyPackageReportSchema = z.object({
  row: PackageLedgerRowSchema,
  nudge: z.string().min(1),
  auto_push: z.literal(false),
});

export const PackageReportSchema: z.ZodType<PackageReport> = z
  .union([ServedPackageReportSchema, LegacyPackageReportSchema])
  .transform((body) =>
    "load" in body
      ? { row: body.load, nudge: body.nudge, auto_push: false as const }
      : body,
  );

const RoutingDecisionSchema: z.ZodType<RoutingDecision> = z.object({
  decision_id: z.string().min(1),
  policy_ref: z.string().min(1),
});

const RoutingAssignmentSchema: z.ZodType<RoutingAssignment> = z.object({
  decision_id: z.string().min(1),
  role: z.string().min(1),
  provider_id: z.string().min(1),
  model: z.string().min(1),
});

const RoutingEvidenceSnapshotSchema: z.ZodType<RoutingEvidenceSnapshot> =
  z.object({
    decision_id: z.string().min(1),
    snapshot_ref: z.string().min(1),
    captured_at: z.string().min(1),
  });

export const ReasonTextSchema: z.ZodType<ReasonText> = z.object({
  task_class: z.string().min(1),
  fit_basis: z.string().min(1),
  price_basis: z.string().min(1),
  quality_basis: z.string().min(1),
  rejected: z.array(z.string()),
});

export const RoutingWhySchema: z.ZodType<RoutingWhy> = z.object({
  decision: RoutingDecisionSchema,
  assignments: z.array(RoutingAssignmentSchema),
  snapshot: RoutingEvidenceSnapshotSchema,
  reason: ReasonTextSchema,
});

const BudgetAmountSchema = z
  .union([z.number().min(0), z.string().regex(/^\d+(\.\d+)?$/)])
  .transform((value) => (typeof value === "string" ? Number(value) : value));

export const BudgetStateSchema: z.ZodType<BudgetState> = z.object({
  project_id: z.string().min(1),
  hard_limit: BudgetAmountSchema,
  spent: BudgetAmountSchema,
  reserved: BudgetAmountSchema,
  currency: z.string().min(1),
});

export const ChatOpenSchema: z.ZodType<ChatOpen> = z.object({
  project_id: z.string().min(1),
  prompt_ref: z.string().min(1),
  stream_id: z.string().min(1),
});

export const ChatChunkSchema: z.ZodType<ChatChunk> = z.object({
  stream_id: z.string().min(1),
  delta: z.string(),
  done: z.boolean(),
});

export const ChatStreamEventSchema = z.object({
  type: z.string().min(1),
  stream_id: z.string().optional(),
  run_id: z.string().optional(),
  text: z.string().optional(),
  code: z.string().optional(),
  message: z.string().optional(),
  reason: z.string().optional(),
  // FXASK2: the held tool's id on approval holds (guard tool_name),
  // plus the task-run hold signal on manager done events. Optional:
  // older events without them parse exactly as before.
  tool_id: z.string().optional(),
  approval_requested: z.boolean().optional(),
});

export type ChatStreamEvent = z.infer<typeof ChatStreamEventSchema>;

export const ChatCancelSchema = z.object({
  stream_id: z.string().min(1),
});

const ProjectsResponseSchema = z.object({
  projects: z.array(ProjectRecordSchema),
});

const ProjectResponseSchema = z.object({
  project: ProjectRecordSchema,
});

const TasksResponseSchema = z.object({
  tasks: z.array(TaskRecordSchema),
});

const TaskResponseSchema = z.object({
  task: TaskRecordSchema,
});

export const TurnTripleSchema = z.object({
  plan: z.string().min(1),
  action: z.string().min(1),
  observation: z.string().min(1),
});

export type TurnTriple = z.infer<typeof TurnTripleSchema>;

export const TaskTurnsSchema = z.object({
  turns: z.array(TurnTripleSchema),
  used: z.number().int().min(0),
  limit: z.number().int().min(0),
});

export type TaskTurns = z.infer<typeof TaskTurnsSchema>;

const LedgerResponseSchema = z.object({
  rows: z.array(LedgerRowSchema),
});

export const BudgetResponseSchema = z.object({
  project_id: z.string().min(1),
  budget: BudgetStateSchema,
});

const OkResponseSchema = z.object({
  ok: z.literal(true),
});

function fetchProjectRecordsOnce(): Promise<ProjectRecord[]> {
  return requestJson(
    ENDPOINTS.projects,
    { method: "GET", kind: "read" },
    ProjectsResponseSchema,
  ).then((body) => body.projects);
}

export async function listProjectRecords(): Promise<ProjectRecord[]> {
  return readWithSharedRetry("projects:list", () =>
    fetchProjectRecordsOnce(),
  );
}

export async function readProjectRecord(
  projectId: string,
): Promise<ProjectRecord> {
  return readWithSharedRetry(`projects:read:${projectId}`, () =>
    requestJson(
      expandEndpoint(ENDPOINTS.projectById, projectId),
      { method: "GET", kind: "read" },
      ProjectResponseSchema,
    ).then((body) => body.project),
  );
}

export async function createProjectRecord(
  body: ProjectCreate,
): Promise<ProjectRecord> {
  return requestJson(
    ENDPOINTS.projects,
    { method: "POST", kind: "write", body },
    ProjectResponseSchema,
  ).then((response) => response.project);
}

export async function updateProjectRecord(
  projectId: string,
  body: ProjectPatch,
): Promise<ProjectRecord> {
  return requestJson(
    expandEndpoint(ENDPOINTS.projectById, projectId),
    { method: "PUT", kind: "write", body },
    ProjectResponseSchema,
  ).then((response) => response.project);
}

export async function deleteProjectRecord(projectId: string): Promise<void> {
  await requestVoid(expandEndpoint(ENDPOINTS.projectById, projectId), {
    method: "DELETE",
    kind: "write",
  });
}

export async function listTaskRecords(
  projectId: string,
): Promise<TaskRecord[]> {
  return readWithSharedRetry(`tasks:list:${projectId}`, () =>
    requestJson(
      withProject(ENDPOINTS.tasks, projectId),
      { method: "GET", kind: "read" },
      TasksResponseSchema,
    ).then((body) => body.tasks),
  );
}

export async function readTaskRecord(taskId: string): Promise<TaskRecord> {
  return readWithSharedRetry(`tasks:read:${taskId}`, () =>
    requestJson(
      expandEndpoint(ENDPOINTS.taskById, taskId),
      { method: "GET", kind: "read" },
      TaskResponseSchema,
    ).then((body) => body.task),
  );
}

export async function readTaskTurns(taskId: string): Promise<TaskTurns> {
  return requestJson(
    `${expandEndpoint(ENDPOINTS.taskById, taskId)}/turns`,
    { method: "GET", kind: "read" },
    TaskTurnsSchema,
  );
}

export async function createTaskRecord(
  projectId: string,
  body: TaskCreate,
): Promise<TaskRecord> {
  return requestJson(
    withProject(ENDPOINTS.tasks, projectId),
    { method: "POST", kind: "write", body },
    TaskResponseSchema,
  ).then((response) => response.task);
}

export async function readLedgerRows(
  projectId: string,
): Promise<LedgerRow[]> {
  return readWithSharedRetry(`ledger:read:${projectId}`, () =>
    requestJson(
      withProject(ENDPOINTS.ledger, projectId),
      { method: "GET", kind: "read" },
      LedgerResponseSchema,
    ).then((body) => body.rows),
  );
}

export async function readPackageReport(
  packageId: string,
): Promise<PackageReport> {
  return readWithSharedRetry(`nudge:read:${packageId}`, () =>
    requestJson(withPackage(ENDPOINTS.nextPackageNudge, packageId), {
      method: "GET",
      kind: "read",
    }, PackageReportSchema),
  );
}

export async function readRoutingWhyDetail(
  decisionId: string,
): Promise<RoutingWhy> {
  return readWithSharedRetry(`routing-why:read:${decisionId}`, () =>
    requestJson(
      expandEndpoint(ENDPOINTS.routingWhy, decisionId),
      { method: "GET", kind: "read" },
      RoutingWhySchema,
    ),
  );
}

export async function readBudgetState(
  projectId: string,
): Promise<BudgetState> {
  return readWithSharedRetry(`budget:read:${projectId}`, () =>
    requestJson(
      withProject(ENDPOINTS.budget, projectId),
      { method: "GET", kind: "read" },
      BudgetResponseSchema,
    ).then((body) => body.budget),
  );
}

export async function cancelChatStreamRequest(
  streamId: string,
): Promise<void> {
  await requestJson(
    ENDPOINTS.chatCancel,
    { method: "POST", kind: "chat", body: { stream_id: streamId } },
    OkResponseSchema,
  );
}

export interface ProjectOverview {
  project: ProjectRecord;
  ledger: LedgerRow[];
  budget: BudgetState;
}

export interface ProjectTimeRow {
  package_id: string;
  wall_time_s: number;
}

export interface WhyThisModel {
  decision_id: string;
  policy_ref: string;
  reason: string;
}

export interface ProjectReportExport {
  format: "agent-si-report/1";
  project: ProjectRecord;
  ledger: LedgerRow[];
  budget: BudgetState;
}

export async function readProjectOverview(
  client: ApiClient,
  projectId: string,
): Promise<ProjectOverview> {
  const [project, ledger, budget] = await Promise.all([
    client.readProject(projectId),
    client.readLedger(projectId),
    client.readBudget(projectId),
  ]);
  return { project, ledger, budget };
}

export async function readProjectRuns(
  client: ApiClient,
  projectId: string,
): Promise<LedgerRow[]> {
  return client.readLedger(projectId);
}

export async function readProjectTime(
  client: ApiClient,
  projectId: string,
): Promise<ProjectTimeRow[]> {
  const rows = await client.readLedger(projectId);
  return rows.map((row) => ({
    package_id: row.package_id,
    wall_time_s: row.wall_time_s,
  }));
}

export async function readWhyThisModel(
  client: ApiClient,
  decisionId: string,
): Promise<WhyThisModel> {
  const why = await client.readRoutingWhy(decisionId);
  return {
    decision_id: why.decision.decision_id,
    policy_ref: why.decision.policy_ref,
    reason: why.reason.fit_basis,
  };
}

export async function exportProjectReport(
  client: ApiClient,
  projectId: string,
): Promise<string> {
  const overview = await readProjectOverview(client, projectId);
  const report: ProjectReportExport = {
    format: "agent-si-report/1",
    project: overview.project,
    ledger: overview.ledger,
    budget: overview.budget,
  };
  return JSON.stringify(report);
}

export function parsePackageReport(data: unknown, status = 200): PackageReport {
  return parseOrThrow(PackageReportSchema, data, status);
}
