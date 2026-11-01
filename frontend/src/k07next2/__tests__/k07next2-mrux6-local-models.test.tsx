/** @vitest-environment jsdom */
// K07NEXT2 M-R-UX-6: the REAL LocalModels over a fresh HttpApiClient
// (only global fetch stubbed, quoting the served local models schema
// from src/agent_si/backend/local_connect.py:42).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { LocalModels } from "../LocalModels";
import type { LocalModelsDoc } from "../k07next2Api";

const SERVED_MODELS: LocalModelsDoc = [];

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
    if (String(input) === "/api/v1/local/models") {
      return jsonBody(SERVED_MODELS);
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

describe("k07next2 M-R-UX-6 local models over the real screen", () => {
  it("renders the served empty model list", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocalModels />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-local-models");
    expect(seen).toContain("/api/v1/local/models");
    expect(screen.getByText(en.settings.localbench.modelsTitle)).toBeTruthy();
    expect(screen.getByText(en.settings.localbench.modelsEmpty)).toBeTruthy();
  });
});
