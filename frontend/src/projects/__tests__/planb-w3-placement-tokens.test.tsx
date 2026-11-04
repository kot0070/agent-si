// PLANB W3: the Cloud AI and Local AI tab rows join the same served
// token counts the Tokens tab shows (role + model), a local model's cost
// reads "costs nothing", and the price word is in the user's language.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectView } from "../ProjectView";
import type { PartRow } from "../../api/iface";

const CREATED_AT = "2026-01-01T00:00:00.000Z";

function liveRow(partial: Record<string, unknown>): PartRow {
  return {
    agent: "agent-1",
    scope: "s-1",
    deliverable: "part-1",
    status: "RETURNED",
    ...partial,
  } as PartRow;
}

function client(rows: PartRow[]): FakeApiClient {
  return new FakeApiClient({
    projects: [{ project_id: "p-9", name: "n-9", created_at: CREATED_AT }],
    tasksByProject: { "p-9": [] },
    ledgerByProject: { "p-9": [] },
    budgetByProject: {
      "p-9": { project_id: "p-9", hard_limit: 5, spent: 0, reserved: 0, currency: "u-9" },
    },
    liveRows: rows,
  });
}

function stubTelemetry(): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url.startsWith("/api/v1/analytics/telemetry")) {
        return new Response(
          JSON.stringify({
            project: { tasks: 1, audits: 0, tokens: 1700 },
            models: [],
            providers: [],
            roles: [
              { role: "director", model: "muse-glimmer:30b", calls: 1, tokens: 1234, cost: "UNAVAILABLE" },
              { role: "worker", model: "muse-spark", calls: 2, tokens: 466, cost: "UNAVAILABLE" },
            ],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
}

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

const LOCAL_ROW = liveRow({
  agent: "director-plan",
  placement: "LOCAL",
  role: "director",
  model: "muse-glimmer:30b",
  cost: "UNKNOWN",
});
const CLOUD_ROW = liveRow({
  agent: "worker-p1",
  placement: "CLOUD",
  role: "worker",
  model: "muse-spark",
  cost: "UNKNOWN",
});

describe("PLANB W3 placement rows", () => {
  it("local tab: tokens joined from the ledger, cost says it costs nothing", async () => {
    stubTelemetry();
    render(
      <ApiClientProvider client={client([LOCAL_ROW, CLOUD_ROW])}>
        <ProjectView projectId="p-9" view="local-ai" />
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId("place-row-director-plan");
    await vi.waitFor(() => {
      expect(row.textContent).toContain("1,234");
    });
    expect(row.textContent).not.toContain("UNAVAILABLE");
    expect(row.textContent).not.toContain("not known");
    expect(row.textContent).toContain("free: a local model costs nothing");
  });

  it("two rows of one role + model: the count sits on the first row only", async () => {
    stubTelemetry();
    const second = liveRow({
      agent: "worker-p2",
      placement: "CLOUD",
      role: "worker",
      model: "muse-spark",
      cost: "UNKNOWN",
    });
    render(
      <ApiClientProvider client={client([CLOUD_ROW, second])}>
        <ProjectView projectId="p-9" view="cloud-ai" />
      </ApiClientProvider>,
    );
    const first = await screen.findByTestId("place-row-worker-p1");
    await vi.waitFor(() => {
      expect(first.textContent).toContain("466");
    });
    const next = await screen.findByTestId("place-row-worker-p2");
    expect(next.textContent).not.toContain("466");
    expect(next.textContent).toContain("\u2014");
  });

  it("cloud tab: tokens joined, price word readable", async () => {
    stubTelemetry();
    render(
      <ApiClientProvider client={client([LOCAL_ROW, CLOUD_ROW])}>
        <ProjectView projectId="p-9" view="cloud-ai" />
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId("place-row-worker-p1");
    await vi.waitFor(() => {
      expect(row.textContent).toContain("466");
    });
    expect(row.textContent).not.toContain("UNAVAILABLE");
    expect(row.textContent).toContain("cost not known (no price)");
  });

  it("uk: local row reads in Ukrainian with tokens and zero cost", async () => {
    setLocale("uk");
    stubTelemetry();
    render(
      <ApiClientProvider client={client([LOCAL_ROW])}>
        <ProjectView projectId="p-9" view="local-ai" />
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId("place-row-director-plan");
    await vi.waitFor(() => {
      expect(row.textContent).toMatch(/1\D234/);
    });
    expect(row.textContent).not.toContain("НЕВІДОМО");
    expect(row.textContent).not.toContain("UNAVAILABLE");
    expect(row.textContent).toContain("безкоштовно: локальна модель нічого не коштує");
  });
});
