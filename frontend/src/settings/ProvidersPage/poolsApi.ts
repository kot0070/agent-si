// Save helper for per-role pool bindings.
// PUTs the page's live RolePoolValue to /api/v1/roles/pools with the session
// token as a query param (never in the JSON body: the backend raw-secret
// guard refuses secret-looking body fields).

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

export async function saveRolePool(
  project_id: string,
  role: string,
  value: RolePoolValue,
  options: PoolOption[],
  sessionToken: string,
): Promise<void> {
  const url = `/api/v1/roles/pools?session_token=${encodeURIComponent(sessionToken)}`;
  const response = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildRolePoolBody(project_id, role, value, options)),
  });
  if (!response.ok) {
    throw new Error(`save role pool failed: ${response.status}`);
  }
}
