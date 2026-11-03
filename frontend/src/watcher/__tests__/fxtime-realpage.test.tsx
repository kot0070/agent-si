/** @vitest-environment jsdom */
// FXTIME real page: the watcher card, a chat bubble and a run-report row
// render the SAME formatScreenTime string (fetch-level fake only; the App
// routes, the real components, the real state). Runs in en and in uk.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { App } from "../../app/App";
import {
  formatScreenTime,
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import {
  CURRENT_PROJECT_STORAGE_KEY,
} from "../../app/ApiClientProvider";

const FIXED = "2026-02-11T19:25:00Z";

const PROJECT = {
  project_id: "p1",
  name: "P1",
  created_at: FIXED,
};

const STATUS = {
  project_id: "p1",
  integrity_ok: true,
  journal_head: "evt-1",
  generated_at: FIXED,
  checks_done: 3,
  alerts_raised: 0,
  last_check_at: FIXED,
  watcher_calls: 1,
  watcher_tokens: 5,
  watched_runs: 1,
  watched_agents: 0,
  last_action: "",
  rules_fired: [],
};

const RUN = {
  run_id: "r1",
  start: FIXED,
  end: FIXED,
  parts: [],
  verdicts: {},
  tokens: 0,
  cost: "0",
  files: [],
  success: true,
  summary: "done",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      if (
        method === "GET" &&
        url.startsWith("/api/v1/watcher/status")
      ) {
        return jsonBody(STATUS);
      }
      if (
        method === "GET" &&
        url.startsWith("/api/v1/watcher/journal")
      ) {
        return jsonBody([
          { entry_id: "evt-1", timestamp: FIXED, hash: "h1" },
        ]);
      }
      if (url.startsWith("/api/v1/chat/history")) {
        if (method === "POST") {
          return jsonBody({ ok: true });
        }
        return jsonBody({
          turns: [
            {
              project_id: "p1",
              user_text: "hi",
              assistant_text: "hello",
              time: FIXED,
            },
          ],
        });
      }
      if (url.startsWith("/api/v1/chat/models")) {
        return jsonBody({ project_id: "p1", models: [] });
      }
      if (url === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (url.startsWith("/api/v1/routing/role")) {
        return jsonBody({ error: "missing" }, 404);
      }
      if (url.startsWith("/api/v1/permissions/install-request")) {
        return jsonBody({ error: "missing" }, 404);
      }
      if (url === "/api/v1/permissions/check" && method === "POST") {
        return jsonBody({ allowed: true, asked_once: false });
      }
      if (url === "/api/v1/chat/decision" && method === "POST") {
        return jsonBody({ ok: true });
      }
      if (url.includes("/api/v1/chat/cancel")) {
        return jsonBody({ ok: true });
      }
      if (method === "GET" && url.startsWith("/api/v1/runs/ledger")) {
        return jsonBody({ rows: [], runs: [RUN] });
      }
      if (method === "GET" && url.startsWith("/api/v1/tasks")) {
        return jsonBody({ tasks: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/budget")) {
        return jsonBody({ project_id: "p1", budget: null });
      }
      if (method === "GET" && url.startsWith("/api/v1/apps/card")) {
        return jsonBody({
          project_id: "p1",
          service_ids: [],
          paused: false,
          generated_at: FIXED,
        });
      }
      throw new Error(`fxtime unexpected fetch ${method} ${url}`);
    },
  );
}

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
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
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  window.localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, "p1");
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe.each(["en", "uk"] as const)("fxtime real page (%s)", (locale) => {
  it("watcher card, chat bubble and run row share one time string", async () => {
    window.localStorage.setItem("agentsi.locale", locale);
    setLocale(locale);
    const expected = formatScreenTime(FIXED, locale);

    renderAppAt("/watcher");
    const lastCheck = await screen.findByTestId("watcher-last-check");
    expect(lastCheck.textContent).toContain(expected);
    expect(lastCheck.textContent).not.toContain(FIXED);
    expect(lastCheck.textContent).not.toMatch(/AM|PM/);
    cleanup();

    renderAppAt("/projects/p1/chat");
    const stamps = await screen.findAllByTestId("chat-timestamp");
    expect(stamps.length).toBeGreaterThan(0);
    for (const stamp of stamps) {
      expect(stamp.textContent).toBe(expected);
    }
    cleanup();

    renderAppAt("/projects/p1/runs");
    const card = await screen.findByTestId("devrun-card-r1");
    expect(card.textContent).toContain(expected);
    expect(card.textContent).not.toContain(FIXED);
  });
});
