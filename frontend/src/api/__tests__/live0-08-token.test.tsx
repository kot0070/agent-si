/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "../client";
import { requestResponse } from "../errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";

const TOKEN = "tok-live0-08";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

function setWindowToken(value: string): void {
  (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY] = value;
}

function clearWindowToken(): void {
  delete (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY];
}

interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
}

function captureFetch(respond: (seen: SeenRequest) => Response): { seen: SeenRequest[] } {
  const seen: SeenRequest[] = [];
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const headers = { ...((init?.headers ?? {}) as Record<string, string>) };
    const body = typeof init?.body === "string" ? init.body : "";
    const record: SeenRequest = {
      url,
      method: (init?.method ?? "GET").toUpperCase(),
      headers,
      body,
    };
    seen.push(record);
    return respond(record);
  });
  return { seen };
}

function expectTokenFromFirstCall(seen: SeenRequest[]): void {
  expect(seen.length).toBeGreaterThanOrEqual(1);
  for (const request of seen) {
    expect(request.url).not.toContain(TOKEN);
    expect(request.body).not.toContain(TOKEN);
    expect(request.headers["Authorization"]).toBeUndefined();
    expect(request.headers["x-agent-si-actor"]).toBeUndefined();
  }
  const first = seen[0];
  expect(first).toBeDefined();
  if (first === undefined) {
    throw new Error("missing request");
  }
  expect(first.headers["x-ui-session-token"]).toBe(TOKEN);
  expect(first.headers["x-actor"]).toBe("ui");
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearWindowToken();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("LIVE0-08 session token on every write path", () => {
  it("client write carries the token header on the bare first call", async () => {
    setWindowToken(TOKEN);
    const { seen } = captureFetch(() =>
      new Response(
        JSON.stringify({ project: { project_id: "p-9", name: "n-new", created_at: "t-0" } }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    await expect(
      new HttpApiClient().createProject({ name: "n-new", folder_ref: "f-new" }),
    ).resolves.toMatchObject({ project_id: "p-9" });
    const posts = seen.filter(
      (request) => request.url === "/api/v1/projects" && request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expectTokenFromFirstCall(posts);
  });

  it("chat stream carries the token header on the bare first call", async () => {
    setWindowToken(TOKEN);
    const { seen } = captureFetch(() =>
      new Response('data: {"stream_id":"s-1","delta":"hi","done":true}\n', {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = new HttpApiClient();
    const stream = client.openChatStream({
      project_id: "p-1",
      prompt_ref: "r-1",
      stream_id: "s-1",
    });
    const deltas: string[] = [];
    for await (const chunk of stream.chunks) {
      deltas.push(chunk.delta);
    }
    expect(deltas).toEqual(["hi"]);
    const posts = seen.filter(
      (request) => request.url === "/api/v1/chat/stream" && request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expectTokenFromFirstCall(posts);
  });

  it("stop-all style direct write carries the token header on the bare first call", async () => {
    setWindowToken(TOKEN);
    const { seen } = captureFetch(() =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const response = await requestResponse("/api/v1/stop-all", {
      method: "POST",
      kind: "write",
    });
    expect(response.status).toBe(200);
    const posts = seen.filter(
      (request) => request.url === "/api/v1/stop-all" && request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expectTokenFromFirstCall(posts);
  });
});
