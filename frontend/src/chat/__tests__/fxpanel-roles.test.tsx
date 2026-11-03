/** @vitest-environment jsdom */
// FXPANEL roles-composer fix through the REAL page. A hung or failing
// provider load degrades to the plain Connect state with a retry action
// (never an empty box); genuinely empty stays the plain Connect state;
// expanding re-reads providers (provider-change retry). Locale driver:
// no new keys — chat.hierarchy.connect, watcher.tab.loading,
// chat.error.retry (en + uk, English defaults). Network boundary only.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { pt } from "../permissions";
import { ChatArea } from "../index";

const PROJECT_ID = "fxpanel-p1";
const PROVIDERS_URL = "/api/v1/providers";
const ROLE_URL = "/api/v1/routing/role";
const SESSION_TOKEN = "fxpanel-test-token";

type Profile = {
  mode: string;
  provider?: string;
  model?: string;
};

let connected: string[] | "hang" | "fail";
let profiles: Record<string, Profile>;

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function profilePayload(role: string, profile: Profile): unknown {
  return {
    role,
    project_id: PROJECT_ID,
    mode: profile.mode,
    provider: profile.provider ?? null,
    model: profile.model ?? null,
    binding: "DEFAULT",
    version: 1,
  };
}

function stubChatBoundary(): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url === PROVIDERS_URL && method === "GET") {
      if (connected === "hang") {
        return new Promise<Response>(() => undefined);
      }
      if (connected === "fail") {
        throw new Error("fxpanel providers down");
      }
      return jsonBody({
        providers: (connected as string[]).map((provider_id) => ({
          provider_id,
        })),
      });
    }
    if (url.startsWith(ROLE_URL) && method === "GET") {
      const query = url.includes("?") ? (url.split("?")[1] as string) : "";
      const params = new URLSearchParams(query);
      const role = params.get("role") ?? "";
      const profile = profiles[role];
      if (profile === undefined) {
        return jsonBody({ error: "missing" }, 404);
      }
      return jsonBody({ profile: profilePayload(role, profile) });
    }
    if (url === "/api/v1/local/models" && method === "GET") {
      return jsonBody({ models: [] });
    }
    const modelsMatch = url.match(/^\/api\/v1\/providers\/([^/]+)\/models$/);
    if (modelsMatch !== null && method === "GET") {
      const id = modelsMatch[1] as string;
      const rows =
        id === "anthropic"
          ? [
              { id: "anthropic/claude-haiku-4-5", name: "claude-haiku-4-5", kb_known: true },
              { id: "anthropic/claude-haiku-5-5", name: "claude-haiku-5-5", kb_known: true },
            ]
          : id === "openai"
            ? [
                { id: "openai/gpt-4o-mini", name: "gpt-4o-mini", kb_known: true },
                { id: "openai/gpt-4o", name: "gpt-4o", kb_known: true },
              ]
            : id === "meta"
              ? [
                  { id: "meta/muse-spark-1.3", name: "muse-spark-1.3", kb_known: true },
                ]
              : [];
      return jsonBody({
        provider_id: id,
        models: rows,
        source: "provider",
        enabled: rows.map((row) => (row as { id: string }).id),
      });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

function defaultSeed(): void {
  profiles = {
    director: {
      mode: "PINNED",
      provider: "anthropic",
      model: "anthropic/claude-haiku-5-5",
    },
    manager: { mode: "AUTO" },
    worker: {
      mode: "PINNED",
      provider: "openai",
      model: "openai/gpt-4o-mini",
    },
    auditor: {
      mode: "PINNED",
      provider: "openai",
      model: "openai/gpt-4o-mini",
    },
  };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  clearUiToken();
  setUiToken(SESSION_TOKEN);
  connected = ["anthropic", "openai"];
  defaultSeed();
  stubChatBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderChat(): void {
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <ChatArea projectId={PROJECT_ID} />
    </ApiClientProvider>,
  );
}

describe("fxpanel roles-composer provider failure", () => {
  it(
    "a hung provider load degrades to Connect + Retry, never an empty box",
    async () => {
      connected = "hang";
      renderChat();
      fireEvent.click(await screen.findByTestId("hierarchy-collapsed"));
      // While pending the expanded section names its state, it never
      // renders title-only.
      expect(await screen.findByTestId("hierarchy-loading")).toBeTruthy();
      // Past the load budget the plain Connect state takes over.
      const link = await screen.findByTestId("hierarchy-connect-link", undefined, {
        timeout: 15000,
      });
      expect(link.getAttribute("href")).toBe("/settings/models");
      expect(
        screen.getByTestId("hierarchy-empty").textContent,
      ).toContain(pt("chat.hierarchy.connect", "Connect a provider"));
      expect(screen.queryByTestId("hierarchy-select-director")).toBeNull();
      expect(await screen.findByTestId("hierarchy-retry")).toBeTruthy();
    },
    20000,
  );

  it(
    "retry recovers when providers answer (provider-change retry)",
    async () => {
      connected = "hang";
      renderChat();
      fireEvent.click(await screen.findByTestId("hierarchy-collapsed"));
      await screen.findByTestId("hierarchy-retry", undefined, {
        timeout: 15000,
      });
      connected = ["anthropic", "openai"];
      fireEvent.click(screen.getByTestId("hierarchy-retry"));
      expect(
        await screen.findByTestId("hierarchy-select-director"),
      ).toBeTruthy();
      expect(screen.queryByTestId("hierarchy-retry")).toBeNull();
    },
    25000,
  );

  it("rejected provider fetch still settles to the Connect state", async () => {
    connected = "fail";
    renderChat();
    fireEvent.click(await screen.findByTestId("hierarchy-collapsed"));
    expect(await screen.findByTestId("hierarchy-loading")).toBeTruthy();
    expect(await screen.findByTestId("hierarchy-connect-link")).toBeTruthy();
    // listConnectedProviders swallows the failure to []; the rows keep
    // their contract (Director row carries the link, no selects).
    expect(screen.queryByTestId("hierarchy-select-director")).toBeNull();
  });

  it("genuinely empty providers render the plain Connect state", async () => {
    connected = [];
    renderChat();
    fireEvent.click(await screen.findByTestId("hierarchy-collapsed"));
    expect(await screen.findByTestId("hierarchy-empty")).toBeTruthy();
    expect(
      screen.getByTestId("hierarchy-empty").textContent,
    ).toContain("Connect a provider");
    expect(
      screen.getAllByTestId("hierarchy-connect-link").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.queryByTestId("hierarchy-select-director")).toBeNull();
    expect(screen.queryByTestId("hierarchy-retry")).toBeNull();
  });

  it("expanding re-reads providers after a provider change", async () => {
    renderChat();
    fireEvent.click(await screen.findByTestId("hierarchy-collapsed"));
    expect(
      await screen.findByTestId("hierarchy-select-director"),
    ).toBeTruthy();
    fireEvent.click(screen.getByTestId("hierarchy-collapse"));
    expect(await screen.findByTestId("hierarchy-collapsed")).toBeTruthy();
    connected = ["anthropic", "openai", "meta"];
    fireEvent.click(screen.getByTestId("hierarchy-collapsed"));
    const select = (await screen.findByTestId(
      "hierarchy-select-director",
    )) as HTMLSelectElement;
    await waitFor(() => {
      const values = Array.from(select.options).map(
        (option) => (option as HTMLOptionElement).value,
      );
      expect(values).toContain("meta/muse-spark-1.3");
    });
  });

  it("reads the Connect state in Ukrainian", async () => {
    setLocale("uk");
    connected = [];
    renderChat();
    fireEvent.click(await screen.findByTestId("hierarchy-collapsed"));
    expect(await screen.findByTestId("hierarchy-empty")).toBeTruthy();
    expect(screen.getByTestId("hierarchy-empty").textContent).toContain(
      "Під'єднати постачальника",
    );
    expect(
      screen.getAllByTestId("hierarchy-connect-link")[0]?.getAttribute("href"),
    ).toBe("/settings/models");
  });
});
