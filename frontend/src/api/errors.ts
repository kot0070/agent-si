// Lane A api error contract implementation: ApiError plus request helpers
// plus the UI session token store. Mirrors frontend/src/api/iface.ts.

import { z } from "zod";
import type { ApiErrorBody, ApiErrorCode } from "./iface";

export type { ApiErrorBody, ApiErrorCode };

export class ApiError extends Error {
  code: ApiErrorCode;
  status: number;
  // FXASK2: optional served detail carried on the error (addition only:
  // existing two-arg constructions are unchanged). The chat/task-run
  // approval hold carries the held tool's id here from the approval
  // event's tool_id field.
  readonly details?: ApiErrorDetails;
  constructor(code: ApiErrorCode, status: number, details?: ApiErrorDetails) {
    super(code);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    if (details !== undefined) {
      this.details = details;
    }
  }
  get toolId(): string | undefined {
    return this.details?.toolId;
  }
}

export interface ApiErrorDetails {
  toolId?: string;
  // FXCONNECT-REFUSED: the served plain text for a refused key or an
  // unreachable provider (the message travels in the error body next
  // to the code; the UI names well-known failures, never raw codes).
  message?: string;
  // FXSTORE: the routed provider id on secret-store terminals (ids
  // only, never the value) so the UI names the missing key plainly.
  providerId?: string;
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
  "PROJECT_FOLDER_IN_USE",
  "PROJECT_FOLDER_MISSING",
  "NO_PROVIDER_BOUND",
  "GENERIC_ERROR",
  "SECRET_VALUE_MISSING",
  "CREDENTIAL_STORE_UNREADABLE",
];

export const API_ERROR_CODES: ReadonlyArray<ApiErrorCode> = ERROR_CODES;

export function isErrorCode(value: unknown): value is ApiErrorCode {
  return (
    typeof value === "string" &&
    (ERROR_CODES as ReadonlyArray<string>).includes(value)
  );
}

const ErrorBodySchema = z.object({
  code: z.unknown().optional(),
  detail: z.unknown().optional(),
  detail_ref: z.unknown().optional(),
  // R1: the backend serves plain reasons as {"error": "..."}; keep the
  // field so the reason survives (the extractor below already reads it).
  error: z.unknown().optional(),
});

function errorFromStatus(code: ApiErrorCode, status: number): ApiError {
  return new ApiError(code, status);
}

export function apiErrorFromCode(code: unknown, status: number): ApiError {
  if (typeof code === "string" && code.length > 0) {
    return errorFromStatus(code as ApiErrorCode, status);
  }
  // FXANSWER S1: an error body with no usable code is a generic failure,
  // never the contract-version sentence (that code reads only when the
  // server actually sent it).
  return errorFromStatus("GENERIC_ERROR", status);
}

function missingWhenNotFound(code: string, status: number): ApiError | null {
  // A 404/offline transport state reads as not-found even when the body
  // carries the generic fallback code; explicit server codes otherwise
  // stay preserved (frozen wire contract).
  if (
    (status === 404 || status === 0) &&
    code === "CONTEXT_WRONG_CONTRACT_VERSION"
  ) {
    return errorFromStatus("CONTEXT_MISSING", status);
  }
  return null;
}

export function parseErrorBody(data: unknown, status: number): ApiError {
  const checked = ErrorBodySchema.safeParse(data);
  // Served plain text next to the code rides the details so the UI shows
  // a plain sentence instead of a fallback contract code. FastAPI serves
  // plain HTTPException details as {"detail": "..."}; legacy bodies use
  // "message" or "error". Only the sentence travels along: every code
  // below is exactly what the old paths returned.
  let details: ApiErrorDetails | undefined;
  try {
    const record = (checked.success ? checked.data : data) as
      | { message?: unknown; detail?: unknown; error?: unknown }
      | null;
    if (typeof record === "object" && record !== null) {
      for (const field of ["message", "detail", "error"] as const) {
        const value = record[field];
        if (typeof value === "string" && value.length > 0) {
          details = { message: value };
          break;
        }
      }
      // R10/R11: FastAPI serves reason dicts as {"detail": {"code",
      // "message"}}; the nested message rides along the same way.
      if (details === undefined) {
        const nested = record.detail as { message?: unknown } | null;
        if (
          typeof nested === "object" &&
          nested !== null &&
          typeof nested.message === "string" &&
          nested.message.length > 0
        ) {
          details = { message: nested.message };
        }
      }
    }
  } catch {
    details = undefined;
  }
  const wrap = (err: ApiError): ApiError => {
    if (details === undefined || err.details?.message !== undefined) {
      return err;
    }
    return new ApiError(err.code, err.status, { ...err.details, message: details.message });
  };
  if (checked.success) {
    const raw = (checked.data as { code?: unknown }).code;
    if (typeof raw === "string" && raw.length > 0) {
      const missing = missingWhenNotFound(raw, status);
      if (missing !== null) {
        return wrap(missing);
      }
      const err = apiErrorFromCode(raw, status);
      return details === undefined ? err
        : new ApiError(err.code, err.status, details);
    }
    const detail = (checked.data as { detail?: unknown }).detail;
    if (typeof detail === "object" && detail !== null) {
      const nested = (detail as { code?: unknown }).code;
      if (typeof nested === "string" && nested.length > 0) {
        const missing = missingWhenNotFound(nested, status);
        if (missing !== null) {
          return wrap(missing);
        }
        const err = apiErrorFromCode(nested, status);
        return details === undefined ? err
          : new ApiError(err.code, err.status, details);
      }
    }
  }
  if (status === 404) {
    return wrap(errorFromStatus("CONTEXT_MISSING", status));
  }
  if (status === 0) {
    return wrap(errorFromStatus("CONTEXT_MISSING", status));
  }
  // FXANSWER S1: same generic fallback (see apiErrorFromCode).
  return wrap(errorFromStatus("GENERIC_ERROR", status));
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
  // FXANSWER S1: an unparsable body is a generic failure, never the
  // contract-version sentence.
  throw errorFromStatus("GENERIC_ERROR", status);
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

// FXEXEUI: accept the per-launch UI session token from the address once
// at module load; the token moves into the token store and leaves the
// address, while every other query param stays in place.
try {
  if (typeof window !== "undefined" && typeof window.location !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const queryToken = params.get("token");
    if (queryToken !== null && queryToken.length > 0) {
      setUiToken(queryToken);
      params.delete("token");
      const rest = params.toString();
      const next =
        window.location.pathname +
        (rest.length > 0 ? `?${rest}` : "") +
        window.location.hash;
      window.history.replaceState(null, "", next);
    }
  }
} catch {
  // Non-browser context: the token stays available from other sources.
}

export type RequestKind = "read" | "write" | "chat";

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  kind?: RequestKind;
  actor?: string;
  // FXANSWER S2: an abort signal for streams (the chat cancel aborts the
  // local reader at once; the signal only rides fetch, never the wire).
  signal?: AbortSignal;
  // PLANB X5: extra request headers (the chat run id); never the token.
  headers?: Record<string, string>;
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
  if (options.headers !== undefined) {
    for (const [name, value] of Object.entries(options.headers)) {
      if (name.toLowerCase() !== UI_TOKEN_HEADER && name.toLowerCase() !== ACTOR_HEADER) {
        headers[name] = value;
      }
    }
  }
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      ...(options.signal === undefined ? {} : { signal: options.signal }),
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

export function apiErrorLocaleKey(code: string): string {
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
    case "PROJECT_FOLDER_IN_USE":
      return "api.error.project_folder_in_use";
    case "PROJECT_FOLDER_MISSING":
      return "api.error.project_folder_missing";
    case "NO_PROVIDER_BOUND":
      return "firstrun.steps.connectProvider";
    case "GENERIC_ERROR":
      return "errors.generic";
    case "SECRET_VALUE_MISSING":
      return "chat.error.keyMissing";
    case "CREDENTIAL_STORE_UNREADABLE":
      return "chat.error.storeUnreadable";
    default:
      return "errors.generic";
  }
}
