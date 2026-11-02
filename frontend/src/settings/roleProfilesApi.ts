// K07HTTP1 role-profile server path: GET plus PUT over the role route
// through the REAL HttpApiClient fetch boundary (no test double, no
// localStorage here). Reads use kind "read" (no token headers); the PUT
// uses kind "write" (header-only token plus actor, never a URL token).
// Backend shapes mirror src/agent_si/backend/pools_routes.py:96
// (_profile_payload), :343 (get_role read handler) and :359 (set_role
// write handler); the endpoint const lives only in this file, never in
// the frozen ENDPOINTS table.

import { z } from "zod";
import { ApiError, requestJson } from "../api/errors";
import type { RoleModelProfile, RoleProfileMap } from "./index";

export const ROLE_PROFILE_ENDPOINT = "/api/v1/routing/role";

export const ROLE_PROFILE_ROLES = [
  "director",
  "manager",
  "worker",
  "auditor",
  "watcher",
] as const;

export type RoleProfileRole = (typeof ROLE_PROFILE_ROLES)[number];

const RoleModeSchema = z.enum(["PINNED", "pool", "AUTO"]);

// Served per-role payload: pools_routes.py:96 (_profile_payload) always
// carries every key, with null provider/model when the mode holds none.
export const ServerRoleProfileSchema = z.object({
  role: z.string().min(1),
  project_id: z.string().min(1),
  mode: RoleModeSchema,
  provider: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
  binding: z.string().optional(),
  version: z.number().optional(),
});

export type ServerRoleProfile = z.infer<typeof ServerRoleProfileSchema>;

// GET /api/v1/routing/role answers {profile} (pools_routes.py:343);
// a missing row answers 404, which reads as undefined, not a throw.
export const RoleProfileGetResponseSchema = z.object({
  profile: ServerRoleProfileSchema,
  binding: z.unknown().optional(),
});

export type RoleProfileGetResponse = z.infer<
  typeof RoleProfileGetResponseSchema
>;

// PUT /api/v1/routing/role takes the profile fields in the JSON body and
// answers {ok, profile} (pools_routes.py:359); unknown roles answer 400
// and are never stored.
export const RoleProfilePutBodySchema = z.object({
  project_id: z.string().min(1),
  role: z.string().min(1),
  mode: RoleModeSchema,
  provider: z.string().optional(),
  model: z.string().optional(),
});

export type RoleProfilePutBody = z.infer<typeof RoleProfilePutBodySchema>;

export const RoleProfilePutResponseSchema = z.object({
  ok: z.literal(true),
  profile: ServerRoleProfileSchema,
});

export type RoleProfilePutResponse = z.infer<
  typeof RoleProfilePutResponseSchema
>;

function toRoleModelProfile(profile: ServerRoleProfile): RoleModelProfile {
  const next: RoleModelProfile = { mode: profile.mode };
  if (typeof profile.provider === "string" && profile.provider.length > 0) {
    next.provider = profile.provider;
  }
  if (typeof profile.model === "string" && profile.model.length > 0) {
    next.model = profile.model;
  }
  return next;
}

function putBody(
  projectId: string,
  role: string,
  profile: RoleModelProfile,
): RoleProfilePutBody {
  const body: RoleProfilePutBody = {
    project_id: projectId,
    role,
    mode: profile.mode,
  };
  if (profile.provider !== undefined) {
    body.provider = profile.provider;
  }
  if (profile.model !== undefined) {
    body.model = profile.model;
  }
  return body;
}

export async function readRoleProfileFromServer(
  projectId: string,
  role: string,
): Promise<RoleModelProfile | undefined> {
  const path =
    `${ROLE_PROFILE_ENDPOINT}?project_id=${encodeURIComponent(projectId)}` +
    `&role=${encodeURIComponent(role)}`;
  try {
    const body = await requestJson(
      path,
      { method: "GET", kind: "read" },
      RoleProfileGetResponseSchema,
    );
    return toRoleModelProfile(body.profile);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return undefined;
    }
    throw error;
  }
}

export async function readRoleProfilesFromServer(
  projectId: string,
): Promise<RoleProfileMap> {
  const map: RoleProfileMap = {};
  for (const role of ROLE_PROFILE_ROLES) {
    const profile = await readRoleProfileFromServer(projectId, role);
    if (profile !== undefined) {
      map[role] = profile;
    }
  }
  return map;
}

export async function writeRoleProfileToServer(
  projectId: string,
  role: string,
  profile: RoleModelProfile,
): Promise<RoleModelProfile> {
  const checked = RoleProfilePutBodySchema.parse(
    putBody(projectId, role, profile),
  );
  const answered = await requestJson(
    ROLE_PROFILE_ENDPOINT,
    { method: "PUT", kind: "write", body: checked },
    RoleProfilePutResponseSchema,
  );
  return toRoleModelProfile(answered.profile);
}

// FXSAVED item 2: full saved pool state for one role (profile plus the
// binding the same GET carries). Mode/pinned come from the profile;
// pool members plus strategy come from the binding. A never-saved role
// answers 404 and reads as undefined (the picker keeps AUTO); any other
// failure also reads as undefined so the page never breaks on load.
export type RolePoolSavedMember = {
  provider: string;
  model: string;
};

export type RolePoolSaved = {
  mode: RoleModelProfile["mode"];
  provider?: string;
  model?: string;
  pool: RolePoolSavedMember[];
  strategy?: string;
};

const RolePoolBindingSchema = z
  .object({
    strategy: z.string().optional(),
    members: z
      .array(
        z
          .object({ provider: z.string(), model: z.string() })
          .passthrough(),
      )
      .optional(),
  })
  .passthrough();

const RolePoolStateResponseSchema = z.object({
  profile: ServerRoleProfileSchema,
  binding: RolePoolBindingSchema.optional(),
});

export async function readRolePoolState(
  projectId: string,
  role: string,
): Promise<RolePoolSaved | undefined> {
  const path =
    `${ROLE_PROFILE_ENDPOINT}?project_id=${encodeURIComponent(projectId)}` +
    `&role=${encodeURIComponent(role)}`;
  try {
    const body = await requestJson(
      path,
      { method: "GET", kind: "read" },
      RolePoolStateResponseSchema,
    );
    const profile = toRoleModelProfile(body.profile);
    const members: RolePoolSavedMember[] = [];
    for (const member of body.binding?.members ?? []) {
      members.push({ provider: member.provider, model: member.model });
    }
    return {
      mode: profile.mode,
      ...(profile.provider !== undefined
        ? { provider: profile.provider }
        : {}),
      ...(profile.model !== undefined ? { model: profile.model } : {}),
      pool: members,
      ...(typeof body.binding?.strategy === "string"
        ? { strategy: body.binding.strategy }
        : {}),
    };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return undefined;
    }
    return undefined;
  }
}
