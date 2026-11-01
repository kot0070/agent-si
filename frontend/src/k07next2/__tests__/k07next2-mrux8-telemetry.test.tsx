/** @vitest-environment jsdom */
// K07NEXT2 M-R-UX-8: the REAL TelemetrySummary over a fresh HttpApiClient
// (only global fetch stubbed, quoting the served analytics schema from
// src/agent_si/backend/read_routes.py:300).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { TelemetrySummary } from "../TelemetrySummary";

const SERVED_TELEMETRY = {
  metric_records: 0,
  telemetry_events: 0,
  totals: {},
  tasks: [],
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
    if (String(input) === "/api/v1/analytics/telemetry") {
      return jsonBody(SERVED_TELEMETRY);
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

describe("k07next2 M-R-UX-8 telemetry over the real screen", () => {
  it("renders the served telemetry counters", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <TelemetrySummary />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-telemetry");
    expect(seen).toContain("/api/v1/analytics/telemetry");
    expect(screen.getByText(en.projects.ai_usage.title)).toBeTruthy();
    expect(screen.getByText(en.telemetry.tokens)).toBeTruthy();
    expect(screen.getByText(en.telemetry.cost)).toBeTruthy();
    expect(
      screen.getByTestId("k07next2-telemetry-metric-records").textContent,
    ).toBe("0");
    expect(screen.getByTestId("k07next2-telemetry-events").textContent).toBe(
      "0",
    );
  });
});
