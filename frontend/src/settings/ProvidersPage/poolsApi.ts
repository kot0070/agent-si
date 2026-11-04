// Save helper for per-role pool bindings.
// PUTs the page's live RolePoolValue to /api/v1/roles/pools with the UI
// session token in the x-ui-session-token header via the shared client
// (never in the URL query or the JSON body: the backend never accepts a
// query token and refuses secret-looking body fields).

import { requestResponse, requestVoid } from "../../api/errors";
import { defaultPoolResolver } from "./RolePoolPicker";
import type { PoolOption, RolePoolValue } from "./RolePoolPicker";

export type RolePoolMemberBody = {
  provider_id: string;
  model: string;
};

export type RolePoolSaveBody = {
  project_id: string;
  role: string;
  mode: string;
  provider?: string;
  model?: string;
  pool: RolePoolMemberBody[];
  strategy: string;
};

export function buildRolePoolBody(
  project_id: string,
  role: string,
  value: RolePoolValue,
  options: PoolOption[],
): RolePoolSaveBody {
  const resolve = defaultPoolResolver(options);
  if (value.mode === "PINNED") {
    const resolved = value.pinnedKey === "" ? undefined : resolve(value.pinnedKey);
    return {
      project_id,
      role,
      mode: "PINNED",
      ...(resolved ? { provider: resolved.provider, model: resolved.model } : {}),
      pool: [],
      strategy: value.strategy,
    };
  }
  if (value.mode === "pool") {
    const pool: RolePoolMemberBody[] = [];
    for (const key of value.poolKeys) {
      const resolved = resolve(key);
      if (resolved) {
        pool.push({ provider_id: resolved.provider, model: resolved.model });
      }
    }
    return { project_id, role, mode: "pool", pool, strategy: value.strategy };
  }
  return { project_id, role, mode: "AUTO", pool: [], strategy: value.strategy };
}

export const AGENT_ROLES = ["director", "manager", "worker", "auditor"] as const;

export type RolePoolReadRow = { role: string; mode: string | null; model: string | null };

export async function readRolePools(project_id: string): Promise<RolePoolReadRow[]> {
  const response = await requestResponse(
    `/api/v1/roles/pools?project_id=${encodeURIComponent(project_id)}`,
    { method: "GET" },
  );
  const data = (await response.json()) as { roles?: RolePoolReadRow[] };
  return Array.isArray(data.roles) ? data.roles : [];
}

export async function saveRolePool(
  project_id: string,
  role: string,
  value: RolePoolValue,
  options: PoolOption[],
): Promise<void> {
  await requestVoid("/api/v1/roles/pools", {
    method: "PUT",
    kind: "write",
    body: buildRolePoolBody(project_id, role, value, options),
  });
}
