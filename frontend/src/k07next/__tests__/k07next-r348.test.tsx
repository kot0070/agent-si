/** @vitest-environment jsdom */
// K07NEXT R-348: the REAL RunsExplained over a fresh HttpApiClient
// (only global fetch replaced, quoting the served runs-explained
// schema from src/agent_si/http/k07next.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { RunsExplained } from "../RunsExplained";

const SERVED_EXPLAINED = {
  row: "R-348",
  sections: [{ key: "runs" }, { key: "codeTests" }, { key: "localTests" }],
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
    if (String(input) === "/api/v1/k07next/runs-explained") {
      return jsonBody(SERVED_EXPLAINED);
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

describe("k07next R-348 runs explained over the real screen", () => {
  it("renders runs versus code tests versus local tests", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RunsExplained />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-runs-explained");
    expect(screen.getByText(en.howItWorks.runs.title)).toBeTruthy();
    expect(screen.getByText(en.howItWorks.runs.body)).toBeTruthy();
    expect(screen.getByText(en.howItWorks.codeTests.title)).toBeTruthy();
    expect(screen.getByText(en.howItWorks.codeTests.body)).toBeTruthy();
    expect(screen.getByText(en.howItWorks.localTests.title)).toBeTruthy();
    expect(screen.getByText(en.howItWorks.localTests.body)).toBeTruthy();
  });
});
