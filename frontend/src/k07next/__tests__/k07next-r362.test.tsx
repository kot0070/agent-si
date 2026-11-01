/** @vitest-environment jsdom */
// K07NEXT R-362: the REAL LocaleCoverage over a fresh HttpApiClient
// (only global fetch replaced, quoting the served locale-coverage
// schema from src/agent_si/http/k07next.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { LocaleCoverage } from "../LocaleCoverage";

const SERVED_COVERAGE = {
  row: "R-362",
  en_leaves: 190,
  uk_leaves: 190,
  parity: true,
  missing_in_uk: [],
  missing_in_en: [],
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  vi.stubGlobal("fetch", async (input: unknown) => {
    if (String(input) === "/api/v1/app/locale-coverage") {
      return jsonBody(SERVED_COVERAGE);
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

describe("k07next R-362 locale coverage over the real screen", () => {
  it("proves the served parity in English and Ukrainian", async () => {
    setLocale("en");
    const english = render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocaleCoverage />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-locale-coverage");
    expect(screen.getByText(en.settings.general.title)).toBeTruthy();
    expect(screen.getByTestId("k07next-locale-counts").textContent).toBe(
      "190:190",
    );
    expect(screen.getByTestId("k07next-locale-parity").textContent).toBe(
      "true",
    );
    english.unmount();
    cleanup();
    setLocale("uk");
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <LocaleCoverage />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-locale-coverage");
    expect(screen.getByText(uk.settings.general.title)).toBeTruthy();
    expect(screen.getByText(uk.empty.generic)).toBeTruthy();
  });
});
