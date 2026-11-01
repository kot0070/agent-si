// Real-route helpers for the Providers page connect flow.
// Every helper uses the shared client (requestResponse), so the operator
// token travels in the x-ui-session-token header and never in a URL or a
// JSON body. Raw key material travels only in the key-save POST body and
// never reaches a log, a URL, or lasting state. Reads never send a token.

import { ApiError, requestResponse } from "../../api/errors";
import type { SecretRef } from "./types";

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

// GET the provider cards state. Never throws: any failure yields an empty
// list so a background refresh never disturbs the page.
export async function listConnectedProviders(): Promise<string[]> {
  try {
    const response = await requestResponse("/api/v1/providers", {
      method: "GET",
    });
    const data: unknown = await response.json();
    if (!isRecord(data) || !Array.isArray(data["providers"])) {
      return [];
    }
    const ids: string[] = [];
    for (const row of data["providers"] as unknown[]) {
      if (isRecord(row) && typeof row["provider_id"] === "string") {
        ids.push(row["provider_id"] as string);
      }
    }
    return ids;
  } catch {
    return [];
  }
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
