/** @vitest-environment jsdom */
// FXWIRE1 shell proof: the REAL app shell wires every MOUNT row.
// Only global fetch is stubbed (quoting the served schemas); the shell,
// router, sidebar labels and k07next screens are all real. RED shape:
// before the FXWIRE1 shell wiring the menu links and routes do not
// exist, so every click below stays on the chat-first screen.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { App } from "../App";

const SERVED: Record<string, unknown> = {
  "/api/v1/projects": [],
  "/api/v1/app/locale-coverage": {
    row: "R-362",
    en_leaves: 193,
    uk_leaves: 193,
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
  "/api/v1/teststage/tests-view?plan_id=k07next3&run_id=seed": {
    plan_id: "k07next3",
    run_id: "seed",
    active: 0,
    passed: 0,
    remaining: 0,
    rows: [],
    settings_controls: [],
  },
  "/api/v1/app/session-write": {
    row: "LIVE0-08",
    token_ok: true,
    actor: "ui",
  },
  "/api/v1/app/page-shell": {
    row: "LIVE0B-04",
    title_key: "shell.sidebar.projects",
    title: "Projects",
    console_class: "agent-si-console",
  },
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

function renderShell(): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: ["/"],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

interface MountRow {
  link: string;
  section: string;
  heading: string;
}

const MOUNT_ROWS: MountRow[] = [
  {
    link: "menu-k07next-locale-coverage",
    section: "k07next-locale-coverage",
    heading: en.settings.general.title,
  },
  {
    link: "menu-k07next-telemetry-themes",
    section: "k07next-telemetry-themes",
    heading: en.settings.appearance.title,
  },
  {
    link: "menu-k07next2-bench-check",
    section: "k07next2-bench-check",
    heading: en.settings.localbench.title,
  },
  {
    link: "menu-k07next2-telemetry",
    section: "k07next2-telemetry",
    heading: en.projects.ai_usage.title,
  },
  {
    link: "menu-k07next3-bench-history",
    section: "k07next3-bench-history",
    heading: en.projects.list.title,
  },
  {
    link: "menu-k07next3-tests-view",
    section: "k07next3-tests-view",
    heading: en.settings.localAi.title,
  },
  {
    link: "menu-k07next4-session-token",
    section: "k07next4-session-token",
    heading: en.chat.composer.send,
  },
  {
    link: "menu-k07next4-page-shell",
    section: "k07next4-page-shell",
    heading: en.shell.sidebar.projects,
  },
];

describe("fxwire1 shell reachability over the real app", () => {
  it("starts chat-first with every MOUNT link visible", async () => {
    renderShell();
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    for (const row of MOUNT_ROWS) {
      expect(screen.getByTestId(row.link)).toBeTruthy();
    }
  });

  it("clicks each MOUNT link from the first screen to its real screen", async () => {
    renderShell();
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    for (const row of MOUNT_ROWS) {
      fireEvent.click(screen.getByTestId(row.link));
      const section = await screen.findByTestId(row.section);
      expect(section.textContent).toContain(row.heading);
      fireEvent.click(screen.getByTestId("menu-chat"));
      expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    }
  });
});
