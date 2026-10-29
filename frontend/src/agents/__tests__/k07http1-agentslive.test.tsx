/** @vitest-environment jsdom */
// K07HTTP1 M-R-UX-7: the status-chip human text over the live GET through
// the REAL HttpApiClient (only global fetch stubbed; no FakeApiClient, no
// setLiveRows). Served rows follow PartRowSchema
// (frontend/src/api/agentsApi.ts:25); the project row follows
// ProjectRecordSchema (frontend/src/api/projectsApi.ts:50).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { AgentsLive } from "../AgentsLive";
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

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  seen.length = 0;
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    seen.push({
      url: path,
      method,
      headers: { ...((init?.headers ?? {}) as Record<string, string>) },
    });
    if (path === "/api/v1/agents/live" && method === "GET") {
      return jsonBody({
        agents: [
          {
            agent: "n-live-1",
            scope: "s-1",
            deliverable: "d-1",
            status: "RUNNING",
          },
          {
            agent: "n-live-2",
            scope: "s-2",
            deliverable: "d-2",
            status: "QUEUED",
          },
        ],
      });
    }
    if (path === "/api/v1/projects/p-1" && method === "GET") {
      return jsonBody({
        project: {
          project_id: "p-1",
          name: "live nine",
          created_at: "2026-01-01T00:00:00.000Z",
        },
      });
    }
    throw new Error(`unexpected fetch ${method} ${path}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07http1 agents live over HttpApiClient", () => {
  it("proves the status-chip human text over the live GET", async () => {
    const before = window.location.href;
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-row-n-live-1")).toBeTruthy();
    // Status-chip human text: RUNNING maps through tasks.status.running
    // (agentsApi resolveStatusHuman over the served status code).
    expect(
      (await screen.findByTestId("agent-row-n-live-1")).textContent,
    ).toContain(en.tasks.status.running);
    expect(
      (await screen.findByTestId("agent-row-n-live-2")).textContent,
    ).toContain(en.tasks.status.queued);
    expect(
      (await screen.findByTestId("agents-live-project")).textContent,
    ).toContain("live nine");
    const liveGets = seen.filter(
      (request) =>
        request.url === "/api/v1/agents/live" && request.method === "GET",
    );
    expect(liveGets.length).toBeGreaterThanOrEqual(1);
    for (const request of seen) {
      expect(request.url).not.toContain("token");
      expect(request.url).not.toContain("TOKEN");
      expect(request.headers["x-ui-session-token"]).toBeUndefined();
    }
    expect(window.location.href).toBe(before);
  });
});
