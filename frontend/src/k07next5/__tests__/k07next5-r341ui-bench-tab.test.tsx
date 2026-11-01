/** @vitest-environment jsdom */
// K07NEXT5 R-341-UI: the REAL BenchSettingsTab over a fresh HttpApiClient
// (only global fetch replaced, quoting the served bench tab schema
// from src/agent_si/http/k07next5.py bench_tab).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { BenchSettingsTab } from "../BenchSettingsTab";

const BENCH_TAB_URL =
  "/api/v1/app/bench/tab" +
  "?model_id=k07next5-bench-b&level=Quick&pc_in_use=1";

const SERVED_BENCH_TAB = {
  row: "R-341-UI",
  scan: [],
  estimate: {
    model_id: "k07next5-bench-b",
    level: "Quick",
    minutes_min: 10.0,
    minutes_max: 15.0,
  },
  warnings: [
    { code: "BENCH_DURATION", message: "takes about 10-15 minutes" },
    { code: "BENCH_PC_IN_USE", message: "do not use the PC" },
  ],
  results: [],
  results_by_model: {},
  history: [],
  gateway: { reachable: false },
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
    if (String(input) === BENCH_TAB_URL) {
      return jsonBody(SERVED_BENCH_TAB);
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

describe("k07next5 R-341-UI bench tab over the real screen", () => {
  it("renders estimate plus warnings plus per-model results", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <BenchSettingsTab />
      </ApiClientProvider>,
    );
    const tab = await screen.findByTestId("k07next5-bench-tab");
    expect(tab).toBeTruthy();
    expect(seen).toContain(BENCH_TAB_URL);
    expect(screen.getByText(en.settings.localbench.title)).toBeTruthy();
    expect(screen.getByText("k07next5-bench-b Quick 10-15")).toBeTruthy();
    expect(screen.getByText("BENCH_DURATION")).toBeTruthy();
    expect(screen.getByText("BENCH_PC_IN_USE")).toBeTruthy();
    expect(
      screen.getByText(`${en.settings.localbench.resultsTitle}: 0`),
    ).toBeTruthy();
  });
});
