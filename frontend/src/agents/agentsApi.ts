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

export const PLACEMENTS = ["LOCAL", "SPLIT", "CLOUD", "UNKNOWN"] as const;
export type Placement = (typeof PLACEMENTS)[number];

export const PlacementSchema: z.ZodType<Placement> = z.enum(PLACEMENTS);

const PLACEMENT_KEYS: Record<Placement, string> = {
  LOCAL: "agents.badge.local",
  SPLIT: "agents.badge.split",
  CLOUD: "agents.badge.cloud",
  UNKNOWN: "shell.common.unknown",
};

export function placementKey(placement: Placement): string {
  return PLACEMENT_KEYS[placement];
}

export function placementLabel(placement: Placement): string {
  return t(PLACEMENT_KEYS[placement]);
}

function readRowPlacement(row: PartRow): Placement | null {
  const placement = (row as unknown as Record<string, unknown>)["placement"];
  if (
    placement === "LOCAL" ||
    placement === "SPLIT" ||
    placement === "CLOUD" ||
    placement === "UNKNOWN"
  ) {
    return placement;
  }
  return null;
}

// Served rows carry the truth in row.placement (LOCAL when the provider
// is a local type, CLOUD otherwise, SPLIT for mixed plan rows). A row
// without it reads UNKNOWN, never a status guess.
export function placementForRow(row: PartRow): Placement {
  return readRowPlacement(row) ?? "UNKNOWN";
}

/** Local loopback provider ids (ollama/lm_studio legs); all others are cloud. */
const LOCAL_PROVIDER_IDS = new Set(["ollama", "lm_studio"]);

export function placementForProviderId(providerId: string): Placement {
  return LOCAL_PROVIDER_IDS.has(providerId) ? "LOCAL" : "CLOUD";
}

export interface ShortRef {
  text: string;
  title?: string;
}

// Shorten served refs for tight rows: drop the fxdevrun: prefix and
// artifact://run/<id>/ to the last part. The full value rides the
// title when shortened; unevidenced values stay a dash.
export function shortenLiveRef(value: unknown): ShortRef {
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
  if (text === "" || text === full) {
    return text === "" ? { text: "–" } : { text };
  }
  return { text, title: full };
}

export type PlacementCounts = Record<Placement, number>;

export function countPlacements(rows: PartRow[]): PlacementCounts {
  const counts: PlacementCounts = { LOCAL: 0, SPLIT: 0, CLOUD: 0, UNKNOWN: 0 };
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
