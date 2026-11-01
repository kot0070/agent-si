/** @vitest-environment jsdom */
// K07NEXT3 LIVE0-02: the REAL BenchEstimateCard over a fresh HttpApiClient
// (only global fetch replaced, quoting the served bench estimate schema
// from src/agent_si/backend/localbench_routes.py:206).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { BenchEstimateCard } from "../BenchEstimateCard";

const SERVED_ESTIMATE = {
  level: "Quick",
  model_id: "k07next3-bench",
  minutes_min: 10.0,
  minutes_max: 15.0,
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
      String(input) ===
      "/api/v1/local/bench/estimate?model_id=k07next3-bench&level=Quick"
    ) {
      return jsonBody(SERVED_ESTIMATE);
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

describe("k07next3 LIVE0-02 bench estimate over the real screen", () => {
  it("renders the served estimate model and level", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <BenchEstimateCard />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next3-bench-estimate");
    expect(seen).toContain(
      "/api/v1/local/bench/estimate?model_id=k07next3-bench&level=Quick",
    );
    expect(screen.getByText(en.settings.localAi.title)).toBeTruthy();
    expect(screen.getByText("k07next3-bench")).toBeTruthy();
    expect(screen.getByText("Quick")).toBeTruthy();
  });
});
