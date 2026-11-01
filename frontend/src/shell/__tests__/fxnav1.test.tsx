/** @vitest-environment jsdom */
// FXNAV1 nav proof: the REAL app shell holds only main entries under true
// names; the kept dev screens live under Settings > Diagnostics at
// /diagnostics/<name> (no aliases, no lane names). Only global fetch is
// stubbed (quoting the served schemas); the shell, router, sidebar labels
// and diagnostics screens are all real.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import type { SupportedLocale } from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { App } from "../../app/App";

const SERVED: Record<string, unknown> = {
  "/api/v1/projects": [],
  "/api/v1/app/locale-coverage": {
    row: "R-362",
    en_leaves: 299,
    uk_leaves: 299,
    parity: true,
    missing_in_uk: [],
    missing_in_en: [],
  },
  "/api/v1/app/telemetry-themes": {
    row: "M-P3-92",
    themes: ["dark", "light"],
    charts: "accessible",
    standard: "visual-standard",
    tokens_key: "telemetry.tokens",
    cost_key: "telemetry.cost",
  },
  "/api/v1/local/bench/check": {
    reachable: false,
    reason: "no gateway endpoint configured",
  },
  "/api/v1/analytics/telemetry": {
    metric_records: 3,
    telemetry_events: 5,
    totals: {},
    tasks: [],
    project: { tasks: null, audits: null },
    models: [],
    providers: [],
    unavailable: [],
  },
  "/api/v1/local/bench/history": [],
};

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url in SERVED) {
      return jsonBody(SERVED[url]);
    }
    throw new Error(`unexpected fetch ${url}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

const MAIN_LINKS = [
  "menu-chat",
  "menu-agents-live",
  "menu-projects",
  "menu-tasks",
  "menu-results",
  "menu-watcher",
  "menu-settings",
];

interface KeptRow {
  link: string;
  section: string;
  enHeading: string;
  ukHeading: string;
}

const KEPT_ROWS: KeptRow[] = [
  {
    link: "diagnostics-link-locale-coverage",
    section: "k07next-locale-coverage",
    enHeading: en.settings.general.title,
    ukHeading: uk.settings.general.title,
  },
  {
    link: "diagnostics-link-telemetry-themes",
    section: "k07next-telemetry-themes",
    enHeading: en.settings.appearance.title,
    ukHeading: uk.settings.appearance.title,
  },
  {
    link: "diagnostics-link-bench-check",
    section: "k07next2-bench-check",
    enHeading: en.settings.localbench.title,
    ukHeading: uk.settings.localbench.title,
  },
  {
    link: "diagnostics-link-telemetry",
    section: "k07next2-telemetry",
    enHeading: en.projects.ai_usage.title,
    ukHeading: uk.projects.ai_usage.title,
  },
  {
    link: "diagnostics-link-bench-history",
    section: "k07next3-bench-history",
    enHeading: en.projects.list.title,
    ukHeading: uk.projects.list.title,
  },
];

// Token-absence probe (mode:regex): session-token material must never render
// on the diagnostics flow. Usage counters ("Tokens") do not match: the
// pattern requires the session-write shape.
const SESSION_TOKEN_PATTERN = /session[-_ ]?token|token_ok|session-write/i;

describe("fxnav1 main navigation over the real app", () => {
  it("holds only main entries under unique labels with no k07next href", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    const sidebar = screen.getByTestId("sidebar");
    const anchors = Array.from(sidebar.querySelectorAll("a"));
    expect(
      anchors.map((anchor) => anchor.getAttribute("data-testid")).sort(),
    ).toEqual([...MAIN_LINKS].sort());
    for (const anchor of anchors) {
      expect(anchor.getAttribute("href")).not.toContain("k07next");
    }
    const labels = anchors.map((anchor) => (anchor.textContent ?? "").trim());
    expect(labels.every((label) => label.length > 0)).toBe(true);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("opens Settings > Diagnostics and renders each kept screen in en and uk", async () => {
    const locales: SupportedLocale[] = ["en", "uk"];
    for (const locale of locales) {
      cleanup();
      setLocale(locale);
      renderAppAt("/settings/diagnostics");
      expect(await screen.findByTestId("diagnostics-section")).toBeTruthy();
      for (const row of KEPT_ROWS) {
        fireEvent.click(screen.getByTestId(row.link));
        const section = await screen.findByTestId(row.section);
        expect(section.textContent).toContain(
          locale === "en" ? row.enHeading : row.ukHeading,
        );
        expect(document.body.textContent ?? "").not.toMatch(
          SESSION_TOKEN_PATTERN,
        );
        fireEvent.click(screen.getByTestId("menu-settings"));
        fireEvent.click(await screen.findByTestId("settings-link-diagnostics"));
        expect(screen.getByTestId(row.link)).toBeTruthy();
      }
      expect(document.body.textContent ?? "").not.toMatch(
        SESSION_TOKEN_PATTERN,
      );
    }
  });
});
