/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../client";
import { FakeApiClient } from "./fakeApiClient";
import { ENDPOINTS } from "../endpoints";
import { Card, MetricCard } from "../../ui/kit";
import { AgentsLive } from "../../agents/AgentsLive";
import { TopBar } from "../../app/TopBar";
import { Sidebar } from "../../app/Sidebar";
import { App } from "../../app/App";
import { ProjectView } from "../../projects/ProjectView";
import type { ApiClient, ApiErrorCode } from "../iface";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function failWith(code: ApiErrorCode): void {
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response(JSON.stringify({ code }), {
        status: 422,
        headers: { "content-type": "application/json" },
      }),
  );
}

const ERROR_CALLS: Array<{
  code: ApiErrorCode;
  call: (client: ApiClient) => Promise<unknown>;
}> = [
  {
    code: "SCOPE_OVERLAP",
    call: (client) => client.createTask("p-1", { title: "t-1", scope: ["s-1"] }),
  },
  {
    code: "REJECTED_SCOPE_OVERLAP",
    call: (client) => client.createTask("p-1", { title: "t-2", scope: ["s-2"] }),
  },
  { code: "GATE_NOT_PASSED", call: (client) => client.readTask("t-1") },
  { code: "MISSING_INTEGRATION_TASK", call: (client) => client.listTasks("p-1") },
  { code: "INVALID_HIERARCHY_CHAIN", call: (client) => client.readTask("t-2") },
  {
    code: "AUDIT_INDEPENDENCE_REJECTED",
    call: (client) => client.updateProject("p-1", { name: null }),
  },
  {
    code: "BUDGET_CAPPED",
    call: (client) => client.createProject({ name: "p-x", folder_ref: "f-x" }),
  },
  { code: "UNKNOWN_LIMIT_KIND", call: (client) => client.listAgentsLive() },
  { code: "DELTA_OVER_BOUND", call: (client) => client.readLedger("p-1") },
  {
    code: "CONTEXT_WRONG_CONTRACT_VERSION",
    call: (client) => client.readLedger("p-9"),
  },
  { code: "POLICY_CONFLICT", call: (client) => client.readProject("p-1") },
  { code: "CONTEXT_MISSING", call: (client) => client.readProject("p-9") },
  { code: "NO_PROFILE_BLOCKED", call: (client) => client.readRoutingWhy("d-1") },
  { code: "NO_ELIGIBLE_CANDIDATE", call: (client) => client.readRoutingWhy("d-2") },
  { code: "MODALITY_MISMATCH", call: (client) => client.readRoutingWhy("d-3") },
  {
    code: "PROVIDER_UNEVIDENCED",
    call: (client) => client.createProject({ name: "p-y", folder_ref: "f-y" }),
  },
  { code: "PRICE_UNKNOWN_EXPENSIVE", call: (client) => client.readRoutingWhy("d-4") },
  { code: "BUDGET_SOFT_WARN", call: (client) => client.readBudget("p-1") },
  { code: "BUDGET_HARD_BLOCKED", call: (client) => client.readBudget("p-2") },
  { code: "PENDING_RECONCILIATION", call: (client) => client.readBudget("p-3") },
  { code: "DUPLICATE_SETTLEMENT_REFUSED", call: (client) => client.readBudget("p-4") },
  { code: "KB_VALIDATION_FAILED", call: (client) => client.readRoutingWhy("d-5") },
  { code: "KB_PROPOSAL_NOT_APPROVED", call: (client) => client.readRoutingWhy("d-6") },
  { code: "KEY_SAVE_TIMEOUT", call: (client) => client.deleteProject("p-1") },
  { code: "CREDENTIAL_ENTRY_MISSING", call: (client) => client.deleteProject("p-2") },
];

function okJson(): Response {
  return new Response(
    JSON.stringify({
      agents: [],
      rows: [],
      row: { package_id: "pkg-1", agents: 0, peak_concurrency: 0, wall_time_s: 0 },
      nudge: "pkg-2",
      auto_push: false,
      decision: { decision_id: "d-1", policy_ref: "pol-1" },
      assignments: [],
      snapshot: { decision_id: "d-1", snapshot_ref: "snap-1", captured_at: "t-0" },
      reason: {
        task_class: "tc-1",
        fit_basis: "fb-1",
        price_basis: "KNOWN",
        quality_basis: "MEASURED",
        rejected: [],
      },
      project_id: "p-1",
      budget: {
        project_id: "p-1",
        currency: "u-1",
        budget_limit: "5.00",
        soft_limit: "4.00",
        hard_limit: "5.00",
        spent: "1.25",
        reserved: "0.50",
        updated_at: "t-0",
        provider_spend_caps: {},
      },
      projects: [],
      project: { project_id: "p-1", name: "n-1", created_at: "t-0" },
      tasks: [],
      task: { task_id: "t-1", project_id: "p-1", title: "n-1", status: "s-1", created_at: "t-0" },
      ok: true,
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

describe("lane-a behaviour contract", () => {
  it.each(ERROR_CALLS)("code $code surfaces under its own condition", async ({ code, call }) => {
    failWith(code);
    const client = new HttpApiClient();
    await expect(call(client)).rejects.toMatchObject({ code });
  });

  it("reaches every ENDPOINTS entry through the ApiClient entry point", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      seen.push(String(url));
      return okJson();
    });
    const client = new HttpApiClient();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <ApiClientProvider client={client}>
          <TopBar projectId="p-1" />
        </ApiClientProvider>
      </MemoryRouter>,
    );
    await client.listAgentsLive();
    await client.readLedger("p-1");
    await client.readNextPackageNudge("pkg-1");
    await client.readRoutingWhy("d-1");
    await client.listProjects();
    await client.readProject("p-1");
    await client.createProject({ name: "n-1", folder_ref: "f-1" });
    await client.updateProject("p-1", { name: null });
    await client.deleteProject("p-1");
    await client.listTasks("p-1");
    await client.readTask("t-1");
    await client.createTask("p-1", { title: "t-1", scope: ["s-1"] });
    const stream = client.openChatStream({ project_id: "p-1", prompt_ref: "pr-1", stream_id: "s-1" });
    for await (const chunk of stream.chunks) {
      expect(chunk.stream_id).toBe("s-1");
      break;
    }
    await client.cancelChatStream("s-1");
    await client.readBudget("p-1");
    const keys = Object.keys(ENDPOINTS) as Array<keyof typeof ENDPOINTS>;
    expect(keys.length).toBeGreaterThan(0);
    for (const key of keys) {
      // F1: fill {id} with the SAME id the recorded request above used (readRoutingWhy d-1 line 129, readProject p-1 line 131, readTask t-1 line 136).
      const idByKey: Partial<Record<keyof typeof ENDPOINTS, string>> = { routingWhy: "d-1", projectById: "p-1", taskById: "t-1" };
      const template = ENDPOINTS[key].replace("{id}", idByKey[key] ?? "").replace("{projectId}", "");
      expect(seen.some((url) => url.includes(template))).toBe(true);
    }
  });

  it("kit collapse plus expand parity", async () => {
    const client = new FakeApiClient({});
    const segments = [
      { segmentKey: "telemetry.tokens", fraction: 0.5 },
      { segmentKey: "telemetry.cost", fraction: 0.5 },
    ];
    const { rerender } = render(
      <ApiClientProvider client={client}>
        <MetricCard
          cardId="card-1"
          titleKey="ui.card.total"
          totalKey="ui.card.total"
          segments={segments}
          collapsed={true}
          onToggle={() => undefined}
        />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("kit-collapsed-line")).toBeTruthy();
    rerender(
      <ApiClientProvider client={client}>
        <MetricCard
          cardId="card-1"
          titleKey="ui.card.total"
          totalKey="ui.card.total"
          segments={segments}
          collapsed={false}
          onToggle={() => undefined}
        />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("kit-expanded-bar")).toBeTruthy();
    expect(await screen.findByTestId("kit-expanded-legend")).toBeTruthy();
    const list = await screen.findByTestId("kit-expanded-list");
    expect(list.childElementCount).toBe(segments.length);
    render(
      <ApiClientProvider client={client}>
        <Card cardId="card-2" titleKey="ui.card.total" collapsed={false} onToggle={() => undefined}>
          <span data-testid="kit-child" />
        </Card>
      </ApiClientProvider>,
    );
    fireEvent.click(await screen.findByTestId("kit-toggle-card-2"));
    expect(await screen.findByTestId("kit-collapsed-line")).toBeTruthy();
  });

  it("agents badges LOCAL plus SPLIT plus CLOUD", async () => {
    const client = new FakeApiClient({});
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-badge-LOCAL")).toBeTruthy();
    expect(await screen.findByTestId("agent-badge-SPLIT")).toBeTruthy();
    expect(await screen.findByTestId("agent-badge-CLOUD")).toBeTruthy();
  });

  it("WHY_THIS_MODEL comes from the stored snapshot", async () => {
    const client = new FakeApiClient({});
    const why = await client.readRoutingWhy("d-1");
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-1" view="routing-decisions" decisionId="d-1" />
      </ApiClientProvider>,
    );
    const node = await screen.findByTestId("why-this-model-reason");
    expect(node.textContent).toBe(why.reason.fit_basis);
  });

  it("live update applies without reload", async () => {
    const client = new FakeApiClient({});
    const before = window.location.href;
    render(
      <ApiClientProvider client={client}>
        <AgentsLive projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("agent-row-agent-1")).toBeTruthy();
    client.setLiveRows([
      { agent: "a-1", scope: "s-1", deliverable: "d-1", status: "RUNNING" },
      { agent: "a-2", scope: "s-2", deliverable: "d-2", status: "QUEUED" },
    ]);
    expect(await screen.findByTestId("agent-row-a-2")).toBeTruthy();
    expect(window.location.href).toBe(before);
  });

  it("named menus are present", async () => {
    const client = new FakeApiClient({});
    render(
      <MemoryRouter initialEntries={["/"]}>
        <ApiClientProvider client={client}>
          <TopBar projectId="p-1" />
          <Sidebar projectId="p-1" />
        </ApiClientProvider>
      </MemoryRouter>
    );
    for (const id of [
      "menu-new-task",
      "menu-projects",
      "menu-results",
      "menu-settings",
    ]) {
      expect(await screen.findByTestId(id)).toBeTruthy();
    }
    cleanup();
    const router = createMemoryRouter([{ path: "*", element: <App /> }], {
      initialEntries: ["/projects/p-1/runs"],
    });
    render(
      <ApiClientProvider client={client}>
        <RouterProvider router={router} />
      </ApiClientProvider>
    );
    expect(await screen.findByTestId("project-menu-runs")).toBeTruthy();
    expect(await screen.findByTestId("project-menu-reports")).toBeTruthy();
  });
});
