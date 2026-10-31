/** @vitest-environment jsdom */
// K07NEXT3 LIVE0-03: the REAL BenchHistoryList over a fresh HttpApiClient
// (only global fetch replaced, quoting the served bench history schema
// from src/agent_si/backend/localbench_routes.py:219).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { BenchHistoryList } from "../BenchHistoryList";

const SERVED_HISTORY: string[] = [];

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
    if (String(input) === "/api/v1/local/bench/history") {
      return jsonBody(SERVED_HISTORY);
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

describe("k07next3 LIVE0-03 bench history over the real screen", () => {
  it("renders the served empty history listing", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <BenchHistoryList />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next3-bench-history");
    expect(seen).toContain("/api/v1/local/bench/history");
    expect(screen.getByText(en.projects.list.title)).toBeTruthy();
    expect(screen.getByText(en.projects.list.empty)).toBeTruthy();
  });
});
