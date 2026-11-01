/** @vitest-environment jsdom */
// K07NEXT5 111-UI: the REAL LocalAiDecisionCard over a fresh HttpApiClient
// (only global fetch replaced, quoting the served local AI decision schema
// from src/agent_si/http/k07next5.py local_ai_decision_update).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { LocalAiDecisionCard } from "../LocalAiDecisionCard";

const TOKEN = "tok-k07next5-111ui";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

const SERVED_DECISION = {
  row: "111-UI",
  decision_id: "dec-k07next5abcd",
  config: {
    project_key: "k07next5-b",
    endpoint_url: "http://127.0.0.1:11434",
    model_id: "k07next5-b-model",
    permission_scope: "local-contact-allowed",
    local_only_mode: false,
  },
};

const seen: Array<{
  url: string;
  method: string;
  headers: Record<string, string>;
}> = [];

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
  (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY] = TOKEN;
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    seen.push({
      url: String(input),
      method: (init?.method ?? "GET").toUpperCase(),
      headers: { ...((init?.headers ?? {}) as Record<string, string>) },
    });
    if (String(input) === "/api/v1/app/local-ai/decision-update") {
      return jsonBody(SERVED_DECISION);
    }
    throw new Error(`unexpected fetch ${String(input)}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY];
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07next5 111-UI decision record over the real screen", () => {
  it("carries the token header on the write from the first call", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocalAiDecisionCard />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next5-decision");
    const posts = seen.filter(
      (request) =>
        request.url === "/api/v1/app/local-ai/decision-update" &&
        request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0]?.headers["x-ui-session-token"]).toBe(TOKEN);
    expect(posts[0]?.headers["x-actor"]).toBe("ui");
    expect(
      screen.getByText(en.settings.localbench.decisionTitle),
    ).toBeTruthy();
    expect(screen.getByText("dec-k07next5abcd k07next5-b-model")).toBeTruthy();
  });
});
