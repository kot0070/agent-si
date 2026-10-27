// Lane A agents area module: placement badges plus status_human mapping for
// the live agents panel. HTTP stays in wave-1 src/api/agentsApi.ts (single
// fetch truth, frozen); this module re-exports its schemas and adds the area
// view helpers the panel mounts. Served rows arrive from
// GET /api/v1/agents/live (K02 section 4 served PartRow list).

import { z } from "zod";
import type { PartRow, PartStatus } from "../api/iface";
import {
  PartRowSchema,
  PartStatusSchema,
  parseAgentsLive,
} from "../api/agentsApi";
import { t } from "../locale/index";
import type { SupportedLocale } from "../locale/index";

export type { PartRow, PartStatus };
export { PartRowSchema, PartStatusSchema, parseAgentsLive };

export const PLACEMENTS = ["LOCAL", "SPLIT", "CLOUD"] as const;
export type Placement = (typeof PLACEMENTS)[number];

export const PlacementSchema: z.ZodType<Placement> = z.enum(PLACEMENTS);

const PLACEMENT_KEYS: Record<Placement, string> = {
  LOCAL: "agents.badge.local",
  SPLIT: "agents.badge.split",
  CLOUD: "agents.badge.cloud",
};

export function placementKey(placement: Placement): string {
  return PLACEMENT_KEYS[placement];
}

export function placementLabel(placement: Placement): string {
  return t(PLACEMENT_KEYS[placement]);
}

// The served PartRow carries no placement field, so the panel buckets rows
// with this documented rule: executed or completed parts read LOCAL, queued
// or parked parts read CLOUD, cross-boundary parts read SPLIT. Counts per
// bucket are exact row counts, never estimates.
export function placementForRow(row: PartRow): Placement {
  switch (row.status) {
    case "RUNNING":
    case "RETURNED":
    case "ACCEPTED":
      return "LOCAL";
    case "QUEUED":
    case "BLOCKED":
      return "CLOUD";
    case "REJECTED":
    case "HANDOFF":
      return "SPLIT";
  }
}

export type PlacementCounts = Record<Placement, number>;

export function countPlacements(rows: PartRow[]): PlacementCounts {
  const counts: PlacementCounts = { LOCAL: 0, SPLIT: 0, CLOUD: 0 };
  for (const row of rows) {
    counts[placementForRow(row)] += 1;
  }
  return counts;
}

const STATUS_KEYS: Record<PartStatus, string> = {
  QUEUED: "tasks.status.queued",
  RUNNING: "tasks.status.running",
  RETURNED: "tasks.status.returned",
  ACCEPTED: "tasks.status.accepted",
  REJECTED: "tasks.status.rejected",
  BLOCKED: "tasks.status.blocked",
  HANDOFF: "tasks.status.handoff",
};

export function statusHumanKey(status: PartStatus): string {
  return STATUS_KEYS[status];
}

export const StatusHumanPairSchema = z.object({
  en: z.string().min(1),
  uk: z.string().min(1),
});
export type StatusHumanPair = z.infer<typeof StatusHumanPairSchema>;

export const StatusHumanSchema = z.union([
  StatusHumanPairSchema,
  z.string().min(1),
]);

// status_human arrives as a uk/en pair or as a status code the frontend maps
// through tasks.status.*. A served pair wins; otherwise the code maps.
export function resolveStatusHuman(
  value: unknown,
  status: PartStatus,
  locale: SupportedLocale,
): string {
  const pair = StatusHumanPairSchema.safeParse(value);
  if (pair.success) {
    return pair.data[locale];
  }
  return t(STATUS_KEYS[status]);
}
