// Shared types for the ProvidersPage lane.
// No secrets, no credentials, no machine paths in this file.

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
