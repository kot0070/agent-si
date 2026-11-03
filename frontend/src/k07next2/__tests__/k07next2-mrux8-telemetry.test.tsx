/** @vitest-environment jsdom */
// FXROLEPICK R7: TelemetrySummary reads real tokens and cost from the
// ledger (never record counts), by model and by provider from the
// same doc. A section with no served data is hidden, never an
// unavailable paragraph.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { TelemetrySummary } from "../TelemetrySummary";

const SERVED_TELEMETRY = {
  project: { tasks: 2, audits: 1, tokens: 25000 },
  models: [
    { model: "meta/m1", calls: 3, tokens: 20000, cost: 1.5 },
    { model: "local/m2", calls: 2, tokens: 5000, cost: "UNAVAILABLE" },
    { model: "ghost/m3", calls: 1, tokens: "UNAVAILABLE", cost: "UNAVAILABLE" },
  ],
  providers: [
    { provider: "meta", calls: 3, tokens: 20000, cost: 1.5 },
    { provider: "local", calls: 2, tokens: 5000, cost: "UNAVAILABLE" },
  ],
  source: "telemetry_store",
  unavailable: ["models.ghost/m3.tokens", "models.ghost/m3.cost"],
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

describe("R7 telemetry summary over the real screen", () => {
  it("renders served tokens and cost totals plus per-model and per-provider rows", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <TelemetrySummary />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-telemetry");
    expect(seen).toContain("/api/v1/analytics/telemetry");
    expect(screen.getByText(en.projects.ai_usage.title)).toBeTruthy();
    expect(screen.getByTestId("k10an-tokens-total").textContent).toBe("25000");
    expect(screen.getByTestId("k10an-cost-total").textContent).toBe("1.5");
    expect(screen.getByTestId("k10an-model-section")).toBeTruthy();
    expect(screen.getByTestId("k10an-provider-section")).toBeTruthy();
    // Call-only rows carry no numbers and stay out.
    expect(screen.queryByText("ghost/m3")).toBeNull();
  });

  it("hides sections with no served data instead of unavailable text", async () => {
    vi.stubGlobal("fetch", async () => jsonBody({}));
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <TelemetrySummary />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-telemetry");
    expect(screen.queryByTestId("k10an-totals")).toBeNull();
    expect(screen.queryByTestId("k10an-model-section")).toBeNull();
    expect(screen.queryByTestId("k10an-provider-section")).toBeNull();
    expect(screen.queryByText(en.telemetry.unavailable)).toBeNull();
  });
});
