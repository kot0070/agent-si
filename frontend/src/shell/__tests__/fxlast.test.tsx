/** @vitest-environment jsdom */
// FXLAST: Stop-all is disabled with a reason when idle, enabled with a
// live run; arm+confirm posts the existing stop route exactly once.
// Real App render, fetch stubbed at the network boundary only.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";

const PROJECT = {
  project_id: "p1",
  name: "P1",
  created_at: "2026-02-11T06:42:44Z",
};

const RUNNING = [
  {
    agent: "worker-p1",
    scope: "s-1",
    deliverable: "d-1",
    status: "RUNNING",
    role: "worker",
    model: "muse-spark-1.3-contributor",
  },
];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

interface SeenRequest {
  url: string;
  method: string;
  body: string;
}

function stubFetch(liveRows: unknown[], seen: SeenRequest[]): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST" && url === "/api/v1/stop-all") {
        seen.push({
          url,
          method,
          body:
            typeof init?.body === "string" ? (init.body as string) : "{}",
        });
        return jsonBody({ accepted: true, stopped_count: 2 });
      }
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({ projects: [PROJECT] });
      }
      if (method === "GET" && url === "/api/v1/projects/p1") {
        return jsonBody({ project: PROJECT });
      }
      if (method === "GET" && url === "/api/v1/agents/live") {
        return jsonBody({ agents: liveRows });
      }
      if (method === "GET" && url === "/api/v1/kb/status") {
        return jsonBody({ kb_id: null });
      }
      if (method === "GET" && url === "/api/v1/kb/refresh/proposal") {
        return jsonBody({ kb_id: null, stale: false, proposals: [] });
      }
      return jsonBody({ code: "FXLAST_UNEXPECTED_API" }, 404);
    },
  );
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

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.locale", "en");
  setLocale("en");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxlast stop-all disabled when idle", () => {
  it("idle run state disables the button with a reason tooltip", async () => {
    stubFetch([], []);
    renderAppAt("/");
    const stop = await screen.findByTestId("topbar-stop-all");
    await waitFor(() => {
      expect((stop as HTMLButtonElement).disabled).toBe(true);
    });
    expect(stop.getAttribute("title")).toBe("No runs active");
    expect(stop.className).not.toMatch(/danger/);
    expect(stop.className).toMatch(/quiet/);
  });

  it("active run enables the button and turns it red", async () => {
    stubFetch(RUNNING, []);
    renderAppAt("/");
    const stop = await screen.findByTestId("topbar-stop-all");
    await waitFor(() => {
      expect(stop.className).toMatch(/danger/);
    });
    expect((stop as HTMLButtonElement).disabled).toBe(false);
    expect(stop.getAttribute("title")).toBeNull();
  });

  it("arm plus confirm posts the stop route exactly once", async () => {
    const seen: SeenRequest[] = [];
    stubFetch(RUNNING, seen);
    renderAppAt("/");
    const stop = await screen.findByTestId("topbar-stop-all");
    await waitFor(() => {
      expect((stop as HTMLButtonElement).disabled).toBe(false);
    });
    fireEvent.click(stop);
    fireEvent.click(stop);
    await screen.findByTestId("stop-all-result");
    const posts = seen.filter(
      (request) =>
        request.url === "/api/v1/stop-all" && request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0]?.body).toMatch(/"actor"\s*:\s*"user"/);
  });

  it("idle tooltip reads in uk under the uk locale", async () => {
    window.localStorage.setItem("agentsi.locale", "uk");
    setLocale("uk");
    stubFetch([], []);
    renderAppAt("/");
    const stop = await screen.findByTestId("topbar-stop-all");
    await waitFor(() => {
      expect((stop as HTMLButtonElement).disabled).toBe(true);
    });
    expect(stop.getAttribute("title")).toBe("Немає активних запусків");
  });
});
