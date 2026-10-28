/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";

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
    ledgerByProject: { "p-9": [] },
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
          {
            decision_id: "d-9",
            role: "worker",
            provider_id: "prov-8",
            model: "mod-8",
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
    liveRows: [],
  });
}

describe.each([false, true])("routing WHY panel (dark=%s)", (dark) => {
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

  it("keeps why-this-model-reason equal to the stored fit_basis", async () => {
    const client = fixtureClient();
    const stored = await client.readRoutingWhy("d-9");
    render(
      <ApiClientProvider client={client}>
        <ProjectView
          projectId="p-9"
          view="routing-decisions"
          decisionId="d-9"
        />
      </ApiClientProvider>,
    );
    expect(
      (await screen.findByTestId("why-this-model-reason")).textContent,
    ).toBe(stored.reason.fit_basis);
  });

  it("shows version from the stored policy_ref", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView
          projectId="p-9"
          view="routing-decisions"
          decisionId="d-9"
        />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("why-version")).textContent).toContain(
      "pol-9",
    );
  });

  it("shows candidates from the stored assignments", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView
          projectId="p-9"
          view="routing-decisions"
          decisionId="d-9"
        />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("why-candidate-0")).textContent).toContain(
      "prov-9/mod-9 manager",
    );
    expect((await screen.findByTestId("why-candidate-1")).textContent).toContain(
      "prov-8/mod-8 worker",
    );
  });

  it("shows provenance from the stored snapshot_ref plus captured_at", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView
          projectId="p-9"
          view="routing-decisions"
          decisionId="d-9"
        />
      </ApiClientProvider>,
    );
    const provenance = (await screen.findByTestId("why-provenance"))
      .textContent;
    expect(provenance).toContain("snap-9");
    expect(provenance).toContain("t-9");
  });
});
