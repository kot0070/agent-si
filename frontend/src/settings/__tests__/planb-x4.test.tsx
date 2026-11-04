/** @vitest-environment jsdom */
// PLANB X4 (DEFECT-25) + X6b (DEFECT-24): real App at /settings/localAI with a
// connected Ollama that lists models; fake only at the network boundary.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { App } from "../../app/App";

const GLIMMER = {
  provider_id: "ollama",
  models: [
    { id: "ollama/muse-glimmer:30b", name: "muse-glimmer:30b", price: null, kb_known: true },
  ],
  source: "local",
  enabled: [],
};

function stubOllama(connected: boolean): void {
  const json = (data: unknown): Response =>
    new Response(JSON.stringify(data), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown) => {
      const url = String(input);
      if (url === "/api/v1/providers") {
        return json({ providers: [] });
      }
      if (url.startsWith("/api/v1/local/bench/check")) {
        return json({ reachable: connected, reason: "open" });
      }
      if (url === "/api/v1/local/models") {
        return json(
          connected
            ? [{ model: "http://localhost:11434", evidence_tier: "PROXY", status: "READY" }]
            : [],
        );
      }
      if (url === "/api/v1/providers/ollama/models") {
        return json(connected ? GLIMMER : { ...GLIMMER, models: [] });
      }
      return json({});
    }),
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  clearUiToken();
  setUiToken("x4-token");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
});

function renderLocalAi(): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: ["/settings/localAI"],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("PLANB X4 local models note", () => {
  it("a connected Ollama with models: no 'No local models found in this folder'", async () => {
    stubOllama(true);
    renderLocalAi();
    const card = await screen.findByTestId("local-preset-ollama");
    await within(card).findByTestId("local-models-ollama");
    expect(screen.queryByText(/No local models found in this folder/)).toBeNull();
    expect(screen.queryByTestId("localai-models-empty")).toBeNull();
  });

  it("nothing connected keeps the honest empty note", async () => {
    stubOllama(false);
    renderLocalAi();
    expect((await screen.findByTestId("localai-models-empty")).textContent).toContain(
      "No local models found in this folder",
    );
  });
});

describe("PLANB X6b Use for agents and Disconnect spacing", () => {
  it("both buttons sit in one row with a gap", async () => {
    stubOllama(true);
    renderLocalAi();
    const card = await screen.findByTestId("local-preset-ollama");
    const row = await within(card).findByTestId("local-actions-ollama");
    expect(row.style.gap).not.toBe("");
    expect(within(row).getByTestId("local-use-ollama")).toBeTruthy();
    expect(within(row).getByRole("button", { name: /Disconnect/ })).toBeTruthy();
  });
});