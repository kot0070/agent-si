// FXROLEPICK R7: the project AI usage tab reads real tokens and
// cost from the ledger, by model and by provider from the same
// ledger. Sections with no served data hide; the raw unavailable
// word never renders.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";

const CREATED_AT = "2026-01-01T00:00:00.000Z";

function fixtureClient(): FakeApiClient {
  return new FakeApiClient({
    projects: [{ project_id: "p-9", name: "n-9", created_at: CREATED_AT }],
    tasksByProject: { "p-9": [] },
    ledgerByProject: {
      "p-9": [
        { package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 },
      ],
    },
    liveRows: [],
  });
}

function stubTelemetry(doc: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url.startsWith("/api/v1/analytics/telemetry")) {
        return new Response(JSON.stringify(doc), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
}

const SERVED = {
  project: { tasks: 2, audits: 0, tokens: 25000 },
  models: [
    { model: "meta/m1", calls: 4, tokens: 20000, cost: 1.25 },
    { model: "local/m2", calls: 2, tokens: 5000, cost: "UNAVAILABLE" },
    { model: "ghost/m3", calls: 1, tokens: "UNAVAILABLE", cost: "UNAVAILABLE" },
  ],
  providers: [{ provider: "meta", calls: 4, tokens: 20000, cost: 1.25 }],
  source: "telemetry_store",
  unavailable: ["models.local/m2.cost", "models.ghost/m3.tokens"],
};

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("R7 project AI usage tab", () => {
  it("shows served tokens and cost totals plus per-model and per-provider rows", async () => {
    stubTelemetry(SERVED);
    render(
      <ApiClientProvider client={fixtureClient()}>
        <ProjectView projectId="p-9" view="ai-usage" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("usage-tokens-total")).toBeTruthy();
    expect(screen.getByTestId("usage-tokens-total").textContent).toContain("25,000");
    expect(screen.getByTestId("usage-cost-total").textContent).toContain("1.25");
    expect(await screen.findByTestId("usage-models")).toBeTruthy();
    expect(await screen.findByTestId("usage-providers")).toBeTruthy();
    expect(screen.getByTestId("usage-model-row-0").textContent).toContain("meta/m1");
    expect(screen.getByTestId("usage-provider-row-0").textContent).toContain("meta");
    expect(screen.queryByText("ghost/m3")).toBeNull();
    expect(screen.queryByText("НЕДОСТУПНО")).toBeNull();
  });

  it("hides sections with no served data", async () => {
    stubTelemetry({ project: { tasks: null, audits: null, tokens: null }, models: [], providers: [] });
    render(
      <ApiClientProvider client={fixtureClient()}>
        <ProjectView projectId="p-9" view="ai-usage" />
      </ApiClientProvider>,
    );
    await screen.findByTestId("usage-agents-total");
    expect(screen.queryByTestId("usage-tokens-total")).toBeNull();
    expect(screen.queryByTestId("usage-cost-total")).toBeNull();
    expect(screen.queryByTestId("usage-models")).toBeNull();
    expect(screen.queryByTestId("usage-providers")).toBeNull();
    expect(screen.queryByText("НЕДОСТУПНО")).toBeNull();
  });
});
