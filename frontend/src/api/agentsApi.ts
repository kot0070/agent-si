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

export const PartRowSchema: z.ZodType<PartRow> = z.object({
  agent: z.string().min(1),
  scope: z.string().min(1),
  deliverable: z.string().min(1),
  status: PartStatusSchema,
});

const AgentsLiveResponseSchema = z.object({
  agents: z.array(PartRowSchema),
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
