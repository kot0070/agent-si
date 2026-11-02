/** @vitest-environment jsdom */
// L0B-01: on the real /projects route with the real HttpApiClient (fetch
// mocked at the network boundary only), Add project shows the new row with
// no reload, and the write POST still carries x-ui-session-token.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import { App } from "../../app/App";

const TOKEN = "tok-l0b01";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";
const CREATED_AT = "2026-01-02T00:00:00.000Z";

interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
}

function setWindowToken(value: string): void {
  (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY] = value;
}

function clearWindowToken(): void {
  delete (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY];
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

describe("l0b01 add-project refetch on the real route", () => {
  it("shows the new row with no reload and keeps the session token on the write", async () => {
    setWindowToken(TOKEN);
    let projects: Array<{
      project_id: string;
      name: string;
      created_at: string;
    }> = [{ project_id: "p-1", name: "n-1", created_at: CREATED_AT }];
    const seen: SeenRequest[] = [];
    vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      const headers = { ...((init?.headers ?? {}) as Record<string, string>) };
      seen.push({ url, method: (init?.method ?? "GET").toUpperCase(), headers });
      if (url === "/api/v1/projects" && (init?.method ?? "GET").toUpperCase() === "POST") {
        const body = JSON.parse(String(init?.body)) as { name: string };
        projects = [
          ...projects,
          { project_id: "p-9", name: body.name, created_at: CREATED_AT },
        ];
        return new Response(
          JSON.stringify({
            project: { project_id: "p-9", name: body.name, created_at: CREATED_AT },
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ projects }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const router = createMemoryRouter([{ path: "*", element: <App /> }], {
      initialEntries: ["/projects"],
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("project-row-p-1")).toBeTruthy();
    fireEvent.change(await screen.findByTestId("project-add-name"), {
      target: { value: "n-new" },
    });
    fireEvent.change(await screen.findByTestId("project-add-folder"), {
      target: { value: "f-new" },
    });
    fireEvent.click(await screen.findByTestId("project-add-submit"));
    // U13: create opens the new project at once (ChatArea for p-9),
    // never a stuck "No projects yet" after a served write.
    expect(await screen.findByTestId("chat-area")).toBeTruthy();

    const posts = seen.filter(
      (request) => request.url === "/api/v1/projects" && request.method === "POST",
    );
    // Exactly one write: no double submit while saving.
    expect(posts.length).toBe(1);
    const first = posts[0];
    expect(first).toBeDefined();
    if (first === undefined) {
      throw new Error("missing write POST");
    }
    expect(first.headers["x-ui-session-token"]).toBe(TOKEN);
    // The refreshed list carries the new row once back on /projects.
    await router.navigate("/projects");
    expect(await screen.findByTestId("project-row-p-9")).toBeTruthy();
  });
});
