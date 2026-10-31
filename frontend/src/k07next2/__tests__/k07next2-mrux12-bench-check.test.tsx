/** @vitest-environment jsdom */
// K07NEXT2 M-R-UX-12: the REAL BenchGatewayCheck over a fresh HttpApiClient
// (only global fetch stubbed, quoting the served bench check schema from
// src/agent_si/backend/localbench_routes.py:223).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { BenchGatewayCheck } from "../BenchGatewayCheck";

const SERVED_CHECK = {
  reachable: false,
  reason: "no gateway endpoint configured",
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
    if (String(input) === "/api/v1/local/bench/check") {
      return jsonBody(SERVED_CHECK);
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

describe("k07next2 M-R-UX-12 bench check over the real screen", () => {
  it("renders the served gateway check", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <BenchGatewayCheck />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-bench-check");
    expect(seen).toContain("/api/v1/local/bench/check");
    expect(screen.getByText(en.settings.localbench.title)).toBeTruthy();
    expect(
      screen.getByTestId("k07next2-bench-check-reachable").textContent,
    ).toBe("false");
    expect(
      screen.getByText("no gateway endpoint configured"),
    ).toBeTruthy();
  });
});
