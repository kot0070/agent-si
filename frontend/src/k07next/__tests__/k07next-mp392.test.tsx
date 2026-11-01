/** @vitest-environment jsdom */
// K07NEXT M-P3-92: the REAL TelemetryThemes over a fresh HttpApiClient
// (only global fetch replaced, quoting the served telemetry-themes
// schema from src/agent_si/http/k07next.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { TelemetryThemes } from "../TelemetryThemes";

const SERVED_THEMES = {
  row: "M-P3-92",
  themes: ["dark", "light"],
  charts: "accessible",
  standard: "visual-standard",
  tokens_key: "telemetry.tokens",
  cost_key: "telemetry.cost",
};

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
  vi.stubGlobal("fetch", async (input: unknown) => {
    if (String(input) === "/api/v1/k07next/telemetry-themes") {
      return jsonBody(SERVED_THEMES);
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

describe("k07next M-P3-92 telemetry themes over the real screen", () => {
  it("renders dark plus light themes with accessible charts", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <TelemetryThemes />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-telemetry-themes");
    expect(screen.getByText(en.settings.appearance.title)).toBeTruthy();
    expect(screen.getByTestId("k07next-telemetry-list").textContent).toBe(
      "dark,light",
    );
    expect(screen.getByText(en.telemetry.tokens)).toBeTruthy();
    expect(screen.getByText(en.telemetry.cost)).toBeTruthy();
  });
});
