// OC-K07 (ARCH-720): agent contract defaults are confirmed before use.
// A role profile is usable only when its contract shape is complete:
// a known mode, plus provider and model for PINNED. Binding and version
// fall back to the shipped defaults (DEFAULT / 1, mirroring the backend
// DefaultManagerProfile) and are always reported, never silently empty.
// The result carries the effective defaults when the shape is complete
// (defaults null when the mode itself is unknown); every label the bar
// renders reuses existing settings.roleProfile keys, so no locale
// addition is needed.

import type { RoleMode, RoleModelProfile } from "./index";

export const DEFAULT_CONTRACT_BINDING = "DEFAULT";

export const DEFAULT_CONTRACT_VERSION = 1;

export interface AgentContractDefaults {
  mode: RoleMode;
  provider?: string;
  model?: string;
  binding: string;
  version: number;
}

export interface ContractConfirmResult {
  confirmed: boolean;
  missing: string[];
  defaults: AgentContractDefaults | null;
}

export interface ContractConfirmInput {
  mode?: unknown;
  provider?: unknown;
  model?: unknown;
  binding?: unknown;
  version?: unknown;
}

function isRoleMode(value: unknown): value is RoleMode {
  return value === "PINNED" || value === "pool" || value === "AUTO";
}

function nonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function confirmAgentContractDefaults(
  input: ContractConfirmInput,
): ContractConfirmResult {
  const missing: string[] = [];
  if (!isRoleMode(input.mode)) {
    missing.push("mode");
  }
  if (input.mode === "PINNED") {
    if (!nonEmpty(input.provider)) {
      missing.push("provider");
    }
    if (!nonEmpty(input.model)) {
      missing.push("model");
    }
  }
  if (missing.length > 0) {
    return { confirmed: false, missing, defaults: null };
  }
  const mode = input.mode as RoleMode;
  const defaults: AgentContractDefaults = {
    mode,
    binding:
      nonEmpty(input.binding) && (input.binding as string).trim().length > 0
        ? (input.binding as string).trim()
        : DEFAULT_CONTRACT_BINDING,
    version:
      typeof input.version === "number" &&
      Number.isInteger(input.version) &&
      (input.version as number) > 0
        ? (input.version as number)
        : DEFAULT_CONTRACT_VERSION,
  };
  if (nonEmpty(input.provider)) {
    defaults.provider = (input.provider as string).trim();
  }
  if (nonEmpty(input.model)) {
    defaults.model = (input.model as string).trim();
  }
  return { confirmed: true, missing, defaults };
}

export function confirmStoredProfile(
  profile: RoleModelProfile | undefined,
): ContractConfirmResult {
  if (profile === undefined) {
    return confirmAgentContractDefaults({});
  }
  return confirmAgentContractDefaults({
    mode: profile.mode,
    provider: profile.provider,
    model: profile.model,
  });
}
