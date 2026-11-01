/** @vitest-environment jsdom */
// K07NEXT5 B0B-UNCOVERED_MVP_ACCEPT-199: the REAL ProviderOutageCard over a
// fresh HttpApiClient (only global fetch replaced, quoting the served
// provider health transitions schema from src/agent_si/http/k07next5.py
// provider_health_transitions).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { ProviderOutageCard } from "../ProviderOutageCard";

const TRANSITIONS_URL = "/api/v1/app/provider-health/transitions";

const SERVED_TRANSITIONS = {
  row: "B0B-UNCOVERED_MVP_ACCEPT-199",
  rows: [
    { registry: "ONLINE", service: "UP", reason: "" },
    { registry: "DEGRADED", service: "DEGRADED", reason: "" },
    { registry: "OFFLINE", service: "DOWN", reason: "" },
    { registry: "UNKNOWN", service: "DOWN", reason: "unknown-health" },
  ],
  transitions: ["UP", "DEGRADED", "DOWN", "DOWN"],
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
    if (String(input) === TRANSITIONS_URL) {
      return jsonBody(SERVED_TRANSITIONS);
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

describe("k07next5 MVP_ACCEPT-199 outage over the real screen", () => {
  it("renders the provider health transitions", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProviderOutageCard />
      </ApiClientProvider>,
    );
    const card = await screen.findByTestId("k07next5-provider-outage");
    expect(card).toBeTruthy();
    expect(seen).toContain(TRANSITIONS_URL);
    expect(screen.getByText(en.chat.stream.offline)).toBeTruthy();
    expect(screen.getByText("UP DEGRADED DOWN DOWN")).toBeTruthy();
  });
});
