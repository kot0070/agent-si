/** @vitest-environment jsdom */
// K07NEXT R-319: the REAL NewcomerGuide over a fresh HttpApiClient
// (only global fetch replaced, quoting the served newcomer-guide
// schema from src/agent_si/http/k07next.py).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { NewcomerGuide } from "../NewcomerGuide";

const SERVED_GUIDE = {
  row: "R-319",
  guide: "newcomer_start_guide",
  steps: [
    { id: "connectProvider" },
    { id: "oneClickTeam" },
    { id: "projectFolder" },
    { id: "firstTask" },
  ],
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
    if (String(input) === "/api/v1/app/newcomer-guide") {
      return jsonBody(SERVED_GUIDE);
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

describe("k07next R-319 newcomer guide over the real screen", () => {
  it("renders the served guide steps in order", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <NewcomerGuide />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next-newcomer-guide");
    expect(screen.getByText(en.firstrun.title)).toBeTruthy();
    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      en.firstrun.steps.connectProvider,
      en.firstrun.steps.oneClickTeam,
      en.firstrun.steps.projectFolder,
      en.firstrun.steps.firstTask,
    ]);
  });
});
