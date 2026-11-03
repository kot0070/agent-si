/** @vitest-environment jsdom */
// FXKBUPDATE K2/K3/K4: the rewritten KbRefreshProposal over stubbed fetch
// only (no network): version line, per-model result sentence, source
// link, up-to-date second click, file input + check-online controls,
// en + uk strings, never a raw code.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { KbRefreshProposal } from "../KbRefreshProposal";

const STATUS_V2 = {
  overall: {
    kb_version: 2,
    updated_at: "2026-11-02T21:55:00Z",
    total_changes: 13,
    last_source: "https://dev.meta.ai/docs",
  },
  per_provider: {
    meta: {
      models: 7,
      last_change_at: "2026-11-02T21:55:00Z",
      last_source: "https://dev.meta.ai/docs",
    },
  },
};

const STATUS_V3 = {
  overall: { ...STATUS_V2.overall, kb_version: 3 },
  per_provider: STATUS_V2.per_provider,
};

const STAGED = {
  staged: true,
  up_to_date: false,
  proposals: [
    {
      proposal_id: "kb-prop-9",
      provider_id: "meta",
      models: ["meta/muse-spark-1.3-contributor"],
      per_model: [
        {
          provider_id: "meta",
          model_id: "muse-spark-1.3-contributor",
          fields: 13,
        },
      ],
      changes: [
        {
          provider_id: "meta",
          model_id: "muse-spark-1.3-contributor",
          field: "cost_tier",
          old: "cheap-fast",
          new: "bulk-cheap",
          source: "https://dev.meta.ai/docs/pricing-rate-limits",
          retrieved_at: "2026-10-11",
        },
      ],
      added: [],
      source: "https://dev.meta.ai/docs",
      retrieved_at: "2026-11-02T21:55:00Z",
      shipped: false,
      fetched_from: null,
    },
  ],
  unavailable: [],
  message: "staged 1 provider update(s)",
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

let updateCalls = 0;

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url === "/api/v1/kb/status") {
        return jsonBody(updateCalls === 0 ? STATUS_V2 : STATUS_V3);
      }
      if (method === "GET" && url === "/api/v1/kb/refresh/proposal") {
        return jsonBody({ kb_id: null, stale: false, proposals: [] });
      }
      if (method === "POST" && url === "/api/v1/kb/update") {
        updateCalls += 1;
        if (updateCalls > 1) {
          return jsonBody({
            staged: false,
            up_to_date: true,
            proposals: [],
            unavailable: [],
            message: "already up to date",
          });
        }
        return jsonBody(STAGED);
      }
      if (method === "POST" && url === "/api/v1/kb/proposals/apply") {
        return jsonBody({
          proposal_id: "kb-prop-9",
          applied: true,
          version: 3,
          cost_state: "UNAVAILABLE",
          metric: null,
        });
      }
      if (method === "POST" && url === "/api/v1/kb/proposals/reject") {
        return jsonBody({ proposal_id: "kb-prop-9", rejected: true });
      }
      if (method === "POST" && url === "/api/v1/kb/check-online") {
        return jsonBody({
          checked_at: "2026-11-02T22:00:00Z",
          providers: [
            {
              provider_id: "meta",
              model_id: "muse-spark-1.3-contributor",
              stale: true,
              stale_reason: "older than 90 days",
              fetched: true,
              fetched_from: "https://dev.meta.ai/docs/models",
            },
          ],
          proposals: [STAGED.proposals[0]],
          skipped: [],
          up_to_date: false,
          message: "staged only, nothing applied",
        });
      }
      if (method === "POST" && url === "/api/v1/kb/file-proposal") {
        return jsonBody(STAGED.proposals[0]);
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    },
  );
}

function renderScreen(): void {
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <KbRefreshProposal />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  updateCalls = 0;
  window.localStorage.clear();
  window.sessionStorage.clear();
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxkbupdate kb screen over stubbed fetch", () => {
  it("shows the version line and per-provider rows from kb/status", async () => {
    renderScreen();
    await screen.findByTestId("kb-status");
    expect(screen.getByTestId("kb-status-line").textContent).toContain(
      "Version 2",
    );
    expect(screen.getByTestId("kb-status-line").textContent).toContain("meta");
  });

  it("update stages, applies and reads one result sentence with a source link", async () => {
    renderScreen();
    await screen.findByTestId("kb-status");
    fireEvent.click(screen.getByTestId("kb-update"));
    const result = await screen.findByTestId("kb-update-result");
    expect(result.textContent).toContain(
      "13 fields updated for muse-spark-1.3-contributor",
    );
    const link = result.querySelector("a");
    expect(link?.getAttribute("href")).toBe("https://dev.meta.ai/docs");
    expect(link?.textContent).toBe("dev.meta.ai");
    expect(await screen.findByText(/Version 3/)).toBeTruthy();
  });

  it("the second update click reads Already up to date, never a raw code", async () => {
    renderScreen();
    await screen.findByTestId("kb-status");
    fireEvent.click(screen.getByTestId("kb-update"));
    await screen.findByTestId("kb-update-result");
    fireEvent.click(screen.getByTestId("kb-update"));
    const again = await screen.findByText(en.settings.capabilityDb.upToDate);
    expect(again).toBeTruthy();
    const card = screen.getByTestId("k07next2-kb-proposal");
    expect(card.textContent).not.toContain("KB_");
  });

  it("exposes check-online plus from-file controls with apply and reject", async () => {
    renderScreen();
    await screen.findByTestId("kb-status");
    expect(screen.getByTestId("kb-check-online")).toBeTruthy();
    expect(screen.getByTestId("kb-from-file")).toBeTruthy();
    expect(screen.getByTestId("kb-file-input")).toBeTruthy();
    fireEvent.click(screen.getByTestId("kb-check-online"));
    await screen.findByTestId("kb-preview");
    expect(screen.getAllByTestId("kb-preview-apply").length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("kb-preview-reject").length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByTestId("kb-preview-apply")[0]);
    const result = await screen.findByTestId("kb-update-result");
    expect(result.textContent).toContain("muse-spark-1.3-contributor");
  });

  it("uk locale renders translated controls and the up-to-date line", async () => {
    setLocale("uk");
    renderScreen();
    await screen.findByTestId("kb-status");
    expect(screen.getByTestId("kb-update").textContent).toBe(
      uk.settings.capabilityDb.update,
    );
    expect(screen.getByTestId("kb-check-online").textContent).toBe(
      uk.settings.capabilityDb.checkOnline,
    );
    expect(screen.getByTestId("kb-from-file").textContent).toBe(
      uk.settings.capabilityDb.fromFile,
    );
    fireEvent.click(screen.getByTestId("kb-update"));
    await screen.findByTestId("kb-update-result");
    fireEvent.click(screen.getByTestId("kb-update"));
    expect(await screen.findByText(uk.settings.capabilityDb.upToDate)).toBeTruthy();
  });
});
