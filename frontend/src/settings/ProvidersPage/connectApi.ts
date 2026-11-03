// Real-route helpers for the Providers page connect flow.
// Every helper uses the shared client (requestResponse), so the operator
// token travels in the x-ui-session-token header and never in a URL or a
// JSON body. Raw key material travels only in the key-save POST body and
// never reaches a log, a URL, or lasting state. Reads never send a token.

import { z } from "zod";
import { ApiError, requestJson, requestResponse } from "../../api/errors";
import { PROVIDER_CATALOG } from "./catalog";
import type { SecretRef } from "./types";

// Local-kind presets and their runtime refs: a local connect attaches the
// preset's base URL as the runtime, so the served local-models rows map
// back to preset ids by exact base-URL match.
const LOCAL_RUNTIME_PRESETS = PROVIDER_CATALOG.filter(
  (preset) => preset.kind === "local",
).map((preset) => ({ id: preset.id, baseUrl: preset.baseUrl }));

export type ConnectRequestBody = {
  preset_id: string;
  model: string;
  key_ref: SecretRef;
};

export function isNetworkFailure(err: unknown): boolean {
  return err instanceof ApiError && err.status === 0;
}

export function failureReason(action: string, err: unknown): string {
  if (err instanceof ApiError) {
    return `${action} failed: ${err.code} (status ${err.status}).`;
  }
  if (err instanceof Error && err.message.length > 0) {
    return `${action} failed: ${err.message}`;
  }
  return `${action} failed.`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

// POST the typed key to the key-save route; answer with the server ref.
// A 2xx answer without a readable ref yields null so the caller falls back
// to the locally built id-only ref (same fields, no key material).
export async function saveKey(
  presetId: string,
  keyValue: string,
): Promise<SecretRef | null> {
  const response = await requestResponse("/api/v1/providers/keys", {
    method: "POST",
    kind: "write",
    body: { preset_id: presetId, key_value: keyValue },
  });
  try {
    const data: unknown = await response.json();
    if (isRecord(data) && isRecord(data["key_ref"])) {
      return data["key_ref"] as SecretRef;
    }
  } catch {
    return null;
  }
  return null;
}

// POST the typed key to the check-only route; never stores.
// 200 means the provider accepted the key with the same preflight the
// save uses (auth/network/other mapped by status). Any failure raises
// ApiError with the served code + plain message, same as saveKey.
export async function checkKey(
  presetId: string,
  keyValue: string,
): Promise<void> {
  await requestResponse("/api/v1/providers/keys/check", {
    method: "POST",
    kind: "write",
    body: { preset_id: presetId, key_value: keyValue },
  });
}

// POST one connect request for a cloud preset, exactly as the connect
// handler reads it: preset id, model, and the id-only key ref.
export async function connectCloud(body: ConnectRequestBody): Promise<void> {
  await requestResponse("/api/v1/providers/connect", {
    method: "POST",
    kind: "write",
    body: {
      preset_id: body.preset_id,
      model: body.model,
      key_ref: body.key_ref,
    },
  });
}

// POST one connect request for a local preset: the handler reads the
// runtime ref plus the header token, nothing else.
export async function connectLocal(runtimeRef: string): Promise<void> {
  await requestResponse("/api/v1/local/connect", {
    method: "POST",
    kind: "write",
    body: { runtime_ref: runtimeRef },
  });
}

// FXFIRST: probe one local preset's base URL without attaching (read-only
// Check half of the local flow). The bench check answers reachability for
// the URL; the local-models read then counts the listed rows. A count
// (possibly zero) means the server runs; null means it does not run or
// is unreadable, so the dialog names that plainly instead of failing on
// a key the local preset never needed.
const BenchCheckSchema = z.object({
  reachable: z.boolean(),
  reason: z.string(),
});

export async function probeLocalModels(baseUrl: string): Promise<number | null> {
  let reachable = false;
  try {
    const check = await requestJson(
      `/api/v1/local/bench/check?endpoint=${encodeURIComponent(baseUrl)}`,
      { method: "GET", kind: "read" },
      BenchCheckSchema,
    );
    reachable = check.reachable;
  } catch {
    return null;
  }
  if (!reachable) {
    return null;
  }
  try {
    const response = await requestResponse("/api/v1/local/models", {
      method: "GET",
    });
    const data: unknown = await response.json();
    if (isRecord(data) && Array.isArray(data["models"])) {
      return (data["models"] as unknown[]).length;
    }
    if (Array.isArray(data)) {
      return (data as unknown[]).length;
    }
  } catch {
    return null;
  }
  return null;
}

// GET the provider cards state. Served state is the truth: the registry
// list (GET /api/v1/providers) plus the attached local runtime (GET
// /api/v1/local/models rows carry the runtime ref in `model`; matched to
// the local preset with the same base URL). Never throws: any failure
// yields an empty list so a background refresh never disturbs the page.
// Local presets attach a runtime instead of registering a provider, so
// without the local half they would flip back to Connect on remount.
export async function listConnectedProviders(): Promise<string[]> {
  const ids: string[] = [];
  try {
    const response = await requestResponse("/api/v1/providers", {
      method: "GET",
    });
    const data: unknown = await response.json();
    if (isRecord(data) && Array.isArray(data["providers"])) {
      for (const row of data["providers"] as unknown[]) {
        if (isRecord(row) && typeof row["provider_id"] === "string") {
          ids.push(row["provider_id"] as string);
        }
      }
    }
  } catch {
    // Registry unreadable: fall through to the local half.
  }
  try {
    const response = await requestResponse("/api/v1/local/models", {
      method: "GET",
    });
    const data: unknown = await response.json();
    const rows: unknown[] = isRecord(data) && Array.isArray(data["models"])
      ? (data["models"] as unknown[])
      : Array.isArray(data)
        ? (data as unknown[])
        : [];
    for (const row of rows) {
      if (!isRecord(row) || typeof row["model"] !== "string") {
        continue;
      }
      const runtime = row["model"] as string;
      for (const preset of LOCAL_RUNTIME_PRESETS) {
        if (runtime === preset.baseUrl && !ids.includes(preset.id)) {
          ids.push(preset.id);
        }
      }
    }
  } catch {
    // No local runtime attached (or no local route): registry list stands.
  }
  return ids;
}

// POST one disconnect request; the card follows a 2xx answer.
export async function disconnectProvider(providerId: string): Promise<void> {
  await requestResponse(
    `/api/v1/providers/${encodeURIComponent(providerId)}/disconnect`,
    {
      method: "POST",
      kind: "write",
      body: {},
    },
  );
}

// GET the leftover-key list for the app namespace. Reads never send a
// token. The route serves names plus dates only, never key material,
// so rows map straight onto id-only refs.
export async function listLeftoverKeys(appPrefix: string): Promise<SecretRef[]> {
  const response = await requestResponse(
    `/api/v1/budget/providers/leftover-keys?app_prefix=${encodeURIComponent(appPrefix)}`,
    {
      method: "GET",
    },
  );
  const data: unknown = await response.json();
  if (!isRecord(data) || !Array.isArray(data["entries"])) {
    return [];
  }
  const refs: SecretRef[] = [];
  for (const row of data["entries"] as unknown[]) {
    if (!isRecord(row) || typeof row["name"] !== "string") {
      continue;
    }
    const name = row["name"] as string;
    const stamp = typeof row["last_used_at"] === "string" ? (row["last_used_at"] as string) : "";
    refs.push({
      secret_id: name,
      provider_id: name.startsWith(appPrefix) ? name.slice(appPrefix.length) : name,
      type: "api-key",
      scope: "providers",
      source: "route",
      created_at: stamp,
      last_rotated_at: null,
    });
  }
  return refs;
}

// POST one leftover-key delete for a user-confirmed entry. The lane
// takes the session token in the body next to the confirm; the header
// token travels through kind write as usual.
export async function deleteLeftoverKey(
  appPrefix: string,
  name: string,
  sessionToken: string,
): Promise<void> {
  await requestResponse("/api/v1/budget/providers/leftover-delete", {
    method: "POST",
    kind: "write",
    body: { app_prefix: appPrefix, name, confirmed: true, session_token: sessionToken },
  });
}
