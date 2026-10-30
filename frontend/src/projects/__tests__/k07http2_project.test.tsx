/** @vitest-environment jsdom */
// K07HTTP2 1524 (ARCH-643 readable reports) + 1653 (MVP_ACCEPT-189
// why-this-model) over the REAL HttpApiClient (only global fetch stubbed,
// never FakeApiClient). Served rows follow ProjectRecordSchema
// (frontend/src/api/projectsApi.ts:50), TaskRecordSchema (:65),
// LedgerRowSchema (:78), BudgetStateSchema (:152), RoutingWhySchema (:141)
// with ReasonTextSchema (:133); live rows follow PartRowSchema
// (frontend/src/api/agentsApi.ts:25). Asserts the request URL plus method
// plus no read-token header and the rendered text.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { ProjectView } from "../ProjectView";
import en from "../../locale/en.json";

interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
}

const seen: SeenRequest[] = [];

function jsonBody(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

const CREATED_AT = "2026-01-01T00:00:00.000Z";

function stubBoundary(): void {
  seen.length = 0;
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    seen.push({
      url,
      method,
      headers: { ...((init?.headers ?? {}) as Record<string, string>) },
    });
    if (url === "/api/v1/projects/p-9" && method === "GET") {
      return jsonBody({
        project: { project_id: "p-9", name: "H2 Nine", created_at: CREATED_AT },
      });
    }
    if (url === "/api/v1/tasks?project_id=p-9" && method === "GET") {
      return jsonBody({
        tasks: [
          {
            task_id: "t-9",
            project_id: "p-9",
            title: "running nine",
            status: "RUNNING",
            created_at: CREATED_AT,
          },
          {
            task_id: "t-10",
            project_id: "p-9",
            title: "queued nine",
            status: "QUEUED",
            created_at: CREATED_AT,
          },
        ],
      });
    }
    if (url === "/api/v1/runs/ledger?project_id=p-9" && method === "GET") {
      return jsonBody({
        rows: [{ package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 }],
      });
    }
    if (url === "/api/v1/budget?project_id=p-9" && method === "GET") {
      return jsonBody({
        project_id: "p-9",
        budget: { project_id: "p-9", hard_limit: 100, spent: 10, reserved: 5, currency: "u-9" },
      });
    }
    if (url === "/api/v1/agents/live" && method === "GET") {
      return jsonBody({ agents: [] });
    }
    if (url === "/api/v1/routing/decision/d-9/why" && method === "GET") {
      return jsonBody({
        decision: { decision_id: "d-9", policy_ref: "pol-h2-9" },
        assignments: [
          { decision_id: "d-9", role: "worker", provider_id: "prov-h2", model: "mod-h2" },
        ],
        snapshot: { decision_id: "d-9", snapshot_ref: "snap-h2-9", captured_at: "t-h2-9" },
        reason: {
          task_class: "tc-h2-9",
          fit_basis: "h2 stored reason",
          price_basis: "KNOWN",
          quality_basis: "MEASURED",
          rejected: [],
        },
      });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

function expectReadOnly(requests: SeenRequest[]): void {
  for (const request of requests) {
    expect(request.url).not.toContain("token");
    expect(request.headers["x-ui-session-token"]).toBeUndefined();
  }
}

describe("k07http2 project over HttpApiClient", () => {
  it("1524: readable reports render labelled rows over the reports GETs", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectView projectId="p-9" view="reports" />
      </ApiClientProvider>,
    );
    const readable = await screen.findByTestId("project-report-readable");
    expect(readable.textContent).toContain("H2 Nine");
    expect(readable.textContent).toContain(t("tasks.status.running"));
    expect(readable.textContent).toContain(t("tasks.status.queued"));
    expect(readable.textContent).toContain("10");
    expect(readable.textContent).toContain("u-9");
    expect(readable.textContent).not.toContain('{"');
    const derived = await screen.findByTestId("project-report-derived");
    expect(derived.textContent).toContain(en.projects.derived.label);
    const gets = seen.filter((request) => request.method === "GET");
    expect(gets.some((request) => request.url === "/api/v1/projects/p-9")).toBe(true);
    expect(
      gets.some((request) => request.url === "/api/v1/runs/ledger?project_id=p-9"),
    ).toBe(true);
    expect(
      gets.some((request) => request.url === "/api/v1/budget?project_id=p-9"),
    ).toBe(true);
    expectReadOnly(seen);
  });

  it("1653: why panel renders policy plus candidates plus provenance", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectView projectId="p-9" view="routing-decisions" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("why-this-model")).toBeTruthy();
    expect((await screen.findByTestId("why-this-model-reason")).textContent).toBe(
      "h2 stored reason",
    );
    expect((await screen.findByTestId("why-version")).textContent).toContain("pol-h2-9");
    expect((await screen.findByTestId("why-candidate-0")).textContent).toContain(
      "prov-h2/mod-h2 worker",
    );
    expect((await screen.findByTestId("why-provenance")).textContent).toContain("snap-h2-9");
    expect(
      (await screen.findByTestId("why-this-model-decision")).textContent,
    ).toContain("d-9");
    const whyGets = seen.filter(
      (request) => request.url === "/api/v1/routing/decision/d-9/why" && request.method === "GET",
    );
    expect(whyGets.length).toBeGreaterThanOrEqual(1);
    expectReadOnly(seen);
  });
});
