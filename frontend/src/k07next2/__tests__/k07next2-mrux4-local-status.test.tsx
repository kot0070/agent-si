/** @vitest-environment jsdom */
// K07NEXT2 M-R-UX-4: the REAL LocalRuntimeStatus over a fresh HttpApiClient
// (only global fetch stubbed, quoting the served local status schema
// from src/agent_si/backend/local_connect.py:36).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { LocalRuntimeStatus } from "../LocalRuntimeStatus";

const SERVED_STATUS = {
  status: "NOT_CONFIGURED",
  reason: "capability base absent; routing continues normally",
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
    if (String(input) === "/api/v1/local/status") {
      return jsonBody(SERVED_STATUS);
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

describe("k07next2 M-R-UX-4 local status over the real screen", () => {
  it("renders the served runtime status and reason", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocalRuntimeStatus />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-local-status");
    expect(seen).toContain("/api/v1/local/status");
    expect(screen.getByText(en.settings.localAi.title)).toBeTruthy();
    expect(screen.getByText("NOT_CONFIGURED")).toBeTruthy();
    expect(
      screen.getByText("capability base absent; routing continues normally"),
    ).toBeTruthy();
  });
});
