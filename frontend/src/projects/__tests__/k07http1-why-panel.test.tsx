/** @vitest-environment jsdom */
// K07HTTP1 MVP_ACCEPT-189: policy plus candidates plus provenance
// rendered over the routing-why GET through the REAL HttpApiClient
// (only global fetch stubbed; no FakeApiClient). The why body follows
// RoutingWhySchema (frontend/src/api/projectsApi.ts:141 with
// ReasonTextSchema :133); sibling panels follow ProjectRecordSchema
// (:50), TaskRecordSchema (:65), LedgerRowSchema (:78) and
// BudgetStateSchema (:152); live rows follow PartRowSchema
// (frontend/src/api/agentsApi.ts:25).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";

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
    if (url === "/api/v1/projects/p-1" && method === "GET") {
      return jsonBody({
        project: {
          project_id: "p-1",
          name: "why nine",
          created_at: "2026-01-01T00:00:00.000Z",
        },
      });
    }
    if (url === "/api/v1/tasks?project_id=p-1" && method === "GET") {
      return jsonBody({ tasks: [] });
    }
    if (url === "/api/v1/runs/ledger?project_id=p-1" && method === "GET") {
      return jsonBody({ rows: [] });
    }
    if (url === "/api/v1/budget?project_id=p-1" && method === "GET") {
      return jsonBody({
        project_id: "p-1",
        budget: {
          project_id: "p-1",
          hard_limit: 100,
          spent: 1,
          reserved: 0,
          currency: "u-1",
        },
      });
    }
    if (url === "/api/v1/agents/live" && method === "GET") {
      return jsonBody({ agents: [] });
    }
    if (url === "/api/v1/routing/decision/d-1/why" && method === "GET") {
      return jsonBody({
        decision: { decision_id: "d-1", policy_ref: "pol-why-1" },
        assignments: [
          {
            decision_id: "d-1",
            role: "worker",
            provider_id: "prov-w",
            model: "mod-w",
          },
          {
            decision_id: "d-1",
            role: "manager",
            provider_id: "prov-m",
            model: "mod-m",
          },
        ],
        snapshot: {
          decision_id: "d-1",
          snapshot_ref: "snap-why-1",
          captured_at: "t-why-1",
        },
        reason: {
          task_class: "tc-why-1",
          fit_basis: "stored why reason",
          price_basis: "KNOWN",
          quality_basis: "MEASURED",
          rejected: ["r-x"],
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

describe("k07http1 why panel over HttpApiClient", () => {
  it("proves policy plus candidates plus provenance over the routing-why GET", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectView
          projectId="p-1"
          view="routing-decisions"
          decisionId="d-1"
        />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("why-this-model")).toBeTruthy();
    // Policy: the served policy_ref plus the fit-basis reason.
    expect(
      (await screen.findByTestId("why-this-model-reason")).textContent,
    ).toBe("stored why reason");
    expect(
      (await screen.findByTestId("why-version")).textContent,
    ).toContain("pol-why-1");
    // Candidates: every served assignment renders provider/model plus role.
    expect(
      (await screen.findByTestId("why-candidate-0")).textContent,
    ).toContain("prov-w/mod-w worker");
    expect(
      (await screen.findByTestId("why-candidate-1")).textContent,
    ).toContain("prov-m/mod-m manager");
    // Provenance: snapshot ref plus captured stamp plus decision link.
    expect((await screen.findByTestId("why-provenance")).textContent).toContain(
      "snap-why-1",
    );
    expect((await screen.findByTestId("why-provenance")).textContent).toContain(
      "t-why-1",
    );
    expect(
      (await screen.findByTestId("why-this-model-decision")).textContent,
    ).toContain("d-1");
    const whyGets = seen.filter(
      (request) =>
        request.url === "/api/v1/routing/decision/d-1/why" &&
        request.method === "GET",
    );
    expect(whyGets.length).toBeGreaterThanOrEqual(1);
    for (const request of seen) {
      expect(request.url).not.toContain("token");
      expect(request.headers["x-ui-session-token"]).toBeUndefined();
    }
  });
});
