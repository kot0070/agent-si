/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../client";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import { App } from "../../app/App";
import { TopBar } from "../../shell/TopBar";

const TOKEN = "tok-k07f1b";
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
}

function captureFetch(
  respond: (url: string, init: SeenRequest) => Response | Promise<Response>,
): { seen: SeenRequest[] } {
  const seen: SeenRequest[] = [];
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const headers = { ...((init?.headers ?? {}) as Record<string, string>) };
    const record: SeenRequest = {
      url,
      method: (init?.method ?? "GET").toUpperCase(),
      headers,
    };
    seen.push(record);
    return respond(url, record);
  });
  return { seen };
}

function projectsListBody(): Response {
  return new Response(JSON.stringify({ projects: [] }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale("en");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearWindowToken();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("k07f1b session token behaviour", () => {
  it("sends both session headers on the first write from /projects", async () => {
    setWindowToken(TOKEN);
    let created: Array<{
      project_id: string;
      name: string;
      created_at: string;
    }> = [];
    const { seen } = captureFetch((url, init) => {
      if (url === "/api/v1/projects" && init.method === "POST") {
        created = [{ project_id: "p-9", name: "n-new", created_at: "t-0" }];
        return new Response(JSON.stringify({ project: created[0] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      if (url === "/api/v1/projects" && init.method === "GET") {
        return new Response(JSON.stringify({ projects: created }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      // Incidental reads fail fast: a 4xx never retries, so background
      // loads settle at once instead of bleeding retry fetches into
      // later tests' stubs.
      return new Response(
        JSON.stringify({ code: "FXK07F1B_UNEXPECTED_API" }),
        {
          status: 404,
          headers: { "content-type": "application/json" },
        },
      );
    });
    const router = createMemoryRouter([{ path: "*", element: <App /> }], {
      initialEntries: ["/projects"],
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    fireEvent.change(await screen.findByTestId("project-add-name"), {
      target: { value: "n-new" },
    });
    fireEvent.change(await screen.findByTestId("project-add-folder"), {
      target: { value: "f-new" },
    });
    fireEvent.click(await screen.findByTestId("project-add-submit"));
    // U13: create opens the new project at once; the row is visible
    // back on /projects after the shared-list refresh.
    await screen.findByTestId("chat-area");
    await router.navigate("/projects");
    await screen.findByTestId("project-row-p-9");

    const posts = seen.filter(
      (request) =>
        request.url === "/api/v1/projects" && request.method === "POST",
    );
    expect(posts.length).toBeGreaterThanOrEqual(1);
    const first = posts[0];
    expect(first).toBeDefined();
    if (first === undefined) {
      throw new Error("missing write POST");
    }
    expect(first.headers["x-ui-session-token"]).toBe(TOKEN);
    expect(first.headers["x-actor"]).toBe("ui");
    for (const request of seen) {
      expect(request.headers["Authorization"]).toBeUndefined();
      expect(request.headers["x-agent-si-actor"]).toBeUndefined();
    }
  });

  it("sends both session headers on the first chat stream call", async () => {
    setWindowToken(TOKEN);
    const { seen } = captureFetch((url) => {
      if (url === "/api/v1/chat/stream") {
        return new Response(
          'data: {"stream_id":"s-1","delta":"hi","done":true}\n',
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        );
      }
      return projectsListBody();
    });
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
    expect(stream.stream_id).toBe("s-1");
    expect(deltas).toEqual(["hi"]);

    const posts = seen.filter(
      (request) =>
        request.url === "/api/v1/chat/stream" && request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0]?.headers["x-ui-session-token"]).toBe(TOKEN);
    expect(posts[0]?.headers["x-actor"]).toBe("ui");
    for (const request of seen) {
      expect(request.headers["Authorization"]).toBeUndefined();
      expect(request.headers["x-agent-si-actor"]).toBeUndefined();
    }
  });

  it("maps error bodies to honest codes and statuses", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ surprise: true }), {
          status: 404,
          headers: { "content-type": "application/json" },
        }),
    );
    await expect(new HttpApiClient().listProjects()).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
      status: 404,
    });

    vi.stubGlobal("fetch", async () => {
      throw new TypeError("offline");
    });
    await expect(new HttpApiClient().listProjects()).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
      status: 0,
    });

    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ surprise: true }), {
          status: 500,
          headers: { "content-type": "application/json" },
        }),
    );
    await expect(new HttpApiClient().listProjects()).rejects.toMatchObject({
      code: "GENERIC_ERROR",
      status: 500,
    });
  });

  it("bounds projects retries and shares one in-flight fetch", async () => {
    let calls = 0;
    vi.stubGlobal("fetch", async () => {
      calls += 1;
      return new Response(JSON.stringify({ surprise: true }), {
        status: 404,
        headers: { "content-type": "application/json" },
      });
    });
    await expect(new HttpApiClient().listProjects()).rejects.toMatchObject({
      code: "CONTEXT_MISSING",
      status: 404,
    });
    expect(calls).toBe(1);

    let serverErrors = 0;
    vi.stubGlobal("fetch", async () => {
      serverErrors += 1;
      return new Response(JSON.stringify({ surprise: true }), {
        status: 500,
        headers: { "content-type": "application/json" },
      });
    });
    await expect(new HttpApiClient().listProjects()).rejects.toMatchObject({
      code: "GENERIC_ERROR",
      status: 500,
    });
    expect(serverErrors).toBeLessThanOrEqual(3);

    let okCalls = 0;
    vi.stubGlobal("fetch", async () => {
      okCalls += 1;
      return projectsListBody();
    });
    await expect(new HttpApiClient().listProjects()).resolves.toEqual([]);
    expect(okCalls).toBe(1);

    let sharedCalls = 0;
    vi.stubGlobal("fetch", async () => {
      sharedCalls += 1;
      await new Promise((resolve) => {
        setTimeout(resolve, 20);
      });
      return projectsListBody();
    });
    const client = new HttpApiClient();
    await expect(
      Promise.all([
        client.listProjects(),
        client.listProjects(),
        client.listProjects(),
      ]),
    ).resolves.toEqual([[], [], []]);
    expect(sharedCalls).toBe(1);
  });

  it("posts stop-all once with the token after arm plus confirm", async () => {
    setWindowToken(TOKEN);
    const { seen } = captureFetch((url) => {
      if (url === "/api/v1/stop-all") {
        // Accepted receipt shape (Stop-all posts {project_id} or {} plus
        // actor user and renders the Stopped N receipt, not a bare 200).
        return new Response(
          JSON.stringify({ accepted: true, stopped_count: 1 }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        );
      }
      return projectsListBody();
    });
    const router = createMemoryRouter([{ path: "*", element: <TopBar projectId="p-1" /> }], {
      initialEntries: ["/"],
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    fireEvent.click(await screen.findByTestId("topbar-stop-all"));
    fireEvent.click(await screen.findByTestId("topbar-stop-all"));
    const result = await screen.findByTestId("stop-all-result");
    expect(result.textContent).toContain("Stopped 1");

    const posts = seen.filter(
      (request) =>
        request.url === "/api/v1/stop-all" && request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0]?.headers["x-ui-session-token"]).toBe(TOKEN);
    expect(posts[0]?.headers["x-actor"]).toBe("ui");
    for (const request of seen) {
      expect(request.headers["Authorization"]).toBeUndefined();
      expect(request.headers["x-agent-si-actor"]).toBeUndefined();
    }
  });
});
