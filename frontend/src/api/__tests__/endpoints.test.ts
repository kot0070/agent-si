/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ENDPOINTS } from "../endpoints";
import type { EndpointKey } from "../endpoints";
import { requestJson } from "../errors";
import {
  listAgentsLiveRows,
  parseAgentsLive,
} from "../agentsApi";
import {
  cancelChatStreamRequest,
  createProjectRecord,
  createTaskRecord,
  deleteProjectRecord,
  exportProjectReport,
  listProjectRecords,
  listTaskRecords,
  readBudgetState,
  readLedgerRows,
  readPackageReport,
  readProjectOverview,
  readProjectRecord,
  readRoutingWhyDetail,
  readTaskRecord,
  readWhyThisModel,
  updateProjectRecord,
} from "../projectsApi";
import { HttpApiClient } from "../client";
import { FakeApiClient } from "./fakeApiClient";

afterEach(() => {
  vi.unstubAllGlobals();
});

const FROZEN_TABLE: Record<EndpointKey, string> = {
  agentsLive: "/api/v1/agents/live",
  ledger: "/api/v1/runs/ledger",
  nextPackageNudge: "/api/v1/reports/next-package-nudge",
  routingWhy: "/api/v1/routing/decision/{id}/why",
  projects: "/api/v1/projects",
  projectById: "/api/v1/projects/{id}",
  tasks: "/api/v1/tasks",
  taskById: "/api/v1/tasks/{id}",
  chatStream: "/api/v1/chat/stream",
  chatCancel: "/api/v1/chat/cancel",
  budget: "/api/v1/budget",
};

const CONSUMERS: Record<EndpointKey, () => unknown> = {
  agentsLive: () => listAgentsLiveRows,
  ledger: () => readLedgerRows,
  nextPackageNudge: () => readPackageReport,
  routingWhy: () => readRoutingWhyDetail,
  projects: () => listProjectRecords,
  projectById: () => readProjectRecord,
  tasks: () => listTaskRecords,
  taskById: () => readTaskRecord,
  chatStream: () => HttpApiClient.prototype.openChatStream,
  chatCancel: () => cancelChatStreamRequest,
  budget: () => readBudgetState,
};

describe("endpoints registry", () => {
  it("matches the frozen table exactly", () => {
    expect({ ...ENDPOINTS }).toEqual(FROZEN_TABLE);
    expect(Object.keys(ENDPOINTS).sort()).toEqual(
      (Object.keys(FROZEN_TABLE) as Array<EndpointKey>).sort(),
    );
  });

  it("keeps every entry under /api/v1 with {id} only on detail routes", () => {
    const detail: Array<EndpointKey> = ["routingWhy", "projectById", "taskById"];
    for (const key of Object.keys(ENDPOINTS) as Array<EndpointKey>) {
      expect(ENDPOINTS[key].startsWith("/api/v1/")).toBe(true);
      expect(ENDPOINTS[key].includes("{id}")).toBe(detail.includes(key));
    }
  });

  it("maps every registry key to an api module consumer", () => {
    for (const key of Object.keys(FROZEN_TABLE) as Array<EndpointKey>) {
      expect(typeof CONSUMERS[key]).toBe("function");
      expect(CONSUMERS[key]()).toBeDefined();
    }
    expect(createProjectRecord).toBeDefined();
    expect(updateProjectRecord).toBeDefined();
    expect(deleteProjectRecord).toBeDefined();
    expect(createTaskRecord).toBeDefined();
    expect(readProjectOverview).toBeDefined();
    expect(exportProjectReport).toBeDefined();
    expect(parseAgentsLive).toBeDefined();
    expect(requestJson).toBeDefined();
  });

  it("reaches every template through the typed module calls", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      seen.push(String(url));
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
          task: { task_id: "t-1", project_id: "p-1", title: "n-1", status: "QUEUED", created_at: "t-0" },
          ok: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    });
    await listAgentsLiveRows();
    await readLedgerRows("p-1");
    await readPackageReport("pkg-1");
    await readRoutingWhyDetail("d-1");
    await listProjectRecords();
    await readProjectRecord("p-1");
    await createProjectRecord({ name: "n-1", folder_ref: "f-1" });
    await updateProjectRecord("p-1", { name: null });
    await deleteProjectRecord("p-1");
    await listTaskRecords("p-1");
    await readTaskRecord("t-1");
    await createTaskRecord("p-1", { title: "t-1", scope: ["s-1"] });
    const fake = new FakeApiClient({});
    await readWhyThisModel(fake, "d-1");
    await exportProjectReport(fake, "p-1");
    const http = new HttpApiClient();
    const stream = http.openChatStream({
      project_id: "p-1",
      prompt_ref: "pr-1",
      stream_id: "s-1",
    });
    for await (const chunk of stream.chunks) {
      expect(chunk.stream_id).toBe("s-1");
      break;
    }
    await cancelChatStreamRequest("s-1");
    await readBudgetState("p-1");
    for (const key of Object.keys(ENDPOINTS) as Array<EndpointKey>) {
      const prefix = ENDPOINTS[key].split("{id}")[0] ?? "";
      expect(seen.some((url) => url.includes(prefix))).toBe(true);
    }
  });
});
