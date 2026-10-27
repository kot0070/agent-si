/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";
import { CONTEXT_SOURCE, contextUsage } from "../projectsApi";
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
        hard_limit: 85,
        spent: 10,
        reserved: 5,
        currency: "u-9",
      },
    },
    liveRows: [],
  });
}

describe.each([false, true])("context card (dark=%s)", (dark) => {
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

  it("shows served remaining/total 70/85 plus the serving source", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="cost" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("context-card")).toBeTruthy();
    expect((await screen.findByTestId("context-card")).textContent).toContain(
      en.projects.tokens.title,
    );
    expect((await screen.findByTestId("context-remaining")).textContent).toBe(
      "70",
    );
    expect((await screen.findByTestId("context-total")).textContent).toBe(
      "85",
    );
    expect((await screen.findByTestId("context-source")).textContent).toBe(
      "/api/v1/budget",
    );
  });

  it("derives the card only from the stored budget record", async () => {
    const client = fixtureClient();
    const stored = await client.readBudget("p-9");
    expect(contextUsage(stored)).toEqual({ remaining: 70, total: 85 });
    expect(CONTEXT_SOURCE).toBe("/api/v1/budget");
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="cost" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("context-remaining")).textContent).toBe(
      String(stored.hard_limit - stored.spent - stored.reserved),
    );
    expect((await screen.findByTestId("context-total")).textContent).toBe(
      String(stored.hard_limit),
    );
    expect((await screen.findByTestId("context-source")).textContent).toBe(
      CONTEXT_SOURCE,
    );
  });
});
