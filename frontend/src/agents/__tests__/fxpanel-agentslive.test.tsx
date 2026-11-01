/** @vitest-environment jsdom */
// FXPANEL R2/R5: AgentsLive shows every live field compactly over the
// REAL HttpApiClient (only global fetch stubbed). Served rows carry the
// frozen four plus the append-only live fields (role/model/step/file/
// cost/tokens/context/errors/waits); the panel keeps its existing
// layout, respects the current theme, and carries no slop styling.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
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

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const path = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (path === "/api/v1/agents/live" && method === "GET") {
      return jsonBody({
        agents: [
          {
            agent: "fxp-1",
            scope: "fxp-task/fxp-sub",
            deliverable: "artifact://run/fxp-1/output",
            status: "RUNNING",
            role: "manager",
            model: "mock-canned",
            step: 2,
            file: "artifact://run/fxp-1/output",
            cost: "0.000001",
            tokens: { input: 12, output: 34 },
            context: "artifact:run/fxp-1/input",
            errors: [],
            waits: ["approval"],
          },
        ],
      });
    }
    if (path === "/api/v1/projects/p-1" && method === "GET") {
      return jsonBody({
        project: {
          project_id: "p-1",
          name: "fxp panel",
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

describe("fxpanel agents live compact fields", () => {
  it("shows every live field compactly with no slop styling", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId("agent-row-fxp-1");
    expect(row).toBeTruthy();
    expect(row.textContent).toContain(en.tasks.status.running);
    const detail = await screen.findByTestId("agent-row-detail-fxp-1");
    const text = detail.textContent ?? "";
    for (const value of [
      "manager",
      "mock-canned",
      "2",
      "artifact://run/fxp-1/output",
      "0.000001",
      "12",
      "34",
      "artifact:run/fxp-1/input",
      "approval",
    ]) {
      expect(text).toContain(value);
    }
    const html = row.innerHTML;
    expect(html).not.toMatch(/linear-gradient/i);
    expect(html).not.toMatch(/backdrop-filter|glass/i);
    expect(text).not.toMatch(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u);
  });
});
