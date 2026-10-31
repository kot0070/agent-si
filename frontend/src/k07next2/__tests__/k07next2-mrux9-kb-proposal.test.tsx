/** @vitest-environment jsdom */
// K07NEXT2 M-R-UX-9: the REAL KbRefreshProposal over a fresh HttpApiClient
// (only global fetch stubbed, quoting the served kb refresh schema from
// src/agent_si/backend/app.py:1579).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { KbRefreshProposal } from "../KbRefreshProposal";

const SERVED_PROPOSAL = { kb_id: null, stale: false, proposals: [] };

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
    if (String(input) === "/api/v1/kb/refresh/proposal") {
      return jsonBody(SERVED_PROPOSAL);
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

describe("k07next2 M-R-UX-9 kb proposal over the real screen", () => {
  it("renders the served empty proposal list", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <KbRefreshProposal />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-kb-proposal");
    expect(seen).toContain("/api/v1/kb/refresh/proposal");
    expect(screen.getByText(en.firstrun.optional.kbs)).toBeTruthy();
    expect(screen.getByText(en.ui.table.empty)).toBeTruthy();
  });
});
