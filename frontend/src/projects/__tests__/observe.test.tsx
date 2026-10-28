/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";
import { MatrixView } from "../observe/MatrixView";
import { HealthView } from "../observe/HealthView";
import { VerifierView } from "../observe/VerifierView";
import en from "../../locale/en.json";

function applyPhoneScheme(dark: boolean): void {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: 375,
  });
  const matchMedia = (query: string) => ({
    matches: query === "(prefers-color-scheme: dark)" && dark,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: matchMedia,
  });
}

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
    budgetByProject: {
      "p-9": {
        project_id: "p-9",
        hard_limit: 100,
        spent: 10,
        reserved: 5,
        currency: "u-9",
      },
    },
    routingWhyByDecision: {
      "d-9": {
        decision: { decision_id: "d-9", policy_ref: "pol-9" },
        assignments: [
          {
            decision_id: "d-9",
            role: "manager",
            provider_id: "prov-9",
            model: "mod-9",
          },
        ],
        snapshot: {
          decision_id: "d-9",
          snapshot_ref: "snap-9",
          captured_at: "t-9",
        },
        reason: {
          task_class: "tc-9",
          fit_basis: "stored reason nine",
          price_basis: "KNOWN",
          quality_basis: "MEASURED",
          rejected: ["r-1"],
        },
      },
    },
    liveRows: [
      { agent: "n-local", scope: "s-1", deliverable: "d-1", status: "RUNNING" },
      { agent: "n-cloud", scope: "s-2", deliverable: "d-2", status: "QUEUED" },
    ],
  });
}

describe.each([false, true])("observe views (dark=%s)", (dark) => {
  beforeEach(() => {
    resetLocaleForTests();
    setLocale("en");
    window.localStorage.clear();
    applyPhoneScheme(dark);
  });

  afterEach(() => {
    cleanup();
    resetLocaleForTests();
    window.localStorage.clear();
  });

  it("matrix renders served live rows and stays honest when empty", async () => {
    const client = fixtureClient();
    const rows = await client.listAgentsLive();
    const shown = render(<MatrixView rows={rows} />);
    expect(await shown.findByTestId("observe-matrix")).toBeTruthy();
    expect(
      (await shown.findByTestId("matrix-row-n-local")).textContent,
    ).toContain("s-1");
    expect(
      (await shown.findByTestId("matrix-row-n-cloud")).textContent,
    ).toContain("s-2");
    shown.unmount();
    cleanup();

    const empty = render(<MatrixView rows={[]} />);
    expect(await empty.findByText(en.agents.live.empty)).toBeTruthy();
    empty.unmount();
    cleanup();
  });

  it("health renders served ledger plus budget and stays honest when empty", async () => {
    const client = fixtureClient();
    const ledger = await client.readLedger("p-9");
    const budget = await client.readBudget("p-9");
    const shown = render(<HealthView ledger={ledger} budget={budget} />);
    expect((await shown.findByTestId("observe-health")).textContent).toContain(
      "pkg-9",
    );
    expect((await shown.findByTestId("observe-health")).textContent).toContain(
      "85",
    );
    shown.unmount();
    cleanup();

    const empty = render(
      <HealthView
        ledger={[]}
        budget={{
          project_id: "p-9",
          hard_limit: 100,
          spent: 10,
          reserved: 5,
          currency: "u-9",
        }}
      />,
    );
    expect(await empty.findByText(en.ui.table.empty)).toBeTruthy();
    empty.unmount();
    cleanup();
  });

  it("verifier renders the served routing evidence and stays honest when missing", async () => {
    const client = fixtureClient();
    const why = await client.readRoutingWhy("d-9");
    const shown = render(<VerifierView why={why} />);
    expect(
      (await shown.findByTestId("observe-verifier")).textContent,
    ).toContain("snap-9");
    expect(
      (await shown.findByTestId("verifier-assignment-0")).textContent,
    ).toContain("prov-9/mod-9 manager");
    shown.unmount();
    cleanup();

    const empty = render(<VerifierView why={null} />);
    expect(await empty.findByText(en.ui.table.empty)).toBeTruthy();
    empty.unmount();
    cleanup();
  });

  it("wires the observe views into the owned project views", async () => {
    const client = fixtureClient();
    const usage = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="ai-usage" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await usage.findByTestId("observe-matrix")).toBeTruthy();
    usage.unmount();
    cleanup();

    const cost = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="cost" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await cost.findByTestId("observe-health")).toBeTruthy();
    cost.unmount();
    cleanup();

    const routing = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="routing-decisions" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await routing.findByTestId("observe-verifier")).toBeTruthy();
    routing.unmount();
    cleanup();
  });
});
