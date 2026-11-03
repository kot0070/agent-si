/** @vitest-environment jsdom */
// FXFACTS F5 RED: the runs card reads all through the locale. One failed
// run (key missing, no duration) plus one passed run, uk locale: no raw
// English, known server sentences mapped, no lone unknown line.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";

const PROJECT = {
  project_id: "p9",
  name: "P9",
  created_at: "2026-01-01T00:00:00.000Z",
};

const RUNS = [
  {
    run_id: "r-pass",
    folder: "f",
    start: "2026-11-02T10:00:00Z",
    end: "2026-11-02T10:01:00Z",
    title: "pass",
    parts: [{ part_id: "p1", verdict: "PASS", attempts: 1 }],
    verdicts: { p1: "PASS" },
    tokens: 23,
    cost: "0.000003",
    files: [],
    success: true,
    summary: "run success: all 1 parts PASS",
    manager_why: "one group",
    manager_count: 1,
  },
  {
    run_id: "r-fail",
    folder: "f",
    start: "bad-stamp",
    end: "bad-stamp",
    title: "fail",
    parts: [{ part_id: "p1", verdict: "FAIL", attempts: 1, reason: "key missing" }],
    verdicts: { p1: "FAIL" },
    tokens: "UNKNOWN",
    cost: "UNAVAILABLE",
    files: [],
    success: false,
    summary: "The key for 'meta' is not available. Connect it again.",
    manager_why: "one group",
    manager_count: 1,
  },
];

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
      if (method === "GET" && url === "/api/v1/projects/p9") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/ledger?project_id=p9") {
        return jsonBody({ rows: [] });
      }
      if (method === "GET" && url === "/api/v1/runs/ledger?project_id=p9") {
        return jsonBody({ rows: [], runs: RUNS });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/reports/next-package-nudge")) {
        return jsonBody({ code: "NONE" }, 404);
      }
      return jsonBody({ code: "FXFACTS5_UNEXPECTED_API" }, 404);
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
  window.localStorage.setItem("agentsi.locale", "uk");
  setLocale("uk");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxfacts5 runs card reads the locale", () => {
  it("maps known server sentences and never leaks raw English", async () => {
    stubFetch();
    renderAppAt("/projects/p9/runs");
    const failed = await screen.findByTestId("devrun-card-r-fail");
    const text = failed.textContent ?? "";
    expect(text).not.toContain("Tokens");
    expect(text).not.toContain("not known");
    expect(text).not.toContain("Manager:");
    expect(text).not.toContain("Tokens not known");
    expect(text).not.toContain("The key for 'meta' is not available");
    expect(text).toContain("Токени");
    expect(text).toContain("Ключ для");
    const passed = await screen.findByTestId("devrun-card-r-pass");
    const passedText = passed.textContent ?? "";
    expect(passedText).not.toContain("run success: all 1 parts PASS");
    expect(passedText).not.toContain("Manager:");
    expect(passedText).toContain("Менеджер");
  });
});
