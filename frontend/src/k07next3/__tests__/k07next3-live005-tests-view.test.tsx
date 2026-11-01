/** @vitest-environment jsdom */
// K07NEXT3 LIVE0-05: the REAL TestsViewBoard over a fresh HttpApiClient
// (only global fetch replaced, quoting the served tests view schema
// from src/agent_si/backend/read_routes.py:283).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { TestsViewBoard } from "../TestsViewBoard";

const SERVED_VIEW = {
  plan_id: "k07next3",
  run_id: "seed",
  active: 0,
  passed: 0,
  remaining: 0,
  rows: [],
  settings_controls: [],
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
    if (
      String(input) === "/api/v1/teststage/tests-view?plan_id=k07next3&run_id=seed"
    ) {
      return jsonBody(SERVED_VIEW);
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

describe("k07next3 LIVE0-05 tests view over the real screen", () => {
  it("renders the served plan and run ids", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <TestsViewBoard />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next3-tests-view");
    expect(seen).toContain(
      "/api/v1/teststage/tests-view?plan_id=k07next3&run_id=seed",
    );
    expect(screen.getByText(en.settings.localAi.title)).toBeTruthy();
    expect(screen.getByText("k07next3")).toBeTruthy();
    expect(screen.getByText("seed")).toBeTruthy();
  });
});
