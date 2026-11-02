/** @vitest-environment jsdom */
// FXVIEWS RED-first: project tabs show served facts, never raw leaks.
// Network only (fetch stub or FakeApiClient); asserts behaviour.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";
import {
  buildRunRecords,
  buildTokenRows,
  changedFiles,
  dedupeLiveRows,
  formatServedDate,
  humanRunRef,
} from "../viewsApi";
import type { PartRow } from "../../api/iface";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

function liveRow(partial: Record<string, unknown>): PartRow {
  return {
    agent: "agent-1",
    scope: "s-1",
    deliverable: "part-1",
    status: "RUNNING",
    ...partial,
  } as PartRow;
}

describe("FXVIEWS viewsApi pure helpers", () => {
  it("strips fxdevrun and artifact prefixes to a human short ref", () => {
    expect(humanRunRef("fxdevrun:abc:part-2").text).toBe("part-2");
    expect(humanRunRef("fxdevrun:abc:part-2").title).toBe(
      "fxdevrun:abc:part-2",
    );
    expect(
      humanRunRef("artifact://run/r-1/dist/bundle.js").text,
    ).toBe("bundle.js");
    expect(humanRunRef("pkg-9").text).toBe("pkg-9");
    expect(humanRunRef("pkg-9").title).toBeUndefined();
  });

  it("formats ISO stamps to locale dates and keeps unparseable stamps raw", () => {
    const dated = formatServedDate("2026-01-01T00:00:00.000Z", "en");
    expect(dated).not.toContain("2026-01-01");
    expect(dated.length).toBeGreaterThan(0);
    expect(formatServedDate("t-9", "en")).toBe("t-9");
  });

  it("dedupes live attempts into one row per agent+role+model+status with a count", () => {
    const rows = dedupeLiveRows([
      liveRow({ agent: "a-1", status: "RUNNING" }),
      liveRow({ agent: "a-1", status: "RUNNING" }),
      liveRow({ agent: "a-1", status: "BLOCKED" }),
    ]);
    expect(rows).toHaveLength(2);
    const running = rows.find((row) => row.status === "RUNNING");
    expect(running?.attempts).toBe(2);
    const blocked = rows.find((row) => row.status === "BLOCKED");
    expect(blocked?.attempts).toBe(1);
  });

  it("sums served token cells per role+model and drops rows with no cells", () => {
    const rows = buildTokenRows(
      [
        liveRow({
          agent: "a-1",
          tokens: { input: 3, output: 4 },
          role: "worker",
          model: "mod-w",
        }),
        liveRow({
          agent: "a-2",
          tokens: { input: 1, output: 0 },
          role: "worker",
          model: "mod-w",
        }),
        liveRow({ agent: "a-3" }),
      ],
      null,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.tokens).toBe(8);
  });

  it("builds run records from served ledger rows and lists served changed files", () => {
    const records = buildRunRecords({
      ledger: [
        { package_id: "pkg-1", agents: 2, peak_concurrency: 1, wall_time_s: 60 },
      ],
      live: [liveRow({ file: "src/a.ts" }), liveRow({})],
      tasks: [],
      budget: {
        project_id: "p-1",
        hard_limit: 100,
        spent: 10,
        reserved: 5,
        currency: "u-1",
      },
    });
    expect(records).toHaveLength(1);
    expect(records[0]?.packageId).toBe("pkg-1");
    expect(records[0]?.wallTimeS).toBe(60);
    expect(changedFiles([liveRow({ file: "src/a.ts" }), liveRow({})])).toEqual([
      "src/a.ts",
    ]);
  });
});

describe("FXVIEWS tokens tab", () => {
  it("shows per-role+model token rows, never money, never raw routes", async () => {
    const client = new FakeApiClient({
      projects: [
        { project_id: "p-9", name: "n-9", created_at: "2026-01-01T00:00:00.000Z" },
      ],
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
        liveRow({
          agent: "w-1",
          scope: "s-1",
          deliverable: "fxdevrun:r-1:part-1",
          status: "RUNNING",
          role: "worker",
          model: "mod-w",
          tokens: { input: 30, output: 12 },
        }),
      ],
    });
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="tokens" />
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId("tokens-row-0");
    expect(row.textContent).toContain("worker");
    expect(row.textContent).toContain("mod-w");
    expect(row.textContent).toContain("42");
    expect(row.textContent).not.toContain("fxdevrun:");
    expect(row.textContent).not.toContain("/api/");
  });
});

describe("FXVIEWS cost tab", () => {
  it("names the budget limit as the total and keeps the served numbers", async () => {
    const client = new FakeApiClient({
      projects: [
        { project_id: "p-9", name: "n-9", created_at: "2026-01-01T00:00:00.000Z" },
      ],
      tasksByProject: { "p-9": [] },
      ledgerByProject: {
        "p-9": [
          { package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 },
        ],
      },
      budgetByProject: {
        "p-9": {
          project_id: "p-9",
          hard_limit: 5,
          spent: 0,
          reserved: 0,
          currency: "u-9",
        },
      },
    });
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="cost" />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("cost-limit")).textContent).toContain("5");
    expect((await screen.findByTestId("cost-limit")).textContent).toMatch(
      /limit/i,
    );
  });
});

describe("FXVIEWS cloud-ai tab", () => {
  it("dedupes attempts, says finished for passed rows, explains blocked rows", async () => {
    const client = new FakeApiClient({
      projects: [
        { project_id: "p-9", name: "n-9", created_at: "2026-01-01T00:00:00.000Z" },
      ],
      tasksByProject: { "p-9": [] },
      ledgerByProject: { "p-9": [] },
      budgetByProject: {
        "p-9": {
          project_id: "p-9",
          hard_limit: 5,
          spent: 0,
          reserved: 0,
          currency: "u-9",
        },
      },
      liveRows: [
        liveRow({
          agent: "c-done",
          scope: "s-1",
          status: "RETURNED",
          placement: "CLOUD",
          role: "worker",
          model: "mod-c",
          tokens: { input: 5, output: 5 },
        }),
        liveRow({
          agent: "c-done",
          scope: "s-1",
          status: "RETURNED",
          placement: "CLOUD",
          role: "worker",
          model: "mod-c",
          tokens: { input: 5, output: 5 },
        }),
        liveRow({
          agent: "c-stuck",
          scope: "s-2",
          status: "BLOCKED",
          placement: "CLOUD",
          role: "manager",
          model: "mod-m",
        }),
      ],
    });
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="cloud-ai" />
      </ApiClientProvider>,
    );
    const done = await screen.findByTestId("place-row-c-done");
    expect(done.textContent).toMatch(/finish/i);
    expect(done.textContent).toContain("2");
    expect(done.textContent).not.toMatch(/MUST.*Blocked|Blocked.*MUST/);
    const stuck = await screen.findByTestId("place-row-c-stuck");
    expect(stuck.textContent).toMatch(/block/i);
  });
});

describe("FXVIEWS advisor items 10/13/14", () => {
  function projectClient(): FakeApiClient {
    return new FakeApiClient({
      projects: [
        { project_id: "p-9", name: "n-9", created_at: "2026-01-01T00:00:00.000Z" },
      ],
      tasksByProject: {
        "p-9": [
          {
            task_id: "t-9",
            project_id: "p-9",
            title: "task nine",
            status: "RUNNING",
            created_at: "2026-01-01T00:00:00.000Z",
          },
        ],
      },
      ledgerByProject: {
        "p-9": [
          { package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 },
        ],
      },
      budgetByProject: {
        "p-9": {
          project_id: "p-9",
          hard_limit: 100,
          spent: 10,
          reserved: 5,
          currency: "u-9",
        },
      },
    });
  }

  it("item 13: every tab opens with a purpose line", async () => {
    for (const view of [
      "overview",
      "tasks",
      "runs",
      "time",
      "tokens",
      "cost",
      "local-ai",
      "cloud-ai",
      "models",
      "audits",
      "errors",
      "reports",
    ] as const) {
      const shown = render(
        <ApiClientProvider client={projectClient()}>
          <ProjectView projectId="p-9" view={view} />
        </ApiClientProvider>,
      );
      const purpose = await screen.findByTestId("tab-purpose");
      expect(purpose.textContent?.length).toBeGreaterThan(10);
      shown.unmount();
      cleanup();
    }
  });

  it("item 10: task rows stack title, chip and a localised date", async () => {
    render(
      <ApiClientProvider client={projectClient()}>
        <ProjectView projectId="p-9" view="tasks" />
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId("task-row-t-9");
    expect(row.textContent).toContain("task nine");
    expect(row.textContent).not.toContain("2026-01-01");
    expect(row.className).toContain("fxpv-task-row");
  });

  it("item 13+14: keyed Label-value fields and money with space plus currency", async () => {
    render(
      <ApiClientProvider client={projectClient()}>
        <ProjectView projectId="p-9" view="cost" />
      </ApiClientProvider>,
    );
    const spent = await screen.findByTestId("cost-spent");
    expect(spent.textContent).toContain(":");
    expect(spent.textContent).toContain("10 u-9");
    const limit = await screen.findByTestId("cost-limit");
    expect(limit.textContent).toContain("100 u-9");
  });

  it("item 14: XOR on tokens and a run record row on runs", async () => {
    const empty = render(
      <ApiClientProvider client={projectClient()}>
        <ProjectView projectId="p-9" view="tokens" />
      </ApiClientProvider>,
    );
    await screen.findByTestId("tab-purpose");
    expect(empty.container.textContent).not.toContain("tokens-spent");
    expect(empty.container.textContent).toContain("Nothing to show yet.");
    empty.unmount();
    cleanup();
    render(
      <ApiClientProvider client={projectClient()}>
        <ProjectView projectId="p-9" view="runs" />
      </ApiClientProvider>,
    );
    const record = await screen.findByTestId("runrecord-pkg-9");
    expect(record.textContent).toContain("90");
  });
});

describe("FXVIEWS raw leaks", () => {
  it("never renders ISO stamps, routes or key=value strings on overview", async () => {
    const client = new FakeApiClient({
      projects: [
        { project_id: "p-9", name: "n-9", created_at: "2026-01-01T00:00:00.000Z" },
      ],
      tasksByProject: { "p-9": [] },
      ledgerByProject: { "p-9": [] },
      budgetByProject: {
        "p-9": {
          project_id: "p-9",
          hard_limit: 5,
          spent: 0,
          reserved: 0,
          currency: "u-9",
        },
      },
    });
    const shown = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="overview" />
      </ApiClientProvider>,
    );
    const created = await screen.findByTestId("overview-created");
    expect(created.textContent).not.toContain("2026-01-01");
    expect(shown.container.textContent).not.toContain("/api/");
    expect(shown.container.textContent).not.toMatch(/[a-z_]+=\d+/);
  });

  it("marks the selected tab", async () => {
    render(
      <ApiClientProvider client={new FakeApiClient()}>
        <ProjectView projectId="p-1" view="cost" />
      </ApiClientProvider>,
    );
    const selected = await screen.findByTestId("project-menu-cost");
    expect(selected.getAttribute("aria-current")).toBe("true");
  });
});
