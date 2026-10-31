/** @vitest-environment jsdom */
// K07NEXT2 M-R-UX-10: the REAL RunsLedgerFresh over a fresh HttpApiClient
// (only global fetch stubbed, quoting the served runs ledger schema from
// src/agent_si/backend/app.py:131 for a fresh project).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { RunsLedgerFresh } from "../RunsLedgerFresh";
import type { RunsLedgerDoc } from "../k07next2Api";

const SERVED_LEDGER: RunsLedgerDoc = { rows: [] };
const LEDGER_URL = "/api/v1/runs/ledger?project_id=k07next2-fresh";

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
    if (String(input) === LEDGER_URL) {
      return jsonBody(SERVED_LEDGER);
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

describe("k07next2 M-R-UX-10 runs ledger over the real screen", () => {
  it("renders the served empty ledger for a fresh project", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RunsLedgerFresh />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next2-runs-ledger");
    expect(seen).toContain(LEDGER_URL);
    expect(screen.getByText(en.projects.runs.title)).toBeTruthy();
    expect(screen.getByText(en.ui.table.empty)).toBeTruthy();
  });
});
