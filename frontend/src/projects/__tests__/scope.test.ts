/** @vitest-environment jsdom */
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";
import { classifyScope } from "../scope";

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

describe("classifyScope", () => {
  it("marks a named served scope MUST", () => {
    expect(classifyScope("s-1")).toBe("MUST");
    expect(classifyScope("scope-1")).toBe("MUST");
  });

  it("marks a blank scope SHOULD", () => {
    expect(classifyScope("")).toBe("SHOULD");
    expect(classifyScope("   ")).toBe("SHOULD");
  });
});

describe.each([false, true])("scope labels on the served page (dark=%s)", (dark) => {
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

  it("renders the kind label next to the served scope string", async () => {
    const client = new FakeApiClient({
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
      liveRows: [
        {
          agent: "n-local",
          scope: "s-1",
          deliverable: "d-1",
          status: "RUNNING",
          placement: "LOCAL",
        },
      ],
    });
    render(
      createElement(ApiClientProvider, {
        client,
        children: createElement(ProjectView, {
          projectId: "p-9",
          view: "local-ai",
          decisionId: "d-9",
        }),
      }),
    );
    expect(
      (await screen.findByTestId("place-row-n-local")).textContent,
    ).toContain("n-local");
  });
});
