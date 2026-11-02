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
import { requestJson, requestResponse } from "../api/errors";
import { z } from "zod";
import { t } from "../locale/index";

export const ASK_CHECK_ROUTE = "/api/v1/permissions/check";

/** FXR1B: installer grant + pending-ask-argv routes (served ledger). */
export const PROJECT_GRANT_ROUTE = "/api/v1/permissions/project-grant";
export const PROJECT_GRANTS_ROUTE = "/api/v1/permissions/project-grants";
export const INSTALL_REQUEST_ROUTE = "/api/v1/permissions/install-request";

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

const InstallRequestSchema = z.object({
  tool_id: z.string(),
  argv: z.array(z.string()),
});

const ProjectGrantSchema = z.object({
  project_id: z.string(),
  installer: z.string(),
  subcommand: z.string(),
  time: z.string(),
});

const ProjectGrantsSchema = z.object({
  grants: z.array(ProjectGrantSchema),
});

export type ProjectGrant = z.infer<typeof ProjectGrantSchema>;

/** Head word of an install ask from its tool id (never the raw key). */
export function installHeadFromToolId(
  toolId: string,
  projectId: string,
): string {
  const prefix = `install:${projectId}:`;
  const head = toolId.startsWith(prefix)
    ? toolId.slice(prefix.length)
    : toolId;
  return head !== "" ? head : toolId;
}

/** Subcommand word of install argv (installer + subcommand only). */
export function installSubcommand(argv: readonly string[]): string {
  if (argv.length < 2) {
    return "";
  }
  const second = argv[1] ?? "";
  return second !== "" && !second.startsWith("-") ? second : "";
}

/** Human install command for cards and lines (never a raw key). */
export function installDisplayCommand(
  toolId: string,
  projectId: string,
  argv: readonly string[] | null,
): string {
  if (argv !== null && argv.length > 0) {
    const head = argv[0] ?? "";
    const sub = installSubcommand(argv);
    const command = sub !== "" ? `${head} ${sub}` : head;
    if (command.trim() !== "") {
      return command;
    }
  }
  return installHeadFromToolId(toolId, projectId);
}

/** Pinned argv behind one pending install ask; null when unknown. */
export async function readInstallArgv(
  toolId: string,
): Promise<readonly string[] | null> {
  try {
    const page = await requestJson(
      `${INSTALL_REQUEST_ROUTE}?tool_id=${encodeURIComponent(toolId)}`,
      { method: "GET", kind: "write" },
      InstallRequestSchema,
    );
    return page.argv;
  } catch {
    return null;
  }
}

/** Record a per-project installer grant; replays the parked run after. */
export async function recordProjectGrant(
  projectId: string,
  toolId: string,
): Promise<ProjectGrant> {
  const page = await requestJson(
    PROJECT_GRANT_ROUTE,
    {
      method: "POST",
      kind: "write",
      body: { project_id: projectId, tool_id: toolId },
    },
    ProjectGrantSchema,
  );
  return page;
}

/** List installer grants for one project. */
export async function listProjectGrants(
  projectId: string,
): Promise<ProjectGrant[]> {
  try {
    const page = await requestJson(
      `${PROJECT_GRANTS_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
      { method: "GET", kind: "read" },
      ProjectGrantsSchema,
    );
    return page.grants;
  } catch {
    return [];
  }
}

/** Remove one installer grant; true when a row was present. */
export async function removeProjectGrant(
  projectId: string,
  installer: string,
  subcommand: string,
): Promise<boolean> {
  try {
    const response = await requestResponse(PROJECT_GRANT_ROUTE, {
      method: "DELETE",
      kind: "write",
      body: {
        project_id: projectId,
        installer,
        subcommand,
      },
    });
    const data = (await response.json()) as { removed?: unknown };
    return data.removed === true;
  } catch {
    return false;
  }
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
