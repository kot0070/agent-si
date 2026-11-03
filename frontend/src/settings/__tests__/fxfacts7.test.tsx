/** @vitest-environment jsdom */
// FXFACTS F7 RED: routing and models are one tab with a prop split.
// /settings/models shows connected providers and their models only;
// /settings/routing shows role-to-model routing only. No new API,
// no control lost, nothing shown twice.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown): Promise<Response> => {
      const url = String(input);
      if (url === "/api/v1/projects") {
        return jsonBody({ projects: [] });
      }
      if (url === "/api/v1/providers") {
        return jsonBody({ providers: [{ provider_id: "meta" }] });
      }
      if (url.startsWith("/api/v1/roles/")) {
        return jsonBody({ code: "NONE" }, 404);
      }
      return jsonBody({ code: "FXFACTS7_UNEXPECTED_API" }, 404);
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
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  setLocale("en");
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("fxfacts7 settings models vs routing", () => {
  it("models tab shows providers and their models, no routing controls", async () => {
    renderAppAt("/settings/models");
    const cards = await screen.findAllByTestId("provider-card");
    expect(cards.length).toBeGreaterThan(0);
    expect(
      screen.queryByTestId("role-pool-picker"),
    ).toBeNull();
  });

  it("routing tab shows role-to-model routing, no provider cards", async () => {
    renderAppAt("/settings/routing");
    const pickers = await screen.findAllByTestId("role-pool-picker");
    expect(pickers.length).toBeGreaterThan(0);
    expect(screen.queryByTestId("provider-card")).toBeNull();
  });
});
