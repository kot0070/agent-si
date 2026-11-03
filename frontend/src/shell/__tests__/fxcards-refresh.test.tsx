/** @vitest-environment jsdom */
// FXCARDS C2 RED-first: a failed refresh keeps last good values for the
// same project (Context + Tokens cards never blink to blank); only a
// project change clears. Real Inspector render, fetch stubbed at the
// network boundary only.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import type { ReactElement } from "react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { Inspector } from "../Inspector";

const PROJECT = {
  project_id: "p-1",
  name: "P1",
  created_at: "2026-02-11T06:42:44Z",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

// FXCARDS C1: served runs are newest-first: run-2 (the second run) first.
const RUNS_LEDGER = {
  rows: [],
  runs: [
    {
      run_id: "run-2",
      start: "2026-02-11T06:42:00Z",
      end: "2026-02-11T06:43:00Z",
      parts: [],
      verdicts: {},
      tokens: 13938,
      cost: "UNKNOWN",
      files: [],
      success: true,
      summary: "second",
    },
    {
      run_id: "run-1",
      start: "2026-02-11T06:40:00Z",
      end: "2026-02-11T06:41:00Z",
      parts: [],
      verdicts: {},
      tokens: 5142,
      cost: "UNKNOWN",
      files: [],
      success: true,
      summary: "first",
    },
  ],
};

const TELEMETRY = {
  metric_records: 2,
  telemetry_events: 2,
  totals: { tokens_total: 19080, cloud_calls: 2 },
  tasks: ["t-1"],
  models: [{ model: "m-1", calls: 2, tokens: 19080, cost: "UNAVAILABLE" }],
  providers: [{ provider: "meta", calls: 2, tokens: 19080, cost: "UNAVAILABLE" }],
};

let failLedger = false;
let failTelemetry = false;

function stubRefresh(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p-1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/runs/ledger")) {
        if (failLedger) {
          return jsonBody({ code: "FXCARDS_LEDGER_DOWN" }, 500);
        }
        return jsonBody(RUNS_LEDGER);
      }
      if (method === "GET" && url.startsWith("/api/v1/tasks")) {
        return jsonBody({ tasks: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/budget")) {
        return jsonBody({
          project_id: "p-1",
          budget: {
            project_id: "p-1",
            hard_limit: 5,
            spent: 0,
            reserved: 0,
            currency: "USD",
          },
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/watcher/status")) {
        return jsonBody({
          project_id: "p-1",
          integrity_ok: true,
          journal_head: "evt-1",
          generated_at: "2026-02-11T06:42:44Z",
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/watcher/journal")) {
        return jsonBody([]);
      }
      if (method === "GET" && url.startsWith("/api/v1/apps/card")) {
        return jsonBody({
          project_id: "p-1",
          service_ids: [],
          paused: false,
          generated_at: "t-0",
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/analytics/telemetry")) {
        if (failTelemetry) {
          return jsonBody({ code: "FXCARDS_TELEMETRY_DOWN" }, 500);
        }
        return jsonBody(TELEMETRY);
      }
      if (method === "GET" && url === "/api/v1/providers") {
        return jsonBody({
          providers: [{ provider_id: "meta", health: "ok", evidenced: true }],
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/teststage/plans/latest")) {
        return jsonBody({ code: "NO_PLAN" }, 404);
      }
      if (method === "GET" && url.startsWith("/api/v1/teststage/runs/latest")) {
        return jsonBody({ code: "NO_RUN" }, 404);
      }
      if (method === "GET" && url.startsWith("/api/v1/local/models")) {
        return jsonBody({ code: "NO_LOCAL" }, 404);
      }
      return jsonBody({ code: "FXCARDS_UNEXPECTED_API" }, 404);
    },
  );
}

function renderInspector(): void {
  const router = createMemoryRouter(
    [{ path: "*", element: <Inspector projectId="p-1" live={<span>live</span>} /> }],
    { initialEntries: ["/"] },
  );
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.locale", "en");
  setLocale("en");
  failLedger = false;
  failTelemetry = false;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxcards failed refresh keeps last good values", () => {
  it("first read ok, second read fails: Context and Tokens numbers stay", async () => {
    stubRefresh();
    renderInspector();
    // First read serves the second run's numbers (newest-first).
    const lastRun = await screen.findByTestId("tokens-last-run");
    expect(lastRun.textContent).toContain("13,938");
    const project = await screen.findByTestId("tokens-project");
    expect(project.textContent).toContain("19,080");
    // The second refresh fails on both routes (visibility tick): no
    // blank card values, the last good numbers stay.
    failLedger = true;
    failTelemetry = true;
    document.dispatchEvent(new Event("visibilitychange"));
    // Let the failed refresh round-trip finish (retries included).
    await new Promise((resolve) => {
      setTimeout(resolve, 800);
    });
    expect((await screen.findByTestId("tokens-last-run")).textContent).toContain(
      "13,938",
    );
    expect((await screen.findByTestId("tokens-project")).textContent).toContain(
      "19,080",
    );
    expect((await screen.findByTestId("ctx-used")).textContent).toContain(
      "19,080",
    );
    expect((await screen.findByTestId("ctx-last-run")).textContent).toContain(
      "13,938",
    );
    // Results still names the second run, not an empty state.
    const verdict = await screen.findByTestId("result-last-verdict");
    expect(verdict.textContent).toContain("second");
  });
});
