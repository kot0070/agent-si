// Shared types for the ProvidersPage lane.
// No secrets, no credentials, no machine paths in this file.

import { t } from "../../locale/index";

export const APP_NAMESPACE_PREFIX = "agent_si/provider/";

export const AUTO_SENTINEL = "AUTO";

export type RoleKey = "director" | "manager" | "worker" | "auditor" | "watcher";

export const ROLE_KEYS: RoleKey[] = ["director", "manager", "worker", "auditor", "watcher"];

export const ROLE_LABELS: Record<RoleKey, string> = {
  director: "Director",
  manager: "Manager",
  worker: "Worker",
  auditor: "Auditor",
  watcher: "Watcher",
};

// Locale-facing role name for rendered UI. Unknown roles fall back to the
// raw role key so a new role never throws a missing-locale-key error.
export function roleLabel(role: string): string {
  try {
    return t(`providers.role.${role}`);
  } catch {
    return role;
  }
}

export type ProviderKind = "cloud" | "compatible" | "local";

export type ModelOption = {
  id: string;
  label: string;
};

export type ProviderPreset = {
  id: string;
  label: string;
  kind: ProviderKind;
  group: string;
  baseUrl: string;
  keyHint: string;
  keyStartsWith: string;
  models: ModelOption[];
  /** Per-provider cap line (e.g. "0.30/1.50 caps"); absent when unreported. */
  caps?: string;
};

export type ProviderState = {
  presetId: string;
  connected: boolean;
  enabledModels: string[];
};

export type SecretRef = {
  secret_id: string;
  provider_id: string;
  type: string;
  scope: string;
  source: string;
  created_at: string;
  last_rotated_at: string | null;
};

export type RoleAssignment = Record<RoleKey, string>;
