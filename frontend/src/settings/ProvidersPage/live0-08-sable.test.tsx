// CODER-2 Sable: LIVE0-08 new lane test (REAL UI write call-sites, fetch stubbed only).
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { clearUiToken } from "../../api/errors";
import { ProvidersPage, saveChatModel } from "./ProvidersPage";
import { saveRolePool } from "./poolsApi";
import { DisconnectDialog } from "./DisconnectDialog";
import { LeftoverKeyFinder } from "./LeftoverKeyFinder";
import { createMemorySecretStore } from "./secretStore";
import type { SecretRef } from "./types";
import { resetLocaleForTests, setLocale } from "../../locale/index";

const TOKEN = "tok-live0-08-sable";
const PAGE_TOKEN = "local-session";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

function clearWindowToken(): void {
  delete (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY];
}

interface SeenRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
}

function stubFetchOk(): { seen: SeenRequest[] } {
  const seen: SeenRequest[] = [];
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      const headers = { ...((init?.headers ?? {}) as Record<string, string>) };
      const body = typeof init?.body === "string" ? init.body : "";
      seen.push({ url, method: (init?.method ?? "GET").toUpperCase(), headers, body });
      return { ok: true, status: 200, json: async () => ({}) };
    },
  );
  return { seen };
}

function expectTokenFromFirstCall(seen: SeenRequest[], token: string, actor: string | null): void {
  expect(seen.length).toBeGreaterThanOrEqual(1);
  for (const request of seen) {
    expect(request.url).not.toContain(token);
    expect(request.url).not.toContain("session_token");
    expect(request.body).not.toContain(token);
    expect(request.headers["Authorization"]).toBeUndefined();
    expect(request.headers["x-agent-si-actor"]).toBeUndefined();
  }
  const first = seen[0];
  expect(first).toBeDefined();
  if (first === undefined) {
    throw new Error("missing request");
  }
  expect(first.headers["x-ui-session-token"]).toBe(token);
  if (actor !== null) {
    expect(first.headers["x-actor"]).toBe(actor);
  }
}

// FAKE-OF: ./types (SecretRef seed rows for the memory store; distinct name)
function sableRefFor(secretId: string, providerId: string): SecretRef {
  return {
    secret_id: secretId,
    provider_id: providerId,
    type: "api-key",
    scope: "providers",
    source: "sable",
    created_at: "2026-01-01T00:00:00.000Z",
    last_rotated_at: null,
  };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  clearWindowToken();
  clearUiToken();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearWindowToken();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("LIVE0-08 sable UI writes carry the session token", () => {
  it("chat-model save carries the token in the header from the first call", async () => {
    const { seen } = stubFetchOk();
    await saveChatModel("local", "openai/model-1", TOKEN);
    const posts = seen.filter(
      (request) => request.url === "/api/v1/roles/chat-model" && request.method === "PUT",
    );
    expect(posts).toHaveLength(1);
    // CODER-2 Sable: saveChatModel uses a direct fetch with the session
    // token header only (existing mechanism, no actor header there).
    expectTokenFromFirstCall(posts, TOKEN, null);
  });

  it("pool save from the mounted page carries the page session token from the first call", async () => {
    render(<ProvidersPage project_id="local" />);
    const { seen } = stubFetchOk();
    await saveRolePool(
      "local",
      "worker",
      { mode: "AUTO", pinnedKey: "", poolKeys: [], strategy: "AUTO" },
      [{ key: "pool-opt-1", label: "OpenAI -- Standard", providerId: "openai", modelId: "openai/model-1" }],
    );
    const posts = seen.filter(
      (request) => request.url === "/api/v1/roles/pools" && request.method === "PUT",
    );
    expect(posts).toHaveLength(1);
    expectTokenFromFirstCall(posts, PAGE_TOKEN, "ui");
  });

  it("empty token is refused with no network write via the disconnect dialog", async () => {
    const store = createMemorySecretStore("sess-sable");
    const secretId = "agent_si/provider/openai";
    await store.save(sableRefFor(secretId, "openai"));
    const { seen } = stubFetchOk();
    const onDisconnected = vi.fn();
    render(
      <DisconnectDialog
        provider_id="openai"
        providerLabel="OpenAI"
        secretId={secretId}
        open
        store={store}
        sessionToken=""
        onClose={() => {}}
        onDisconnected={onDisconnected}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(onDisconnected).not.toHaveBeenCalled();
    expect(await store.list("agent_si/provider/")).toHaveLength(1);
    expect(seen).toHaveLength(0);
  });

  it("empty token is refused with no network write via the leftover finder, token-ok deletes", async () => {
    const store = createMemorySecretStore("sess-sable");
    await store.save(sableRefFor("agent_si/provider/old", "old"));
    const { seen } = stubFetchOk();
    render(<LeftoverKeyFinder store={store} sessionToken="" linkedSecretIds={[]} />);
    await screen.findByText("agent_si/provider/old");
    fireEvent.click(screen.getByLabelText("Delete agent_si/provider/old"));
    fireEvent.click(screen.getByText("Confirm delete"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("agent_si/provider/old")).toBeTruthy();
    expect(await store.list("agent_si/provider/")).toHaveLength(1);
    expect(seen).toHaveLength(0);
    cleanup();
    const okStore = createMemorySecretStore("sess-sable");
    await okStore.save(sableRefFor("agent_si/provider/old", "old"));
    render(<LeftoverKeyFinder store={okStore} sessionToken="sess-sable" linkedSecretIds={[]} />);
    await screen.findByText("agent_si/provider/old");
    fireEvent.click(screen.getByLabelText("Delete agent_si/provider/old"));
    fireEvent.click(screen.getByText("Confirm delete"));
    await waitFor(() => expect(screen.queryByText("agent_si/provider/old")).toBeNull());
    expect(await okStore.list("agent_si/provider/")).toHaveLength(0);
    expect(okStore.audit().map((record) => record.entryName)).toContain("agent_si/provider/old");
  });
});
