// FXASK2 install-permission-asked-once product module (F4 canonical home).
// askPermission moved here from frontend/src/teststage/ask_buttons.jsx;
// ChatArea (F2 dialog) and AcceptedRiskSwitch (F3) import it from here.
// The teststage fixture keeps a behavior-identical self-contained copy so
// its fe_run copy (ask_buttons.jsx alone, no product imports) keeps working.
//
// Served route: POST /api/v1/permissions/check (F1, tool-guard ask-once
// file store). The request carries the tool name as { tool_id }; the reply
// carries { allowed, asked_once }. Pending asks are keyed by the tool id
// the approval event carries (the guarded call's tool_name): the dialog
// shows that id, answers POST it, and the served asked_once flag
// suppresses second runs per tool.
//
// The project-scoped installPermissionToolId below is NOT an ask key: it
// is the AcceptedRiskSwitch grant latch (F3, project risk acceptance),
// never posted by the dialog path.

import { ApiError } from "../api/errors";
import { t } from "../locale/index";

export const ASK_CHECK_ROUTE = "/api/v1/permissions/check";

export interface PermissionCheckOutcome {
  allowed: boolean;
  askedOnce: boolean;
}

export interface InstallPermissionAsk {
  toolName: string;
  messageId: string;
}

export function installPermissionToolId(projectId: string): string {
  return `install:${projectId}`;
}

export async function askPermission(
  toolId: string,
): Promise<PermissionCheckOutcome> {
  const res = await fetch(ASK_CHECK_ROUTE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool_id: toolId }),
  });
  if (!res.ok) {
    throw new Error("permission check failed: " + res.status);
  }
  const data = await res.json();
  return {
    allowed: data.allowed === true,
    askedOnce: data.asked_once === true,
  };
}

export function isInstallPermissionAsk(error: unknown): boolean {
  // FXASK2: only a hold that names its tool is an install-permission
  // ask (the dialog + POST need the event's tool id, once per tool).
  // A toolless hold keeps the pre-lane blocking-error behavior.
  return (
    error instanceof ApiError &&
    error.code === "APPROVAL_REQUIRED" &&
    typeof error.toolId === "string" &&
    error.toolId !== ""
  );
}

export function pt(
  key: string,
  fallback: string,
  params?: Record<string, string | number>,
): string {
  let template: string;
  try {
    template = t(key);
  } catch {
    template = fallback;
  }
  if (params === undefined) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}
