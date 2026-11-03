// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import {
  CARD_BACKEND_RULE,
  SERVICE_CHECK_KINDS,
  SERVICE_CHECK_ROUTE,
  SERVICE_STATUS_ROUTE,
  WATCHER_ALERTS_ROUTE,
  WATCHER_EVALUATE_ROUTE,
  WATCHER_INTEGRITY_ROUTE,
  WATCHER_TIMER_FIRE_ROUTE,
  WATCHER_TIMER_PAUSE_ROUTE,
  backendRuleForCard,
} from "./watcherOps";

describe("watcherOps contract (RED: module missing)", () => {
  it("pins the frozen watcher HTTP surface", () => {
    expect(WATCHER_ALERTS_ROUTE).toBe("/api/v1/watcher/alerts");
    expect(WATCHER_INTEGRITY_ROUTE).toBe("/api/v1/watcher/integrity-check");
    expect(WATCHER_EVALUATE_ROUTE("rule-guard")).toBe(
      "/api/v1/watcher/rules/rule-guard/evaluate",
    );
    expect(WATCHER_TIMER_FIRE_ROUTE("t-1")).toBe(
      "/api/v1/watcher/timers/t-1/fire",
    );
    expect(WATCHER_TIMER_PAUSE_ROUTE("t-1")).toBe(
      "/api/v1/watcher/timers/t-1/pause",
    );
    expect(SERVICE_STATUS_ROUTE("svc-api")).toBe(
      "/api/v1/services/svc-api/status",
    );
    expect(SERVICE_CHECK_ROUTE("svc-api")).toBe(
      "/api/v1/services/svc-api/check",
    );
  });

  it("maps frontend cards to backend rules, hang to none", () => {
    expect(backendRuleForCard("card-guard")).toBe("rule-guard");
    expect(backendRuleForCard("card-tamper")).toBe("rule-tamper");
    expect(backendRuleForCard("card-hang")).toBeNull();
    expect(CARD_BACKEND_RULE["card-hang"]).toBeNull();
  });

  it("offers the frozen service check kinds", () => {
    expect([...SERVICE_CHECK_KINDS]).toEqual([
      "HTTP",
      "TCP",
      "CONTAINER_READONLY",
    ]);
  });
});
