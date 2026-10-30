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

function projectsOk(): Response {
  return jsonResponse(200, { projects: [] });
}

describe("LIVE0-03 bounded retry with backoff, no storm", () => {
  it("never retries a 4xx: one fetch, same error", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      return jsonResponse(404, { surprise: true });
    });
    await expect(new HttpApiClient().listProjects()).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
      status: 404,
    });
    expect(calls).toBe(1);
  });

  it("bounds server-error retries at 3 attempts with backoff delay", async () => {
    const at: number[] = [];
    vi.stubGlobal("fetch", async () => {
      at.push(Date.now());
      return jsonResponse(500, { surprise: true });
    });
    const started = Date.now();
    await expect(new HttpApiClient().listProjects()).rejects.toMatchObject({
      code: "CONTEXT_WRONG_CONTRACT_VERSION",
      status: 500,
    });
    const elapsed = Date.now() - started;
    expect(at).toHaveLength(3);
    expect(elapsed).toBeGreaterThanOrEqual(20);
  });

  it("recovers when a retry succeeds", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      if (calls < 3) {
        return jsonResponse(500, { surprise: true });
      }
      return projectsOk();
    });
    await expect(new HttpApiClient().listProjects()).resolves.toEqual([]);
    expect(calls).toBe(3);
  });

  it("shares one in-flight fetch across concurrent callers (no storm)", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      await new Promise((resolve) => {
        setTimeout(resolve, 20);
      });
      return projectsOk();
    });
    const client = new HttpApiClient();
    await expect(
      Promise.all([client.listProjects(), client.listProjects(), client.listProjects()]),
    ).resolves.toEqual([[], [], []]);
    expect(calls).toBe(1);
  });
});
