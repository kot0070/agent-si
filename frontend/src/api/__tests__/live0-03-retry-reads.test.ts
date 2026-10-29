/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "../client";

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function ledgerOk(): Response {
  return jsonResponse(200, {
    rows: [{ package_id: "pkg-1", agents: 1, peak_concurrency: 1, wall_time_s: 5 }],
  });
}

describe("LIVE0-03 bounded retry with backoff beyond listProjects", () => {
  it("a 500 project read retries at most 3 attempts with backoff delay", async () => {
    const at: number[] = [];
    vi.stubGlobal("fetch", async () => {
      at.push(Date.now());
      return jsonResponse(500, { surprise: true });
    });
    const started = Date.now();
    await expect(new HttpApiClient().readProject("p-1")).rejects.toMatchObject({
      code: "CONTEXT_WRONG_CONTRACT_VERSION",
      status: 500,
    });
    const elapsed = Date.now() - started;
    expect(at).toHaveLength(3);
    expect(elapsed).toBeGreaterThanOrEqual(20);
  });

  it("never retries a 4xx on other reads: one fetch, same error", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      return jsonResponse(404, { surprise: true });
    });
    await expect(new HttpApiClient().readProject("p-9")).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
      status: 404,
    });
    expect(calls).toBe(1);
  });

  it("a ledger read recovers when a retry succeeds", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      if (calls < 3) {
        return jsonResponse(500, { surprise: true });
      }
      return ledgerOk();
    });
    await expect(new HttpApiClient().readLedger("p-1")).resolves.toEqual([
      { package_id: "pkg-1", agents: 1, peak_concurrency: 1, wall_time_s: 5 },
    ]);
    expect(calls).toBe(3);
  });

  it("concurrent identical ledger reads share one in-flight fetch", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      await new Promise((resolve) => {
        setTimeout(resolve, 20);
      });
      return ledgerOk();
    });
    const client = new HttpApiClient();
    const expected = [[{ package_id: "pkg-1", agents: 1, peak_concurrency: 1, wall_time_s: 5 }]];
    await expect(
      Promise.all([client.readLedger("p-1"), client.readLedger("p-1"), client.readLedger("p-1")]),
    ).resolves.toEqual([expected[0], expected[0], expected[0]]);
    expect(calls).toBe(1);
  });

  it("a 500 agents-live read retries at most 3 attempts", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      return jsonResponse(500, { surprise: true });
    });
    await expect(new HttpApiClient().listAgentsLive()).rejects.toMatchObject({
      code: "CONTEXT_WRONG_CONTRACT_VERSION",
      status: 500,
    });
    expect(calls).toBe(3);
  });
});
