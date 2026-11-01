// R349A project step-limits API helper: real GET/PUT over
// /api/v1/projects/{project_id}/step-limits plus the read-only budget line
// over the EXISTING GET /api/v1/budget?project_id= real shape
// ({project_id, budget:{hard_limit,spent,reserved,currency}} as strings).
// Session tokens travel in the x-ui-session-token header (never the URL)
// via requestResponse kind "write". No frozen api/* file is touched.

import { z } from "zod";
import { requestJson } from "../api/errors";

const StepLimitsSchema = z.object({
  project_id: z.string().min(1),
  task_max_steps: z.number().int(),
  chat_max_steps: z.number().int(),
});

export type StepLimits = z.infer<typeof StepLimitsSchema>;

const StepLimitsSavedSchema = StepLimitsSchema.extend({
  decision_ref: z.string().min(1),
});

export type StepLimitsSaved = z.infer<typeof StepLimitsSavedSchema>;

// Real GET /api/v1/budget shape: string amounts, not the client BudgetState.
// provider_spend_caps and provider_spending ride along when the gate
// knows them; both stay optional so older payloads still parse.
const ProviderSpendingSchema = z.object({
  spent: z.string(),
  reserved: z.string(),
  cap: z.string().nullable(),
});

const BudgetLineSchema = z.object({
  project_id: z.string().min(1),
  budget: z.object({
    hard_limit: z.string(),
    spent: z.string(),
    reserved: z.string(),
    currency: z.string(),
    provider_spend_caps: z.record(z.string(), z.string()).optional(),
    provider_spending: z
      .record(z.string(), ProviderSpendingSchema)
      .optional(),
  }),
});

export type BudgetLine = z.infer<typeof BudgetLineSchema>;

const LimitsSavedSchema = z.object({
  project_id: z.string().min(1),
  provider_spend_caps: z.record(z.string(), z.string()),
});

export type LimitsSaved = z.infer<typeof LimitsSavedSchema>;

export function stepLimitsPath(projectId: string): string {
  return `/api/v1/projects/${encodeURIComponent(projectId)}/step-limits`;
}

export function budgetLinePath(projectId: string): string {
  return `/api/v1/budget?project_id=${encodeURIComponent(projectId)}`;
}

export function budgetLimitsPath(): string {
  return "/api/v1/budget/limits";
}

export async function readStepLimits(
  projectId: string,
): Promise<StepLimits> {
  return requestJson(
    stepLimitsPath(projectId),
    { method: "GET", kind: "read" },
    StepLimitsSchema,
  );
}

export async function readBudgetLine(
  projectId: string,
): Promise<BudgetLine> {
  return requestJson(
    budgetLinePath(projectId),
    { method: "GET", kind: "read" },
    BudgetLineSchema,
  );
}

export async function saveBudgetLimits(
  projectId: string,
  providerSpendCaps: Record<string, string>,
): Promise<LimitsSaved> {
  return requestJson(
    budgetLimitsPath(),
    {
      method: "POST",
      kind: "write",
      body: { project_id: projectId, provider_spend_caps: providerSpendCaps },
    },
    LimitsSavedSchema,
  );
}

export async function saveStepLimits(
  projectId: string,
  taskMaxSteps: number,
  chatMaxSteps: number,
): Promise<StepLimitsSaved> {
  return requestJson(
    stepLimitsPath(projectId),
    {
      method: "PUT",
      kind: "write",
      body: { task_max_steps: taskMaxSteps, chat_max_steps: chatMaxSteps },
    },
    StepLimitsSavedSchema,
  );
}
