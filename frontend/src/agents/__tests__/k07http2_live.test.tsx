/** @vitest-environment jsdom */
// K07HTTP2 1484 (M-R-UX-7 AgentsLive status chip) + 1527 (ARCH-550 live
// update) over the REAL HttpApiClient (only global fetch stubbed, never
// FakeApiClient, never setLiveRows). Served rows follow PartRowSchema
// (frontend/src/api/agentsApi.ts:25); the project row follows
// ProjectRecordSchema (frontend/src/api/projectsApi.ts:50). Asserts the
// request URL plus method plus no read-token header and the rendered text;
// the live-update test drives the real poll path with two fetch generations.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
let liveCalls = 0;
let secondGen = false;

function jsonBody(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function firstGenAgents(): unknown[] {
  return [
    { agent: "h2-1", scope: "s-1", deliverable: "d-1", status: "RUNNING" },
  ];
}

function secondGenAgents(): unknown[] {
  return [
    { agent: "h2-2", scope: "s-2", deliverable: "d-2", status: "QUEUED" },
  ];
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  seen.length = 0;
  liveCalls = 0;
  secondGen = false;
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    seen.push({
      url,
      method,
      headers: { ...((init?.headers ?? {}) as Record<string, string>) },
    });
    if (url === "/api/v1/agents/live" && method === "GET") {
      liveCalls += 1;
      if (secondGen && liveCalls >= 2) {
        return jsonBody({ agents: secondGenAgents() });
      }
      return jsonBody({ agents: firstGenAgents() });
    }
    if (url === "/api/v1/projects/p-1" && method === "GET") {
      return jsonBody({
        project: {
          project_id: "p-1",
          name: "h2 nine",
          created_at: "2026-01-01T00:00:00.000Z",
        },
      });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07http2 agents live over HttpApiClient", () => {
  it("1484: status chip renders served human text over the live GET", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-row-h2-1")).toBeTruthy();
    expect((await screen.findByTestId("agent-row-h2-1")).textContent).toContain(
      en.tasks.status.running,
    );
    expect((await screen.findByTestId("agents-live-project")).textContent).toContain(
      "h2 nine",
    );
    const liveGets = seen.filter(
      (request) => request.url === "/api/v1/agents/live" && request.method === "GET",
    );
    expect(liveGets.length).toBeGreaterThanOrEqual(1);
    for (const request of seen) {
      expect(request.url).not.toContain("token");
      expect(request.headers["x-ui-session-token"]).toBeUndefined();
    }
  });

  it("1527: rows update without reload through the real poll path", async () => {
    secondGen = true;
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-row-h2-1")).toBeTruthy();
    await waitFor(
      () => {
        expect(liveCalls).toBeGreaterThanOrEqual(2);
      },
      { timeout: 8000 },
    );
    expect(await screen.findByTestId("agent-row-h2-2")).toBeTruthy();
    expect((await screen.findByTestId("agent-row-h2-2")).textContent).toContain(
      en.tasks.status.queued,
    );
    const liveGets = seen.filter(
      (request) => request.url === "/api/v1/agents/live" && request.method === "GET",
    );
    expect(liveGets.length).toBeGreaterThanOrEqual(2);
  }, 15000);
});
