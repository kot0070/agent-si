/** @vitest-environment jsdom */
// FXDESIGN2 S1-S4: the REAL App over a stubbed fetch (only global fetch is
// replaced; served schemas quoted from src/agent_si/backend/*). RED before
// the fix, GREEN after. S1 submit reads Create project via its own locale
// key; S2 kb card shows readable facts, never raw JSON; S3 context card and
// project form read real locale strings, never garble keys or English
// fallbacks on the uk screen; S4 has no lone why chip without per-model
// text while the per-model display stays mounted.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { App } from "../../app/App";

const PROJECT = { project_id: "p-1", name: "n-1", created_at: "t-0" };

const BUDGET = {
  project_id: "p-1",
  budget: {
    project_id: "p-1",
    hard_limit: 100,
    spent: 10,
    reserved: 5,
    currency: "u-1",
  },
};

const WHY = {
  decision: { decision_id: "d-9", policy_ref: "pol-9" },
  assignments: [
    { decision_id: "d-9", role: "manager", provider_id: "prov-9", model: "mod-9" },
  ],
  snapshot: { decision_id: "d-9", snapshot_ref: "snap-9", captured_at: "t-9" },
  reason: {
    task_class: "tc-9",
    fit_basis: "stored reason nine",
    price_basis: "KNOWN",
    quality_basis: "MEASURED",
    rejected: ["r-1"],
  },
};

const LIVE_UNKNOWN_COUNTS = {
  agents: [
    {
      agent: "agent-9",
      scope: "scope-9",
      deliverable: "part-9",
      status: "RUNNING",
      role: "worker",
    },
  ],
};

let liveAgents: unknown = { agents: [] };

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  liveAgents = { agents: [] };
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: { method?: string; body?: unknown }) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (url === "/api/v1/projects/p-1") {
        return jsonBody({ project: PROJECT });
      }
      if (url === "/api/v1/tasks?project_id=p-1") {
        return jsonBody({ tasks: [] });
      }
      if (url === "/api/v1/runs/ledger?project_id=p-1") {
        return jsonBody({ rows: [] });
      }
      if (url === "/api/v1/agents/live") {
        return jsonBody(liveAgents);
      }
      if (url === "/api/v1/budget?project_id=p-1") {
        return jsonBody(BUDGET);
      }
      if (url === "/api/v1/watcher/status?project_id=p-1") {
        return jsonBody({
          project_id: "p-1",
          integrity_ok: true,
          journal_head: "evt-0007",
          generated_at: "2026-10-27T00:00:00Z",
        });
      }
      if (url === "/api/v1/watcher/journal?project_id=p-1") {
        return jsonBody([
          { entry_id: "evt-0007", timestamp: "2026-10-27T00:00:00Z", hash: "h7" },
        ]);
      }
      if (url === "/api/v1/kb/status") {
        return jsonBody({
          overall: { kb_version: 3, last_update: "2026-10-27T00:00:00Z" },
          per_provider: { prov: "2026-10-26T00:00:00Z" },
        });
      }
      if (url === "/api/v1/kb/refresh/proposal") {
        return jsonBody({
          kb_id: "kb-1",
          stale: true,
          proposals: [{ proposal_id: "prop-1", field: "price", reason: "cheaper" }],
        });
      }
      if (url === "/api/v1/kb/update" && method === "POST") {
        return jsonBody({ applied: true, proposal_id: "kb-prop-1", kb_version: 8 });
      }
      if (url === "/api/v1/kb/proposals/apply" && method === "POST") {
        return jsonBody({ proposal_id: "kb-prop-1", applied: 5 });
      }
      if (url === "/api/v1/routing/decision/d-9/why") {
        return jsonBody(WHY);
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    },
  );
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

describe("fxdesign2 S1 project submit label", () => {
  it("reads Create project through its own locale key, never the task composer key", async () => {
    renderAppAt("/projects");
    // FXLOOK D3: the stub seeds one project, so the form folds behind
    // New project before the submit label can be read.
    fireEvent.click(await screen.findByTestId("project-add-open"));
    const submit = await screen.findByTestId("project-add-submit");
    expect(submit.textContent).toBe("Create project");
    expect(submit.textContent).not.toBe(t("tasks.creator.create"));
  });
});

describe("fxdesign2 S2 kb facts table", () => {
  it("shows kb facts as a readable table, zero raw JSON anywhere on the card", async () => {
    renderAppAt("/settings/capabilityDB");
    const card = await screen.findByTestId("k07next2-kb-proposal");
    expect(await screen.findByTestId("kb-status")).toBeTruthy();
    expect(screen.getByTestId("kb-status").textContent).toContain("overall");
    fireEvent.click(await screen.findByTestId("kb-update"));
    expect(await screen.findByTestId("kb-update-result")).toBeTruthy();
    expect(screen.getByTestId("kb-update-result").textContent).toContain(
      "kb-prop-1",
    );
    const text = card.textContent ?? "";
    expect(text).toContain("price");
    expect(text).not.toContain("{");
    expect(text).not.toContain("}");
    expect(text).not.toContain('"');
  });
});

describe("fxdesign2 S3 context card and project form locales", () => {
  it("renders dedicated context lines with real locale strings, never garble keys", async () => {
    liveAgents = LIVE_UNKNOWN_COUNTS;
    renderAppAt("/projects");
    const unknown = await screen.findByTestId("ctx-unknown");
    expect(unknown.getAttribute("title")).toBe(t("shell.common.unknown"));
    expect(screen.queryByTestId("ctx-percent")).toBeNull();
    expect(screen.queryByTestId("ctx-window")).toBeNull();
    const text = unknown.textContent ?? "";
    expect(text).not.toContain(t("shell.common.unknown"));
    expect(text).not.toContain("Used");
    expect(text).not.toContain("/");
    expect(text).not.toContain("shell.cards");
    expect(text).not.toContain("shell.common");
    expect(t("shell.cards.context.percentValue", { value: "v" })).toContain("v");
    expect(t("shell.cards.context.windowValue", { value: "v" })).toContain("v");
  });

  it("reads project name, folder and choose-folder from the uk locale", async () => {
    setLocale("uk");
    liveAgents = LIVE_UNKNOWN_COUNTS;
    renderAppAt("/projects");
    // FXLOOK D3: the stub seeds one project, so the form folds behind
    // New project before the uk labels can be read.
    fireEvent.click(await screen.findByTestId("project-add-open"));
    const form = await screen.findByTestId("project-add-form");
    const formText = form.textContent ?? "";
    expect(formText).toContain("Назва проєкту");
    expect(formText).toContain("Тека проєкту");
    expect(formText).toContain("Обрати теку");
    expect(formText).not.toContain("Project name");
    expect(formText).not.toContain("Choose folder");
    const unknown = await screen.findByTestId("ctx-unknown");
    expect(unknown.getAttribute("title")).toBe(t("shell.common.unknown"));
    expect(unknown.getAttribute("title")).toContain("НЕВІДОМО");
    expect(screen.queryByTestId("ctx-percent")).toBeNull();
    expect(screen.queryByTestId("ctx-window")).toBeNull();
    const text = unknown.textContent ?? "";
    expect(text).not.toContain("НЕВІДОМО");
    expect(text).not.toContain("Used");
    expect(text).not.toContain("/");
    expect(/[A-Za-z]/.test(text)).toBe(false);
  });
});

describe("fxdesign2 S4 why chip with per-model text", () => {
  it("pairs the why chip with a per-model explanation and keeps per-model rows", async () => {
    renderAppAt("/settings/general");
    const chip = await screen.findByTestId("settings-why-chip");
    expect(chip.textContent).toBe(t("projects.why_this_model.title"));
    const detail = await screen.findByTestId("settings-why-detail");
    expect((detail.textContent ?? "").length).toBeGreaterThan(0);
    expect(detail.textContent).toContain("model");
    cleanup();
    renderAppAt("/projects/p-1/models?decision=d-9");
    const row = await screen.findByTestId("model-row-0");
    expect(row.textContent).toContain("prov-9");
    expect(row.textContent).toContain("mod-9");
  });
});
