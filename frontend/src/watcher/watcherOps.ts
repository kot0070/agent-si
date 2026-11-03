/** Watcher page HTTP calls: one wrapper per backend route.
 *
 * GET routes are open and follow the WatcherTab pattern (fetch plus
 * parseErrorBody); POST routes carry the session token through
 * requestResponse kind "write" (the TopBar stop-all pattern). Every
 * wrapper serves the stored body verbatim and never computes values.
 * The apps-card route constant and base row come from AppsCard.tsx; the
 * additive served columns (services, safe_to_close, close_prompt) ride
 * casts because the frozen row keeps only the four base fields.
 */

import {
  parseErrorBody,
  requestResponse,
} from "../api/errors";
import { APPS_CARD_ROUTE, type AppsCardData } from "./AppsCard";

/** Frozen GET route serving one alert row per due rule card. */
export const WATCHER_ALERTS_ROUTE = "/api/v1/watcher/alerts";

/** Frozen POST route verifying integrity over stored hashes. */
export const WATCHER_INTEGRITY_ROUTE = "/api/v1/watcher/integrity-check";

/** Frozen POST route evaluating one rule card. */
export function WATCHER_EVALUATE_ROUTE(ruleId: string): string {
  return `/api/v1/watcher/rules/${encodeURIComponent(ruleId)}/evaluate`;
}

/** Additive POST route firing one watcher timer. */
export function WATCHER_TIMER_FIRE_ROUTE(timerId: string): string {
  return `/api/v1/watcher/timers/${encodeURIComponent(timerId)}/fire`;
}

/** Additive POST route pausing or resuming one watcher timer. */
export function WATCHER_TIMER_PAUSE_ROUTE(timerId: string): string {
  return `/api/v1/watcher/timers/${encodeURIComponent(timerId)}/pause`;
}

/** Frozen GET route serving one service status row. */
export function SERVICE_STATUS_ROUTE(serviceId: string): string {
  return `/api/v1/services/${encodeURIComponent(serviceId)}/status`;
}

/** Frozen POST route running one service check. */
export function SERVICE_CHECK_ROUTE(serviceId: string): string {
  return `/api/v1/services/${encodeURIComponent(serviceId)}/check`;
}

/** Frontend card id to the backend rule it evaluates, if any.
 *
 * The backend registry (src/agent_si/watcher/rules.py RULES) serves
 * rule-tamper and rule-guard only; card-hang maps to null because no
 * backend rule-hang exists. A null card renders a read-only note and
 * no Evaluate control.
 */
export const CARD_BACKEND_RULE: Record<string, string | null> = {
  "card-hang": null,
  "card-guard": "rule-guard",
  "card-tamper": "rule-tamper",
};

/** Backend rule id for one frontend card, or null when none exists. */
export function backendRuleForCard(cardId: string): string | null {
  if (!(cardId in CARD_BACKEND_RULE)) {
    return null;
  }
  return CARD_BACKEND_RULE[cardId] ?? null;
}

/** One served alert row: the due card plus its pure verdict. */
export interface WatcherAlertRow {
  alert_id: string;
  project_id: string;
  rule_id: string;
  verdict: string;
  detail: string;
}

/** Fetch the stored alert rows verbatim; never computes values. */
export async function fetchWatcherAlerts(
  projectId: string,
): Promise<WatcherAlertRow[]> {
  const response = await fetch(
    `${WATCHER_ALERTS_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!response.ok) {
    throw parseErrorBody({}, response.status);
  }
  const body = await response.json();
  const rows: unknown[] = Array.isArray(body)
    ? body
    : Array.isArray((body as Record<string, unknown>)["alerts"])
      ? ((body as Record<string, unknown>)["alerts"] as unknown[])
      : [];
  return rows.map((row) => {
    const record = row as Record<string, unknown>;
    return {
      alert_id: String(record["alert_id"] ?? ""),
      project_id: String(record["project_id"] ?? ""),
      rule_id: String(record["rule_id"] ?? ""),
      verdict: String(record["verdict"] ?? ""),
      detail: String(record["detail"] ?? ""),
    };
  });
}

/** Served integrity report: ok plus the mismatched refs, if any. */
export interface IntegrityReportData {
  project_id: string;
  ok: boolean;
  checked_at: string;
  mismatched_refs: string[];
}

/** Run the integrity check; the report reads the served body verbatim. */
export async function postIntegrityCheck(
  projectId: string,
): Promise<IntegrityReportData> {
  const response = await requestResponse(WATCHER_INTEGRITY_ROUTE, {
    method: "POST",
    kind: "write",
    body: { project_id: projectId },
  });
  const body = (await response.json()) as Record<string, unknown>;
  const refs: unknown = body["mismatched_refs"];
  return {
    project_id: String(body["project_id"] ?? ""),
    ok: body["ok"] === true,
    checked_at: String(body["checked_at"] ?? ""),
    mismatched_refs: Array.isArray(refs)
      ? refs.map((ref) => String(ref))
      : [],
  };
}

/** Served rule evaluation: the verdict plus its journal row ref. */
export interface RuleEvaluationData {
  decision_id: string;
  project_id: string;
  rule_id: string;
  verdict: string;
  journal_entry_id: string;
  decided_at: string;
}

/** Evaluate one backend rule; unknown rules refuse with RULE_NOT_FOUND. */
export async function postEvaluateRule(
  projectId: string,
  ruleId: string,
): Promise<RuleEvaluationData> {
  const response = await requestResponse(WATCHER_EVALUATE_ROUTE(ruleId), {
    method: "POST",
    kind: "write",
    body: { project_id: projectId },
  });
  const body = (await response.json()) as Record<string, unknown>;
  return {
    decision_id: String(body["decision_id"] ?? ""),
    project_id: String(body["project_id"] ?? ""),
    rule_id: String(body["rule_id"] ?? ""),
    verdict: String(body["verdict"] ?? ""),
    journal_entry_id: String(body["journal_entry_id"] ?? ""),
    decided_at: String(body["decided_at"] ?? ""),
  };
}

/** Served timer firing receipt plus its journal row ref. */
export interface TimerFireReceiptData {
  timer_id: string;
  project_id: string;
  event: string;
  action_mode: string;
  journal_entry_id: string;
  fired_at: string;
}

/** Fire one watcher timer; a paused timer refuses with AUTOMATION_PAUSED. */
export async function postFireTimer(
  projectId: string,
  timerId: string,
): Promise<TimerFireReceiptData> {
  const response = await requestResponse(WATCHER_TIMER_FIRE_ROUTE(timerId), {
    method: "POST",
    kind: "write",
    body: { project_id: projectId },
  });
  const body = (await response.json()) as Record<string, unknown>;
  return {
    timer_id: String(body["timer_id"] ?? ""),
    project_id: String(body["project_id"] ?? ""),
    event: String(body["event"] ?? ""),
    action_mode: String(body["action_mode"] ?? ""),
    journal_entry_id: String(body["journal_entry_id"] ?? ""),
    fired_at: String(body["fired_at"] ?? ""),
  };
}

/** Served timer pause flag. */
export interface TimerPauseStateData {
  timer_id: string;
  project_id: string;
  paused: boolean;
  reason: string;
}

/** Pause or resume one timer; pausing needs a non-empty reason. */
export async function postPauseTimer(
  projectId: string,
  timerId: string,
  paused: boolean,
  reason: string,
): Promise<TimerPauseStateData> {
  const response = await requestResponse(WATCHER_TIMER_PAUSE_ROUTE(timerId), {
    method: "POST",
    kind: "write",
    body: { project_id: projectId, paused, reason },
  });
  const body = (await response.json()) as Record<string, unknown>;
  return {
    timer_id: String(body["timer_id"] ?? ""),
    project_id: String(body["project_id"] ?? ""),
    paused: body["paused"] === true,
    reason: String(body["reason"] ?? ""),
  };
}

/** Served apps card: the frozen row plus the additive served columns. */
export interface AppsCardFacts extends AppsCardData {
  services: Array<{ service_id: string; name: string }>;
  safe_to_close: boolean;
  close_prompt: string;
}

/** Fetch the stored apps-card facts verbatim, plus additive columns. */
export async function fetchAppsCardFacts(
  projectId: string,
): Promise<AppsCardFacts> {
  const response = await fetch(
    `${APPS_CARD_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!response.ok) {
    throw parseErrorBody({}, response.status);
  }
  const body = (await response.json()) as Record<string, unknown>;
  const ids: unknown = body["service_ids"];
  const services: unknown = body["services"];
  return {
    project_id: String(body["project_id"] ?? ""),
    service_ids: Array.isArray(ids) ? ids.map((id) => String(id)) : [],
    paused: body["paused"] === true,
    generated_at: String(body["generated_at"] ?? ""),
    services: Array.isArray(services)
      ? (services as Array<Record<string, unknown>>).map((entry) => ({
          service_id: String(entry["service_id"] ?? ""),
          name: String(entry["name"] ?? entry["service_id"] ?? ""),
        }))
      : [],
    safe_to_close: body["safe_to_close"] !== false,
    close_prompt: String(body["close_prompt"] ?? ""),
  };
}

/** Served service status row: observe-only facts, never probes. */
export interface ServiceStatusData {
  service_id: string;
  state: string;
  timestamp: string;
  in_use: boolean;
  last_used: string;
  last_agent: string;
}

function readServiceStatus(body: Record<string, unknown>): ServiceStatusData {
  return {
    service_id: String(body["service_id"] ?? ""),
    state: String(body["state"] ?? ""),
    timestamp: String(body["timestamp"] ?? ""),
    in_use: body["in_use"] === true,
    last_used: String(body["last_used"] ?? ""),
    last_agent: String(body["last_agent"] ?? ""),
  };
}

/** Fetch one stored service status row verbatim. */
export async function fetchServiceStatus(
  serviceId: string,
): Promise<ServiceStatusData> {
  const response = await fetch(SERVICE_STATUS_ROUTE(serviceId));
  if (!response.ok) {
    throw parseErrorBody({}, response.status);
  }
  return readServiceStatus((await response.json()) as Record<string, unknown>);
}

/** Frozen service check kinds the check route accepts. */
export const SERVICE_CHECK_KINDS = [
  "HTTP",
  "TCP",
  "CONTAINER_READONLY",
] as const;

/** One frozen service check kind. */
export type ServiceCheckKind = (typeof SERVICE_CHECK_KINDS)[number];

/** Run one service check; refusals surface before any probe. */
export async function postServiceCheck(
  serviceId: string,
  check: ServiceCheckKind,
): Promise<ServiceStatusData> {
  const response = await requestResponse(SERVICE_CHECK_ROUTE(serviceId), {
    method: "POST",
    kind: "write",
    body: { check },
  });
  return readServiceStatus((await response.json()) as Record<string, unknown>);
}

/** Plain-words locale key for a served verdict; never the raw enum. */
export function verdictLocaleKey(verdict: string): string {
  if (verdict === "BLOCK") {
    return "watcher.tab.actionBlocked";
  }
  if (verdict === "ESCALATE") {
    return "watcher.tab.actionEscalated";
  }
  return "watcher.tab.actionAllowed";
}

/** Locale key for a served service state; unknown reads "not known". */
export function serviceStateLocaleKey(state: string): string {
  if (state === "UP") {
    return "watcher.page.stateUp";
  }
  if (state === "DOWN") {
    return "watcher.page.stateDown";
  }
  if (state === "DEGRADED") {
    return "watcher.page.stateDegraded";
  }
  return "watcher.tab.notKnown";
}
