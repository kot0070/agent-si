// Lane A agents area module: zod schemas plus requestJson calls for
// agents-live rows. Served from GET /api/v1/agents/live (K02 NEW side:
// PartRow list with PartStatus).

import { z } from "zod";
import type { PartRow, PartStatus } from "./iface";
import { ENDPOINTS } from "./endpoints";
import { parseOrThrow, requestJson } from "./errors";

export type { PartRow, PartStatus };

export const PART_STATUSES: [PartStatus, ...PartStatus[]] = [
  "QUEUED",
  "RUNNING",
  "RETURNED",
  "ACCEPTED",
  "REJECTED",
  "BLOCKED",
  "HANDOFF",
];

export const PartStatusSchema: z.ZodType<PartStatus> =
  z.enum(PART_STATUSES);

const PartRowBase = z.object({
  agent: z.string().min(1),
  scope: z.string().min(1),
  deliverable: z.string().min(1),
  status: PartStatusSchema,
});

export const PartRowSchema: z.ZodType<PartRow> = PartRowBase;

// FXPANEL append-only live fields: every extra is optional, so rows
// served before the panel upgrade still parse unchanged. provider plus
// placement ride the FXDESIGN4 truth (row.placement LOCAL/SPLIT/CLOUD,
// UNKNOWN when no writer sourced it); last_action carries the step text;
// window carries the model context size when the KB knew it.
export const LiveTokensSchema = z.object({
  input: z.number().int().nullable().optional(),
  output: z.number().int().nullable().optional(),
});

export const LivePlacementSchema = z.enum([
  "LOCAL",
  "SPLIT",
  "CLOUD",
  "UNKNOWN",
]);

export interface LiveRowExtra {
  role?: string;
  model?: string;
  step?: number;
  file?: string;
  cost?: string;
  tokens?: z.infer<typeof LiveTokensSchema>;
  context?: string | number;
  errors?: string[];
  waits?: string[];
  provider?: string;
  placement?: z.infer<typeof LivePlacementSchema>;
  last_action?: string;
  window?: string | number;
}

export type LiveRow = PartRow & LiveRowExtra;

export const LiveRowSchema: z.ZodType<LiveRow> = PartRowBase.extend({
  role: z.string().optional(),
  model: z.string().optional(),
  step: z.number().int().optional(),
  file: z.string().optional(),
  cost: z.string().optional(),
  tokens: LiveTokensSchema.optional(),
  context: z.union([z.string(), z.number().int()]).optional(),
  errors: z.array(z.string()).optional(),
  waits: z.array(z.string()).optional(),
  provider: z.string().optional(),
  placement: LivePlacementSchema.optional(),
  last_action: z.string().optional(),
  window: z.union([z.string(), z.number().int()]).optional(),
});

const AgentsLiveResponseSchema = z.object({
  agents: z.array(LiveRowSchema),
});

export function parseAgentsLive(data: unknown, status = 200): PartRow[] {
  return parseOrThrow(AgentsLiveResponseSchema, data, status).agents;
}

export async function listAgentsLiveRows(): Promise<PartRow[]> {
  return requestJson(
    ENDPOINTS.agentsLive,
    { method: "GET", kind: "read" },
    AgentsLiveResponseSchema,
  ).then((body) => body.agents);
}
