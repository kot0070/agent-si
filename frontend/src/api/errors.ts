// Lane A api error contract implementation: ApiError plus request helpers
// plus the UI session token store. Mirrors frontend/src/api/iface.ts.

import { z } from "zod";
import type { ApiErrorBody, ApiErrorCode } from "./iface";

export type { ApiErrorBody, ApiErrorCode };

export class ApiError extends Error {
  code: ApiErrorCode;
  status: number;
  constructor(code: ApiErrorCode, status: number) {
    super(code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

const ERROR_CODES: ReadonlyArray<ApiErrorCode> = [
  "SCOPE_OVERLAP",
  "REJECTED_SCOPE_OVERLAP",
  "GATE_NOT_PASSED",
  "MISSING_INTEGRATION_TASK",
  "INVALID_HIERARCHY_CHAIN",
  "AUDIT_INDEPENDENCE_REJECTED",
  "BUDGET_CAPPED",
  "UNKNOWN_LIMIT_KIND",
  "DELTA_OVER_BOUND",
  "CONTEXT_WRONG_CONTRACT_VERSION",
  "POLICY_CONFLICT",
  "CONTEXT_MISSING",
  "NO_PROFILE_BLOCKED",
  "NO_ELIGIBLE_CANDIDATE",
  "MODALITY_MISMATCH",
  "PROVIDER_UNEVIDENCED",
  "PRICE_UNKNOWN_EXPENSIVE",
  "BUDGET_SOFT_WARN",
  "BUDGET_HARD_BLOCKED",
  "PENDING_RECONCILIATION",
  "DUPLICATE_SETTLEMENT_REFUSED",
  "KB_VALIDATION_FAILED",
  "KB_PROPOSAL_NOT_APPROVED",
  "KEY_SAVE_TIMEOUT",
  "CREDENTIAL_ENTRY_MISSING",
];

export const API_ERROR_CODES: ReadonlyArray<ApiErrorCode> = ERROR_CODES;

function isErrorCode(value: unknown): value is ApiErrorCode {
  return (
    typeof value === "string" &&
    (ERROR_CODES as ReadonlyArray<string>).includes(value)
  );
}

const ErrorBodySchema = z.object({
  code: z.unknown(),
  detail_ref: z.unknown().optional(),
});

function errorFromStatus(code: ApiErrorCode, status: number): ApiError {
  return new ApiError(code, status);
}

export function parseErrorBody(data: unknown, status: number): ApiError {
  const checked = ErrorBodySchema.safeParse(data);
  if (checked.success && isErrorCode(checked.data.code)) {
    return errorFromStatus(checked.data.code, status);
  }
  if (status === 404) {
    return errorFromStatus("CONTEXT_MISSING", status);
  }
  if (status === 0) {
    return errorFromStatus("CONTEXT_MISSING", status);
  }
  return errorFromStatus("CONTEXT_WRONG_CONTRACT_VERSION", status);
}

export function parseOrThrow<T>(
  schema: z.ZodType<T>,
  data: unknown,
  status = 200,
): T {
  const checked = schema.safeParse(data);
  if (checked.success) {
    return checked.data;
  }
  throw errorFromStatus("CONTEXT_WRONG_CONTRACT_VERSION", status);
}

const UI_TOKEN_STORAGE_KEY = "agent-si.ui-token";

const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

let memoryToken: string | null = null;

function readWindowToken(): string | null {
  try {
    if (typeof window !== "undefined") {
      const value = (window as unknown as Record<string, unknown>)[
        WINDOW_TOKEN_KEY
      ];
      if (typeof value === "string" && value.length > 0) {
        return value;
      }
    }
  } catch {
    return null;
  }
  return null;
}

function readStoredToken(): string | null {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      return window.localStorage.getItem(UI_TOKEN_STORAGE_KEY);
    }
  } catch {
    return memoryToken;
  }
  return null;
}

export function getUiToken(): string | null {
  const fromWindow = readWindowToken();
  if (fromWindow !== null) {
    return fromWindow;
  }
  if (memoryToken !== null) {
    return memoryToken;
  }
  return readStoredToken();
}

export function setUiToken(token: string): void {
  memoryToken = token;
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(UI_TOKEN_STORAGE_KEY, token);
    }
  } catch {
    return;
  }
}

export function clearUiToken(): void {
  memoryToken = null;
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.removeItem(UI_TOKEN_STORAGE_KEY);
    }
  } catch {
    return;
  }
}

export type RequestKind = "read" | "write" | "chat";

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  kind?: RequestKind;
  actor?: string;
}

const UI_TOKEN_HEADER = "x-ui-session-token";
const ACTOR_HEADER = "x-actor";
const DEFAULT_ACTOR = "ui";

export async function requestResponse(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const method = options.method ?? "GET";
  const kind: RequestKind = options.kind ?? "read";
  const headers: Record<string, string> = {
    "content-type": "application/json",
  };
  if (kind === "write" || kind === "chat") {
    const token = getUiToken();
    if (token !== null) {
      headers[UI_TOKEN_HEADER] = token;
    }
    headers[ACTOR_HEADER] = options.actor ?? DEFAULT_ACTOR;
  }
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw errorFromStatus("CONTEXT_MISSING", 0);
  }
  if (!response.ok) {
    let data: unknown = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    throw parseErrorBody(data, response.status);
  }
  return response;
}

export async function requestJson<T>(
  path: string,
  options: RequestOptions,
  schema: z.ZodType<T>,
): Promise<T> {
  const response = await requestResponse(path, options);
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  return parseOrThrow(schema, data, response.status);
}

export async function requestVoid(
  path: string,
  options: RequestOptions,
): Promise<void> {
  await requestResponse(path, options);
}

export function apiErrorLocaleKey(code: ApiErrorCode): string {
  switch (code) {
    case "SCOPE_OVERLAP":
      return "api.error.scope_overlap";
    case "REJECTED_SCOPE_OVERLAP":
      return "api.error.rejected_scope_overlap";
    case "GATE_NOT_PASSED":
      return "api.error.gate_not_passed";
    case "MISSING_INTEGRATION_TASK":
      return "api.error.missing_integration_task";
    case "INVALID_HIERARCHY_CHAIN":
      return "api.error.invalid_hierarchy_chain";
    case "AUDIT_INDEPENDENCE_REJECTED":
      return "api.error.audit_independence_rejected";
    case "BUDGET_CAPPED":
      return "api.error.budget_capped";
    case "UNKNOWN_LIMIT_KIND":
      return "api.error.unknown_limit_kind";
    case "DELTA_OVER_BOUND":
      return "api.error.delta_over_bound";
    case "CONTEXT_WRONG_CONTRACT_VERSION":
      return "api.error.context_wrong_contract_version";
    case "POLICY_CONFLICT":
      return "api.error.policy_conflict";
    case "CONTEXT_MISSING":
      return "api.error.context_missing";
    case "NO_PROFILE_BLOCKED":
      return "api.error.no_profile_blocked";
    case "NO_ELIGIBLE_CANDIDATE":
      return "api.error.no_eligible_candidate";
    case "MODALITY_MISMATCH":
      return "api.error.modality_mismatch";
    case "PROVIDER_UNEVIDENCED":
      return "api.error.provider_unevidenced";
    case "PRICE_UNKNOWN_EXPENSIVE":
      return "api.error.price_unknown_expensive";
    case "BUDGET_SOFT_WARN":
      return "api.error.budget_soft_warn";
    case "BUDGET_HARD_BLOCKED":
      return "api.error.budget_hard_blocked";
    case "PENDING_RECONCILIATION":
      return "api.error.pending_reconciliation";
    case "DUPLICATE_SETTLEMENT_REFUSED":
      return "api.error.duplicate_settlement_refused";
    case "KB_VALIDATION_FAILED":
      return "api.error.kb_validation_failed";
    case "KB_PROPOSAL_NOT_APPROVED":
      return "api.error.kb_proposal_not_approved";
    case "KEY_SAVE_TIMEOUT":
      return "api.error.key_save_timeout";
    case "CREDENTIAL_ENTRY_MISSING":
      return "api.error.credential_entry_missing";
  }
}
