/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createElement, useEffect } from "react";
import type { ReactElement } from "react";
import {
  ApiClientProvider,
  useApiClient,
  useCurrentProject,
} from "../../app/ApiClientProvider";
import { FakeApiClient, HttpApiClient } from "../client";
import { ENDPOINTS } from "../endpoints";
import { ApiError, apiErrorLocaleKey } from "../errors";
import type { ApiClient, ApiErrorCode } from "../iface";
import {
  exportProjectReport,
  readProjectOverview,
  readProjectRuns,
  readProjectTime,
  readWhyThisModel,
} from "../projectsApi";

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
  {
    code: "NO_ELIGIBLE_CANDIDATE",
    call: (client) => client.readRoutingWhy("d-2"),
  },
  { code: "MODALITY_MISMATCH", call: (client) => client.readRoutingWhy("d-3") },
  {
    code: "PROVIDER_UNEVIDENCED",
    call: (client) =>
      client.createProject({ name: "p-y", folder_ref: "f-y" }),
  },
  {
    code: "PRICE_UNKNOWN_EXPENSIVE",
    call: (client) => client.readRoutingWhy("d-4"),
  },
  { code: "BUDGET_SOFT_WARN", call: (client) => client.readBudget("p-1") },
  { code: "BUDGET_HARD_BLOCKED", call: (client) => client.readBudget("p-2") },
  {
    code: "PENDING_RECONCILIATION",
    call: (client) => client.readBudget("p-3"),
  },
  {
    code: "DUPLICATE_SETTLEMENT_REFUSED",
    call: (client) => client.readBudget("p-4"),
  },
  { code: "KB_VALIDATION_FAILED", call: (client) => client.readRoutingWhy("d-5") },
  {
    code: "KB_PROPOSAL_NOT_APPROVED",
    call: (client) => client.readRoutingWhy("d-6"),
  },
  { code: "KEY_SAVE_TIMEOUT", call: (client) => client.deleteProject("p-1") },
  {
    code: "CREDENTIAL_ENTRY_MISSING",
    call: (client) => client.deleteProject("p-2"),
  },
];

function okJson(): Response {
  return new Response(
    JSON.stringify({
      agents: [
        { agent: "a-1", scope: "s-1", deliverable: "d-1", status: "RUNNING" },
      ],
      rows: [
        { package_id: "pkg-1", agents: 1, peak_concurrency: 1, wall_time_s: 5 },
      ],
      row: { package_id: "pkg-1", agents: 1, peak_concurrency: 1, wall_time_s: 5 },
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
      projects: [{ project_id: "p-1", name: "n-1", created_at: "t-0" }],
      project: { project_id: "p-1", name: "n-1", created_at: "t-0" },
      tasks: [
        { task_id: "t-1", project_id: "p-1", title: "n-1", status: "QUEUED", created_at: "t-0" },
      ],
      task: { task_id: "t-1", project_id: "p-1", title: "n-1", status: "QUEUED", created_at: "t-0" },
      ok: true,
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

describe("http error codes", () => {
  it.each(ERROR_CALLS)(
    "code $code surfaces under its own condition",
    async ({ code, call }) => {
      failWith(code);
      const client = new HttpApiClient();
      await expect(call(client)).rejects.toMatchObject({ code });
    },
  );

  it("wraps a network failure as CONTEXT_MISSING", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("offline");
    });
    const client = new HttpApiClient();
    const error = await client.listProjects().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "CONTEXT_MISSING", status: 0 });
  });

  it("maps an error body without a code to CONTEXT_WRONG_CONTRACT_VERSION", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ surprise: true }), {
          status: 500,
          headers: { "content-type": "application/json" },
        }),
    );
    const client = new HttpApiClient();
    await expect(client.listProjects()).rejects.toMatchObject({
      code: "CONTEXT_WRONG_CONTRACT_VERSION",
      status: 500,
    });
  });
});

describe("endpoint reachability through the client entry", () => {
  it("reaches every ENDPOINTS entry", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      seen.push(String(url));
      return okJson();
    });
    const client = new HttpApiClient();
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
    const stream = client.openChatStream({
      project_id: "p-1",
      prompt_ref: "pr-1",
      stream_id: "s-1",
    });
    for await (const chunk of stream.chunks) {
      expect(chunk.stream_id).toBe("s-1");
      break;
    }
    await client.cancelChatStream("s-1");
    await client.readBudget("p-1");
    const keys = Object.keys(ENDPOINTS) as Array<keyof typeof ENDPOINTS>;
    expect(keys.length).toBe(11);
    for (const key of keys) {
      const prefix = (ENDPOINTS[key] as string).split("{id}")[0] ?? "";
      expect(seen.some((url) => url.includes(prefix))).toBe(true);
    }
  });

  it("streams server-sent chunks with the request stream id", async () => {
    const sse = [
      'data: {"stream_id":"other","delta":"hello ","done":false}',
      'data: {"stream_id":"other","delta":"world","done":true}',
    ].join("\n");
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(sse, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );
    const client = new HttpApiClient();
    const stream = client.openChatStream({
      project_id: "p-1",
      prompt_ref: "pr-1",
      stream_id: "s-9",
    });
    const deltas: string[] = [];
    let done = false;
    for await (const chunk of stream.chunks) {
      expect(chunk.stream_id).toBe("s-9");
      deltas.push(chunk.delta);
      done = chunk.done;
    }
    expect(deltas.join("")).toBe("hello world");
    expect(done).toBe(true);
  });
});

describe("provider wiring", () => {
  it("exposes the client and the current project through context", async () => {
    const client = new FakeApiClient({});
    function Probe(): ReactElement {
      const api = useApiClient();
      const current = useCurrentProject();
      useEffect(() => {
        current.select("p-1");
      }, [current]);
      return createElement(
        "span",
        null,
        api === client && current.projectId !== null ? "wired" : "waiting",
      );
    }
    render(
      createElement(ApiClientProvider, {
        client,
        children: createElement(Probe, null),
      }),
    );
    expect(await screen.findByText("wired")).toBeTruthy();
  });
});

describe("fake validation", () => {
  it("rejects malformed input with CONTEXT_WRONG_CONTRACT_VERSION", async () => {
    const client = new FakeApiClient({});
    await expect(
      client.createTask("p-1", { title: "", scope: [] }),
    ).rejects.toMatchObject({ code: "CONTEXT_WRONG_CONTRACT_VERSION" });
    await expect(client.readLedger("")).rejects.toMatchObject({
      code: "CONTEXT_WRONG_CONTRACT_VERSION",
    });
    expect(() =>
      client.openChatStream({ project_id: "p-1", prompt_ref: "x", stream_id: "" }),
    ).toThrow("CONTEXT_WRONG_CONTRACT_VERSION");
  });

  it("rejects unknown ids with CONTEXT_MISSING", async () => {
    const client = new FakeApiClient({});
    await expect(client.readProject("no-such")).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
    });
    await expect(client.readRoutingWhy("no-such")).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
    });
    await expect(client.readBudget("no-such")).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
    });
  });

  it("rejects invalid live rows on setLiveRows", async () => {
    const client = new FakeApiClient({});
    expect(() =>
      client.setLiveRows([
        { agent: "a-1", scope: "s-1", deliverable: "d-1", status: "QUEUED" },
        { agent: "broken", scope: "", deliverable: "", status: "NOPE" as never },
      ]),
    ).toThrow("CONTEXT_WRONG_CONTRACT_VERSION");
    expect(await client.listAgentsLive()).toHaveLength(2);
  });

  it("serves project views from fixture rows", async () => {
    const client = new FakeApiClient({});
    const overview = await readProjectOverview(client, "p-1");
    expect(overview.project.project_id).toBe("p-1");
    expect(overview.ledger.length).toBeGreaterThan(0);
    expect(overview.budget.project_id).toBe("p-1");
    const runs = await readProjectRuns(client, "p-1");
    expect(runs).toEqual(overview.ledger);
    const time = await readProjectTime(client, "p-1");
    expect(time[0]).toEqual({
      package_id: "pkg-1",
      wall_time_s: 60,
    });
    const why = await readWhyThisModel(client, "d-1");
    expect(why.reason).toBe("fb-1");
    const exported = await exportProjectReport(client, "p-1");
    expect(JSON.parse(exported)).toMatchObject({ format: "agent-si-report/1" });
  });

  it("maps every api error code to a locale key", () => {
    expect(apiErrorLocaleKey("SCOPE_OVERLAP")).toBe("api.error.scope_overlap");
    expect(apiErrorLocaleKey("CREDENTIAL_ENTRY_MISSING")).toBe(
      "api.error.credential_entry_missing",
    );
  });
});
