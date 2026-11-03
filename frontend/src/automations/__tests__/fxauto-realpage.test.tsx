/** @vitest-environment jsdom */
// FXAUTO real page: the served Automations page renders on the real App
// route with the real state; fetch is faked only at the network boundary
// (stateful in-memory automation records, never injected into components).
// Runs in en and in uk.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { App } from "../../app/App";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import {
  CURRENT_PROJECT_STORAGE_KEY,
} from "../../app/ApiClientProvider";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";

const FIXED = "2026-02-11T19:25:00Z";

const PROJECT = {
  project_id: "p1",
  name: "P1",
  created_at: FIXED,
};

const PLAN_IDS = [
  "tpl-reread-3h",
  "tpl-checkpoint-30m",
  "tpl-resume-restart",
  "tpl-pause-90pct",
  "tpl-notify-audit-fail",
];

function planTemplate(id: string): Record<string, unknown> {
  const drafts: Record<string, Record<string, string>> = {
    "tpl-reread-3h": { when_kind: "schedule", when_detail: "every-3h", do: "reread-context" },
    "tpl-checkpoint-30m": { when_kind: "schedule", when_detail: "every-30m", do: "checkpoint" },
    "tpl-resume-restart": { when_kind: "event", when_detail: "app-started", do: "checkpoint" },
    "tpl-pause-90pct": { when_kind: "metric", when_detail: "budget-90", do: "pause-project" },
    "tpl-notify-audit-fail": { when_kind: "event", when_detail: "audit-failed", do: "notify" },
  };
  const draft = drafts[id] ?? { when_kind: "schedule", when_detail: "every-30m", do: "notify" };
  return {
    template_id: id,
    name: id,
    description: `${id} description`,
    trigger_key: "fxauto.chips.every30m",
    action_key: "fxauto.chips.notify",
    draft: { if_text: "", miss: "once", ...draft },
  };
}

const SIX = [
  "tpl-nightly",
  "tpl-healthcheck",
  "tpl-container-audit",
  "tpl-usage-report",
  "tpl-watch-sweep",
  "tpl-outage-drill",
];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

interface Store {
  rules: Array<Record<string, unknown>>;
  runs: Array<Record<string, unknown>>;
  checkpoints: Array<Record<string, unknown>>;
  approvals: Array<Record<string, unknown>>;
  globalPaused: boolean;
}

function stubFetch(store: Store): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      const query = (prefix: string): Record<string, string> => {
        const out: Record<string, string> = {};
        const at = url.indexOf("?");
        if (at === -1) {
          return out;
        }
        for (const part of url.slice(at + 1).split("&")) {
          const [key, value] = part.split("=");
          if (key !== undefined && value !== undefined) {
            out[key] = decodeURIComponent(value);
          }
        }
        void prefix;
        return out;
      };
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/automations/pause?")) {
        return jsonBody(store.globalPaused);
      }
      if (
        method === "GET" &&
        url.startsWith("/api/v1/automations/pause/project")
      ) {
        return jsonBody({ project_id: "p1", paused: false });
      }
      if (method === "POST" && url === "/api/v1/automations/pause") {
        const body = JSON.parse(String(init?.body ?? "{}")) as {
          paused?: boolean;
        };
        store.globalPaused = body.paused === true;
        return jsonBody({ paused: store.globalPaused });
      }
      if (method === "GET" && url.startsWith("/api/v1/automations/rules")) {
        return jsonBody({ rules: store.rules });
      }
      if (method === "POST" && url === "/api/v1/automations/rules") {
        const body = JSON.parse(String(init?.body ?? "{}")) as Record<
          string,
          unknown
        >;
        const rule = {
          rule_id: `rule-${store.rules.length + 1}`,
          name: body["name"],
          project_id: "p1",
          when_kind: body["when_kind"],
          when_detail: body["when_detail"],
          if_text: body["if_text"],
          do: body["do"],
          miss: body["miss"],
          enabled: true,
          next_run_at: FIXED,
          last_run_id: null,
        };
        store.rules.push(rule);
        return jsonBody({ rule });
      }
      if (
        method === "POST" &&
        /\/api\/v1\/automations\/rules\/[^/]+\/run$/.test(url)
      ) {
        if (store.globalPaused) {
          return jsonBody(
            { detail: { code: "AUTOMATION_PAUSED", detail: "automation paused" } },
            409,
          );
        }
        const run = {
          run_id: `run-${store.runs.length + 1}`,
          time: FIXED,
          rule: String(store.rules[0]?.["name"] ?? ""),
          state: "Running",
          result: { key: "fxauto.results.notified", params: { name: "n" } },
        };
        store.runs.push(run);
        return jsonBody({
          run,
          result: { key: "fxauto.results.notified", params: { name: "n" } },
          approval: null,
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/automations/runs")) {
        return jsonBody({ runs: store.runs });
      }
      if (method === "GET" && url === "/api/v1/automations/templates") {
        return jsonBody({
          templates: [...PLAN_IDS, ...SIX].map(planTemplate),
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/automations/checkpoints")) {
        return jsonBody({ checkpoints: store.checkpoints, latest: null });
      }
      if (method === "GET" && url.startsWith("/api/v1/automations/approvals")) {
        return jsonBody({ approvals: store.approvals });
      }
      if (url.startsWith("/api/v1/chat/history")) {
        if (method === "POST") {
          return jsonBody({ ok: true });
        }
        return jsonBody({ turns: [] });
      }
      if (url.startsWith("/api/v1/chat/models")) {
        return jsonBody({ project_id: "p1", models: [] });
      }
      if (url === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (url.startsWith("/api/v1/routing/role")) {
        return jsonBody({ error: "missing" }, 404);
      }
      if (url.startsWith("/api/v1/permissions/install-request")) {
        return jsonBody({ error: "missing" }, 404);
      }
      if (url === "/api/v1/permissions/check" && method === "POST") {
        return jsonBody({ allowed: true, asked_once: false });
      }
      if (url === "/api/v1/chat/decision" && method === "POST") {
        return jsonBody({ ok: true });
      }
      if (url.includes("/api/v1/chat/cancel")) {
        return jsonBody({ ok: true });
      }
      if (method === "GET" && url.startsWith("/api/v1/runs/ledger")) {
        return jsonBody({ rows: [], runs: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/tasks")) {
        return jsonBody({ tasks: [] });
      }
      if (method === "GET" && url.startsWith("/api/v1/budget")) {
        return jsonBody({ project_id: "p1", budget: null });
      }
      if (method === "GET" && url.startsWith("/api/v1/apps/card")) {
        return jsonBody({
          project_id: "p1",
          service_ids: [],
          paused: false,
          generated_at: FIXED,
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/watcher/status")) {
        return jsonBody({
          project_id: "p1",
          integrity_ok: true,
          journal_head: "evt-1",
          generated_at: FIXED,
        });
      }
      if (method === "GET" && url.startsWith("/api/v1/watcher/journal")) {
        return jsonBody([]);
      }
      void query;
      throw new Error(`fxauto unexpected fetch ${method} ${url}`);
    },
  );
}

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

function freshStore(): Store {
  return {
    rules: [],
    runs: [],
    checkpoints: [],
    approvals: [],
    globalPaused: false,
  };
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  window.localStorage.setItem(CURRENT_PROJECT_STORAGE_KEY, "p1");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe.each(["en", "uk"] as const)("fxauto real page (%s)", (locale) => {
  const table = locale === "en" ? en : uk;

  it("renders purpose, stop switches, empty rules and plan-first templates", async () => {
    window.localStorage.setItem("agentsi.locale", locale);
    setLocale(locale);
    stubFetch(freshStore());
    renderAppAt("/settings/automations");

    expect(await screen.findByTestId("automations-page")).toBeTruthy();
    expect(
      screen.getByText(
        (table as unknown as { fxauto: { purpose: string } }).fxauto.purpose,
      ),
    ).toBeTruthy();
    expect(screen.getByTestId("auto-global-stop")).toBeTruthy();
    expect(
      (screen.getByTestId("auto-global-stop") as HTMLInputElement).checked,
    ).toBe(false);
    expect(screen.getByTestId("auto-project-stop")).toBeTruthy();
    expect(screen.getByTestId("settings-group-watcher-automations"))
      .toBeTruthy();
    expect(screen.getByTestId("auto-rules-empty")).toBeTruthy();
    expect(screen.getByTestId("auto-goto-templates")).toBeTruthy();
    expect(screen.getByTestId("auto-new-rule")).toBeTruthy();
    const cards = document.querySelectorAll('[data-testid^="auto-template-"]');
    expect(cards.length).toBeGreaterThan(0);
    const first = screen.getByTestId("auto-template-tpl-reread-3h");
    expect(first.textContent ?? "").toContain("tpl-reread-3h");
    expect(screen.getByTestId("auto-history-empty")).toBeTruthy();
    expect(screen.getByTestId("auto-checkpoints-empty")).toBeTruthy();
  });

  it("creates a rule from the builder and runs it with a plain result", async () => {
    window.localStorage.setItem("agentsi.locale", locale);
    setLocale(locale);
    stubFetch(freshStore());
    renderAppAt("/settings/automations");
    await screen.findByTestId("auto-new-rule");

    fireEvent.click(screen.getByTestId("auto-new-rule"));
    fireEvent.change(screen.getByTestId("auto-builder-name"), {
      target: { value: "half-hour ping" },
    });
    fireEvent.click(screen.getByTestId("auto-builder-validate"));
    expect(
      await screen.findByTestId("auto-builder-message"),
    ).toBeTruthy();
    fireEvent.click(screen.getByTestId("auto-builder-save"));

    const card = await screen.findByTestId("auto-rule-rule-1");
    expect(card.textContent ?? "").toContain("half-hour ping");
    fireEvent.click(screen.getByTestId("auto-rule-rule-1-run"));
    const result = await screen.findByTestId("auto-rule-rule-1-result");
    expect(result.textContent ?? "").not.toContain("AUTOMATION");
    expect(result.textContent?.length ?? 0).toBeGreaterThan(0);
  });

  it("refuses Run now in plain words while the global stop is on", async () => {
    window.localStorage.setItem("agentsi.locale", locale);
    setLocale(locale);
    const store = freshStore();
    stubFetch(store);
    renderAppAt("/settings/automations");
    await screen.findByTestId("auto-new-rule");

    fireEvent.click(screen.getByTestId("auto-new-rule"));
    fireEvent.change(screen.getByTestId("auto-builder-name"), {
      target: { value: "half-hour ping" },
    });
    fireEvent.click(screen.getByTestId("auto-builder-save"));
    await screen.findByTestId("auto-rule-rule-1");

    fireEvent.click(screen.getByTestId("auto-global-stop"));
    await screen.findByTestId("auto-global-stop-state");
    fireEvent.click(screen.getByTestId("auto-rule-rule-1-run"));
    const result = await screen.findByTestId("auto-rule-rule-1-result");
    const refused = (
      table as unknown as { fxauto: { pausedRefused: string } }
    ).fxauto.pausedRefused;
    expect(result.textContent).toBe(refused);
  });
});
