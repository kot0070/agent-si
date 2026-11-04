/** @vitest-environment jsdom */
// PLANB Z6 (DEFECT-41): project Details > Runs listed the Director of ANOTHER
// project (after its Stop all) in "Team". The live rows are served for every
// project; each carries its run id in the deliverable. The real RunHistory
// keeps only the rows of this project's runs. Fetch is the only fake.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { RunHistory } from "../RunHistory";

const MY_RUN = "3829831f3546456baaa49e3c4d932851";
const OTHER_RUN = "aaaa1111bbbb2222cccc3333dddd4444";

const RUN = {
  run_id: MY_RUN,
  start: "2026-11-02T10:14:00.000Z",
  end: "2026-11-02T10:15:11.000Z",
  parts: [{ part_id: "p1", verdict: "PASS", attempts: 1, reason: "checks green" }],
  verdicts: { p1: "PASS" },
  tokens: 100,
  cost: "UNKNOWN",
  files: ["add.js"],
  success: true,
  summary: "run success: all 1 parts PASS",
};

const LIVE = [
  { agent: "director-mine", status: "ACCEPTED", scope: "s", role: "director", deliverable: `artifact://run/${MY_RUN}/output` },
  { agent: "worker-mine", status: "ACCEPTED", scope: "s", role: "worker", deliverable: `artifact://run/${MY_RUN}/output` },
  { agent: "director-other", status: "BLOCKED", scope: "s", role: "director", deliverable: `artifact://run/${OTHER_RUN}/output` },
];

function jsonBody(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url.startsWith("/api/v1/runs/ledger")) {
      return jsonBody({ rows: [], runs: [RUN] });
    }
    if (url === "/api/v1/agents/live") {
      return jsonBody({ agents: LIVE });
    }
    return new Response("{}", { status: 404 });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
});

describe("PLANB Z6 team row is scoped to its project", () => {
  it("lists this project's agents, not another project's Director", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RunHistory projectId="p-mine" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("runhistory-part-director-mine")).toBeTruthy();
    expect(screen.getByTestId("runhistory-part-worker-mine")).toBeTruthy();
    expect(screen.queryByTestId("runhistory-part-director-other")).toBeNull();
  });
});
