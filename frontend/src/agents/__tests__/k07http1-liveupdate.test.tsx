/** @vitest-environment jsdom */
// K07HTTP1 ARCH-550: rows updating without reload over the REAL
// HttpApiClient subscribe path (only global fetch stubbed; no
// FakeApiClient, never setLiveRows). HttpApiClient carries no push
// listener, so AgentsLive polls; the stub answers two fetch generations
// and the second generation renders without a location change. Served
// rows follow PartRowSchema (frontend/src/api/agentsApi.ts:25); the
// project row follows ProjectRecordSchema
// (frontend/src/api/projectsApi.ts:50).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { AgentsLive } from "../AgentsLive";
import en from "../../locale/en.json";

function jsonBody(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

let liveCalls = 0;

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  liveCalls = 0;
  vi.stubGlobal("fetch", async (url: unknown, init?: { method?: string }) => {
    const path = String(url);
    const method = init?.method ?? "GET";
    if (path === "/api/v1/agents/live" && method === "GET") {
      liveCalls += 1;
      if (liveCalls >= 2) {
        return jsonBody({
          agents: [
            {
              agent: "b-2",
              scope: "s-2",
              deliverable: "d-2",
              status: "QUEUED",
            },
          ],
        });
      }
      return jsonBody({
        agents: [
          {
            agent: "a-1",
            scope: "s-1",
            deliverable: "d-1",
            status: "RUNNING",
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

describe("k07http1 live update over HttpApiClient", () => {
  it("proves rows updating without reload through the poll generations", async () => {
    const before = window.location.href;
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-row-a-1")).toBeTruthy();
    expect((await screen.findByTestId("agent-row-a-1")).textContent).toContain(
      en.tasks.status.running,
    );
    await waitFor(
      () => {
        expect(liveCalls).toBeGreaterThanOrEqual(2);
      },
      { timeout: 8000 },
    );
    expect(await screen.findByTestId("agent-row-b-2")).toBeTruthy();
    expect((await screen.findByTestId("agent-row-b-2")).textContent).toContain(
      en.tasks.status.queued,
    );
    expect(window.location.href).toBe(before);
  }, 15000);
});
