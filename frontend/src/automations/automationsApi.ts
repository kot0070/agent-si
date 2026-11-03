// FXAUTO served Automations page API: real routes, fetch only (the UI
// never computes automation state; every row is a served record).
import { z } from "zod";
import { requestJson } from "../api/errors";

const ResultSchema = z.object({
  key: z.string().min(1),
  params: z.record(z.string(), z.unknown()).optional(),
});

export type AutomationResult = z.infer<typeof ResultSchema>;

const RuleSchema = z.object({
  rule_id: z.string().min(1),
  name: z.string(),
  project_id: z.string(),
  when_kind: z.string(),
  when_detail: z.string(),
  if_text: z.string(),
  do: z.string(),
  miss: z.string(),
  enabled: z.boolean(),
  next_run_at: z.string().nullable(),
  last_run_id: z.string().nullable(),
});

export type AutomationRule = z.infer<typeof RuleSchema>;

const RunSchema = z.object({
  run_id: z.string().min(1),
  time: z.string().nullable(),
  rule: z.string(),
  state: z.string(),
  result: ResultSchema,
});

export type AutomationRunRow = z.infer<typeof RunSchema>;

const BuilderDraftSchema = z.object({
  when_kind: z.string(),
  when_detail: z.string(),
  if_text: z.string(),
  do: z.string(),
  miss: z.string(),
});

export type BuilderDraft = z.infer<typeof BuilderDraftSchema>;

const TemplateSchema = z.object({
  template_id: z.string().min(1),
  name: z.string(),
  description: z.string(),
  trigger_key: z.string(),
  action_key: z.string(),
  draft: BuilderDraftSchema,
});

export type AutomationTemplate = z.infer<typeof TemplateSchema>;

const CheckpointSchema = z.object({
  checkpoint_id: z.string().min(1),
  time: z.string(),
  digest: z.string(),
  rule: z.string(),
  run_id: z.string(),
});

export type AutomationCheckpoint = z.infer<typeof CheckpointSchema>;

const ApprovalSchema = z.object({
  approval_id: z.string().min(1),
  rule_id: z.string(),
  rule_name: z.string(),
  project_id: z.string(),
  action: z.string(),
  reason: z.string(),
  state: z.string(),
  created_at: z.number(),
  decided_at: z.number().nullable(),
  run_id: z.string().nullable(),
  result: ResultSchema.nullable(),
});

export type AutomationApproval = z.infer<typeof ApprovalSchema>;

const RulesSchema = z.object({ rules: z.array(RuleSchema) });
const RunsSchema = z.object({ runs: z.array(RunSchema) });
const TemplatesSchema = z.object({ templates: z.array(TemplateSchema) });
const CheckpointsSchema = z.object({
  checkpoints: z.array(CheckpointSchema),
  latest: CheckpointSchema.nullable(),
});
const ApprovalsSchema = z.object({ approvals: z.array(ApprovalSchema) });
const PauseSchema = z.object({
  project_id: z.string(),
  paused: z.boolean(),
});
const RuleEnvelopeSchema = z.object({ rule: RuleSchema });
const FireSchema = z.object({
  run: RunSchema.nullable(),
  result: ResultSchema,
  approval: ApprovalSchema.nullable(),
});
const ApprovalEnvelopeSchema = z.object({ approval: ApprovalSchema });

export async function listAutomationRules(
  projectId: string,
): Promise<AutomationRule[]> {
  const body = await requestJson(
    `/api/v1/automations/rules?project_id=${encodeURIComponent(projectId)}`,
    { method: "GET", kind: "read" },
    RulesSchema,
  );
  return body.rules;
}

export interface RuleDraft {
  name: string;
  when_kind: string;
  when_detail: string;
  if_text: string;
  do: string;
  miss: string;
}

export async function createAutomationRule(
  projectId: string,
  draft: RuleDraft,
): Promise<AutomationRule> {
  const body = await requestJson(
    "/api/v1/automations/rules",
    { method: "POST", kind: "write", body: { project_id: projectId, ...draft } },
    RuleEnvelopeSchema,
  );
  return body.rule;
}

export async function setAutomationRuleEnabled(
  projectId: string,
  ruleId: string,
  enabled: boolean,
): Promise<AutomationRule> {
  const body = await requestJson(
    `/api/v1/automations/rules/${encodeURIComponent(ruleId)}`,
    {
      method: "PUT",
      kind: "write",
      body: { project_id: projectId, enabled },
    },
    RuleEnvelopeSchema,
  );
  return body.rule;
}

export interface FireReceipt {
  run: AutomationRunRow | null;
  result: AutomationResult;
  approval: AutomationApproval | null;
}

export async function runAutomationRuleNow(
  projectId: string,
  ruleId: string,
): Promise<FireReceipt> {
  return requestJson(
    `/api/v1/automations/rules/${encodeURIComponent(ruleId)}/run`,
    { method: "POST", kind: "write", body: { project_id: projectId } },
    FireSchema,
  );
}

export async function listAutomationRuns(
  projectId: string,
): Promise<AutomationRunRow[]> {
  const body = await requestJson(
    `/api/v1/automations/runs?project_id=${encodeURIComponent(projectId)}`,
    { method: "GET", kind: "read" },
    RunsSchema,
  );
  return body.runs;
}

export async function listAutomationTemplates(): Promise<
  AutomationTemplate[]
> {
  const body = await requestJson(
    "/api/v1/automations/templates",
    { method: "GET", kind: "read" },
    TemplatesSchema,
  );
  return body.templates;
}

export interface AutomationCheckpoints {
  checkpoints: AutomationCheckpoint[];
  latest: AutomationCheckpoint | null;
}

export async function listAutomationCheckpoints(
  projectId: string,
): Promise<AutomationCheckpoints> {
  return requestJson(
    `/api/v1/automations/checkpoints?project_id=${encodeURIComponent(projectId)}`,
    { method: "GET", kind: "read" },
    CheckpointsSchema,
  );
}

export async function resumeAutomationCheckpoint(
  projectId: string,
  checkpointId: string,
): Promise<{ checkpoint_id: string; run_id: string; state: string }> {
  return requestJson(
    `/api/v1/automations/checkpoints/${encodeURIComponent(checkpointId)}/resume`,
    { method: "POST", kind: "write", body: { project_id: projectId } },
    z.object({
      checkpoint_id: z.string(),
      run_id: z.string(),
      state: z.string(),
    }),
  );
}

export async function readProjectPause(
  projectId: string,
): Promise<boolean> {
  const body = await requestJson(
    `/api/v1/automations/pause/project?project_id=${encodeURIComponent(projectId)}`,
    { method: "GET", kind: "read" },
    PauseSchema,
  );
  return body.paused;
}

export async function setProjectPause(
  projectId: string,
  paused: boolean,
): Promise<boolean> {
  const body = await requestJson(
    "/api/v1/automations/pause/project",
    { method: "POST", kind: "write", body: { project_id: projectId, paused } },
    PauseSchema,
  );
  return body.paused;
}

export async function readGlobalPause(): Promise<boolean> {
  const body = await requestJson(
    "/api/v1/automations/pause?project_id=",
    { method: "GET", kind: "read" },
    z.boolean(),
  );
  return body;
}

export async function setGlobalPause(
  paused: boolean,
  reason: string,
): Promise<void> {
  await requestJson(
    "/api/v1/automations/pause",
    { method: "POST", kind: "write", body: { paused, reason } },
    z.unknown(),
  );
}

export async function listAutomationApprovals(
  projectId: string,
): Promise<AutomationApproval[]> {
  const body = await requestJson(
    `/api/v1/automations/approvals?project_id=${encodeURIComponent(projectId)}`,
    { method: "GET", kind: "read" },
    ApprovalsSchema,
  );
  return body.approvals;
}

export async function decideAutomationApproval(
  projectId: string,
  approvalId: string,
  approved: boolean,
): Promise<AutomationApproval> {
  const body = await requestJson(
    `/api/v1/automations/approvals/${encodeURIComponent(approvalId)}`,
    {
      method: "POST",
      kind: "write",
      body: { project_id: projectId, approved },
    },
    ApprovalEnvelopeSchema,
  );
  return body.approval;
}
