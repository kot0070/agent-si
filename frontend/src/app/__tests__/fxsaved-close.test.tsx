/**
 * @vitest-environment jsdom
 * FXSAVED items 3 + 5 on the real page (fetch-boundary fake only):
 * stored project restores (ghost falls back to rows[0] and rewrites
 * the store); a live chat pump arms beforeunload, idle does not.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { App } from "../App";
import { hasLivePump } from "../../chat/index";
import { resetLocaleForTests, setLocale } from "../../locale/index";

function projectsBody(ids: string[]) {
  return {
    projects: ids.map((id) => ({
      project_id: id,
      name: `Name ${id}`,
      created_at: "2026-01-01T00:00:00Z",
    })),
  };
}

function programFetch(
  handler: (url: string, init: RequestInit) => unknown,
) {
  const mock = vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    return handler(url, init ?? {});
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function baseHandler(projectIds: string[]) {
  return (url: string, init: RequestInit) => {
    const method = (init?.method ?? "GET").toUpperCase();
    if (url === "/api/v1/projects" && method === "GET") {
      return ok(projectsBody(projectIds));
    }
    if (url.startsWith("/api/v1/routing/role") && method === "GET") {
      return {
        ok: false,
        status: 404,
        json: async () => ({ code: "ROLE_MISSING" }),
      };
    }
    if (url.startsWith("/api/v1/chat/history") && method === "GET") {
      return ok({ turns: [] });
    }
    if (url.startsWith("/api/v1/chat/models") && method === "GET") {
      return ok({ models: [] });
    }
    if (url === "/api/v1/providers" && method === "GET") {
      return ok({ providers: [] });
    }
    if (url === "/api/v1/agents/live" && method === "GET") {
      return ok({ agents: [] });
    }
    return ok({});
  };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("FXSAVED item 3: stored project pick restores", () => {
  it("shows the stored project, not rows[0]", async () => {
    programFetch(baseHandler(["p1", "p2"]));
    window.localStorage.setItem("agentsi.currentProjectId", "p2");
    renderAppAt("/");
    await waitFor(() => {
      expect(
        (screen.getByTestId("topbar-project") as HTMLSelectElement).value,
      ).toBe("p2");
    });
    expect(window.localStorage.getItem("agentsi.currentProjectId")).toBe(
      "p2",
    );
  });

  it("a ghost id falls back to rows[0] and rewrites the store", async () => {
    programFetch(baseHandler(["p1", "p2"]));
    window.localStorage.setItem("agentsi.currentProjectId", "ghost");
    renderAppAt("/");
    await waitFor(() => {
      expect(
        (screen.getByTestId("topbar-project") as HTMLSelectElement).value,
      ).toBe("p1");
    });
    expect(window.localStorage.getItem("agentsi.currentProjectId")).toBe(
      "p1",
    );
  });
});

describe("FXSAVED item 5: close warning follows the live pump", () => {
  it("idle page: beforeunload is not prevented", async () => {
    programFetch(baseHandler(["p1"]));
    renderAppAt("/");
    await screen.findByTestId("chat-statusline");
    expect(hasLivePump()).toBe(false);
    const event = new Event("beforeunload", { cancelable: true });
    const dispatched = window.dispatchEvent(event);
    expect(dispatched).toBe(true);
  });

  it("live stream: beforeunload is prevented until the run ends", async () => {
    const streamControl: {
      controller: ReadableStreamDefaultController<Uint8Array> | null;
    } = { controller: null };
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        streamControl.controller = c;
      },
    });
    programFetch((url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (url === "/api/v1/chat/stream" && method === "POST") {
        return new Response(stream, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      }
      return baseHandler(["p1"])(url, init);
    });
    renderAppAt("/");
    // ChatArea (not the pre-project ChatStartBox): the status line only
    // renders in the real chat surface once p1 is selected.
    await screen.findByTestId("chat-statusline");
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "fxsaved live run" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    await waitFor(() => {
      expect(hasLivePump()).toBe(true);
    });
    const held = new Event("beforeunload", { cancelable: true });
    expect(window.dispatchEvent(held)).toBe(false);
    const encoder = new TextEncoder();
    streamControl.controller?.enqueue(
      encoder.encode(
        'data: {"type":"start","stream_id":"srv-fx","run_id":"r-fx"}\n\n',
      ),
    );
    streamControl.controller?.enqueue(
      encoder.encode(
        'data: {"type":"done","stream_id":"srv-fx","run_id":"r-fx"}\n\n',
      ),
    );
    streamControl.controller?.close();
    await waitFor(() => {
      expect(hasLivePump()).toBe(false);
    });
    const free = new Event("beforeunload", { cancelable: true });
    expect(window.dispatchEvent(free)).toBe(true);
  });
});
