/** @vitest-environment jsdom */
// K07NEXT5 B0B-UNCOVERED_ARCH-526: the REAL LocalAiViewCard over a fresh
// HttpApiClient (only global fetch replaced, quoting the served settings
// view schema from src/agent_si/http/k07next5.py local_ai_settings_view).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { LocalAiViewCard } from "../LocalAiViewCard";

const SETTINGS_VIEW_URL =
  "/api/v1/app/local-ai/settings-view?project_key=proj-a";

const SERVED_LOCAL_AI_VIEW = {
  row: "B0B-UNCOVERED_ARCH-526",
  project_key: "proj-a",
  title_key: "settings.localAi.title",
  purpose_key: "settings.localAi.purpose",
  need_it_now_key: "settings.localAi.needItNow",
  config: {
    project_key: "proj-a",
    endpoint_url: "http://127.0.0.1:11434",
    model_id: "llama3.1:8b",
    permission_scope: "local-contact-allowed",
    local_only_mode: false,
  },
  endpoint_url: "http://127.0.0.1:11434",
  models: [],
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
    if (String(input) === SETTINGS_VIEW_URL) {
      return jsonBody(SERVED_LOCAL_AI_VIEW);
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

describe("k07next5 ARCH-526 local AI view over the real screen", () => {
  it("renders the stored endpoint plus model", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocalAiViewCard />
      </ApiClientProvider>,
    );
    const card = await screen.findByTestId("k07next5-local-ai-view");
    expect(card).toBeTruthy();
    expect(seen).toContain(SETTINGS_VIEW_URL);
    expect(screen.getByText(en.settings.localAi.title)).toBeTruthy();
    expect(screen.getByText("http://127.0.0.1:11434")).toBeTruthy();
    expect(screen.getByText("llama3.1:8b")).toBeTruthy();
  });
});
