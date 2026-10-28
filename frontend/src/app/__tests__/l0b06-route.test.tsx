/** @vitest-environment jsdom */
// L0B-06: the real / route mounts a working message box; typing a message
// and submitting starts a task (fetch mocked at the network boundary only).
// Kit orders the chat surface (kit/PRODUCT_SPEC.md:4154 chat-first console).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import { App } from "../../app/App";

interface SeenCall {
  url: string;
  method: string;
  body: unknown;
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
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("l0b06 chat route message box", () => {
  it("mounts a message box on / and starts a task from a typed message", async () => {
    const seen: SeenCall[] = [];
    vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      let body: unknown;
      if (init?.body !== undefined) {
        body = JSON.parse(String(init.body)) as unknown;
      }
      seen.push({ url, method, body });
      if (url === "/api/v1/projects" && method === "POST") {
        const create = body as { name: string };
        return new Response(
          JSON.stringify({
            project: {
              project_id: "p-1",
              name: create.name,
              created_at: "2026-01-02T00:00:00.000Z",
            },
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      if (url.startsWith("/api/v1/tasks") && method === "POST") {
        const create = body as { title: string };
        return new Response(
          JSON.stringify({
            task: {
              task_id: "t-1",
              project_id: "p-1",
              title: create.title,
              status: "QUEUED",
              created_at: "2026-01-02T00:00:00.000Z",
            },
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ projects: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const router = createMemoryRouter([{ path: "*", element: <App /> }], {
      initialEntries: ["/"],
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    fireEvent.change(await screen.findByTestId("chat-prompt"), {
      target: { value: "hello task" },
    });
    fireEvent.click(await screen.findByTestId("chat-send"));
    await waitFor(() => {
      expect(
        seen.some(
          (call) =>
            call.url.startsWith("/api/v1/tasks") &&
            call.method === "POST" &&
            (call.body as { title?: string }).title === "hello task",
        ),
      ).toBe(true);
    });
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
  });
});
