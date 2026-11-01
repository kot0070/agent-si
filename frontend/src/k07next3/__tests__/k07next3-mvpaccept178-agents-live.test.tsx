/** @vitest-environment jsdom */
// K07NEXT3 B0B-UNCOVERED_MVP_ACCEPT-178: the REAL AgentsLiveOverview over a
// fresh HttpApiClient (only global fetch replaced, quoting the served
// agents live schema from src/agent_si/backend/app.py:125).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { AgentsLiveOverview } from "../AgentsLiveOverview";

const SERVED_AGENTS = {
  agents: [],
};

const seen: string[] = [];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  seen.length = 0;
  vi.stubGlobal("fetch", async (input: unknown) => {
    seen.push(String(input));
    if (String(input) === "/api/v1/agents/live") {
      return jsonBody(SERVED_AGENTS);
    }
    throw new Error(`unexpected fetch ${String(input)}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07next3 B0B-UNCOVERED_MVP_ACCEPT-178 agents live over the real screen", () => {
  it("renders the served empty agents list", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <AgentsLiveOverview />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next3-agents-live");
    expect(seen).toContain("/api/v1/agents/live");
    expect(screen.getByText(en.projects.list.title)).toBeTruthy();
    expect(screen.getByText(en.projects.list.empty)).toBeTruthy();
  });
});
