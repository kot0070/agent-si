/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "../client";
import { ApiError, apiErrorLocaleKey, requestResponse } from "../errors";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
  delete (window as unknown as Record<string, unknown>).__AGENT_SI_UI_TOKEN;
});

describe("K07L0D3 LIVE0-02 honest 404 wording", () => {
  it("404 with contract-version code reads CONTEXT_MISSING", async () => {
    vi.stubGlobal("fetch", async () => json(404, { code: "CONTEXT_WRONG_CONTRACT_VERSION" }));
    const failure = await new HttpApiClient().listProjects().catch((e: unknown) => e);
    expect(failure).toMatchObject({ code: "CONTEXT_MISSING", status: 404 });
    expect((failure as ApiError).code).not.toBe("CONTEXT_WRONG_CONTRACT_VERSION");
    expect(apiErrorLocaleKey((failure as ApiError).code)).toBe("api.error.context_missing");
  });

  it("offline failure reads server-down CONTEXT_MISSING", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("offline");
    });
    const failure = await new HttpApiClient().listProjects().catch((e: unknown) => e);
    expect(failure).toMatchObject({ code: "CONTEXT_MISSING", status: 0 });
  });
});

describe("K07L0D3 LIVE0-03 bounded retry, no storm", () => {
  it("4xx never retries", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      return json(404, { surprise: true });
    });
    await expect(new HttpApiClient().listProjects()).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
      status: 404,
    });
    expect(calls).toBe(1);
  });

  it("500 retries at most 3 with backoff then recovers", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      if (calls < 3) return json(500, { surprise: true });
      return json(200, { projects: [] });
    });
    await expect(new HttpApiClient().listProjects()).resolves.toEqual([]);
    expect(calls).toBe(3);
  });

  it("ledger 500 retries at most 3 (beyond listProjects)", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      return json(500, { surprise: true });
    });
    await expect(new HttpApiClient().readLedger("p-1")).rejects.toMatchObject({
      status: 500,
    });
    expect(calls).toBe(3);
  });

  it("concurrent identical reads share one fetch", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      await new Promise((r) => setTimeout(r, 20));
      return json(200, { projects: [] });
    });
    const client = new HttpApiClient();
    await Promise.all([client.listProjects(), client.listProjects(), client.listProjects()]);
    expect(calls).toBe(1);
  });
});

describe("K07L0D3 LIVE0-08 token from first call", () => {
  it("write carries x-ui-session-token on the bare first call", async () => {
    (window as unknown as Record<string, unknown>).__AGENT_SI_UI_TOKEN = "tok-k07l0d3";
    const seen: Array<{ headers: Record<string, string> }> = [];
    vi.stubGlobal("fetch", async (_u: unknown, init?: RequestInit) => {
      seen.push({ headers: { ...((init?.headers ?? {}) as Record<string, string>) } });
      return json(200, { project: { project_id: "p-9", name: "n", created_at: "t-0" } });
    });
    await new HttpApiClient().createProject({ name: "n", folder_ref: "f" });
    expect(seen.length).toBeGreaterThanOrEqual(1);
    expect(seen[0]?.headers["x-ui-session-token"]).toBe("tok-k07l0d3");
    expect(seen[0]?.headers["x-actor"]).toBe("ui");
  });

  it("direct write via requestResponse carries the token", async () => {
    (window as unknown as Record<string, unknown>).__AGENT_SI_UI_TOKEN = "tok-k07l0d3";
    const seen: Array<{ headers: Record<string, string> }> = [];
    vi.stubGlobal("fetch", async (_u: unknown, init?: RequestInit) => {
      seen.push({ headers: { ...((init?.headers ?? {}) as Record<string, string>) } });
      return json(200, { ok: true });
    });
    await requestResponse("/api/v1/stop-all", { method: "POST", kind: "write" });
    expect(seen[0]?.headers["x-ui-session-token"]).toBe("tok-k07l0d3");
  });
});
