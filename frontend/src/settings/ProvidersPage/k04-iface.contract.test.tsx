/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PROVIDER_CATALOG, getPreset } from "./catalog";
import { ConnectDialog } from "./ConnectDialog";
import { DisconnectDialog } from "./DisconnectDialog";
import { LeftoverKeyFinder } from "./LeftoverKeyFinder";
import { createMemorySecretStore, secretIdForProvider } from "./secretStore";
import type {
  ConnectDialogProps,
  DisconnectDialogProps,
  LeftoverKeyFinderProps,
} from "./k04-iface";
import type { SecretRef } from "./types";
import { resetLocaleForTests, setLocale } from "../../locale/index";

// The default locale is uk; these contract assertions read the English labels.
beforeEach(() => {
  setLocale("en");
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
});

function contractOpenaiPreset() {
  const preset = getPreset(PROVIDER_CATALOG, "openai");
  if (!preset) {
    throw new Error("openai preset missing");
  }
  return preset;
}

// FAKE-OF: ./types (SecretRef seed rows for the memory store; distinct name)
function contractRefFor(secretId: string, providerId: string): SecretRef {
  return {
    secret_id: secretId,
    provider_id: providerId,
    type: "api-key",
    scope: "providers",
    source: "contract",
    created_at: "2026-01-01T00:00:00.000Z",
    last_rotated_at: null,
  };
}

describe("k04-iface static assignability", () => {
  it("stub props objects pass to the real components incl. optional defaults", () => {
    const store = createMemorySecretStore("contract-sess");
    const connectProps: ConnectDialogProps = {
      preset_id: "openai",
      preset: contractOpenaiPreset(),
      open: true,
      store,
      onClose: () => {},
      onConnected: () => {},
    };
    const disconnectProps: DisconnectDialogProps = {
      provider_id: "openai",
      providerLabel: "OpenAI",
      secretId: secretIdForProvider("openai"),
      open: false,
      store,
      sessionToken: "contract-sess",
      onClose: () => {},
      onDisconnected: () => {},
    };
    const finderProps: LeftoverKeyFinderProps = {
      store,
      sessionToken: "contract-sess",
      linkedSecretIds: [],
    };
    const finderFullProps: LeftoverKeyFinderProps = {
      store,
      sessionToken: "contract-sess",
      linkedSecretIds: [],
      refreshKey: 0,
      loadEntries: async () => [],
    };
    render(<ConnectDialog {...connectProps} />);
    cleanup();
    // Optional timeoutMs default (8000) also accepts an explicit value.
    render(<ConnectDialog {...connectProps} timeoutMs={8000} />);
    cleanup();
    render(<DisconnectDialog {...disconnectProps} />);
    cleanup();
    render(<LeftoverKeyFinder {...finderProps} />);
    cleanup();
    render(<LeftoverKeyFinder {...finderFullProps} />);
    expect(true).toBe(true);
  });
});

describe("k04-iface ConnectDialog contract", () => {
  it("match: onConnected called with the frozen preset_id value", async () => {
    // Network-boundary stub: the success line requires the real route
    // round trip (key-save 201 plus connect 200); the contract then
    // proves onConnected fires with the frozen preset_id through it.
    vi.stubGlobal(
      "fetch",
      async (input: unknown) => {
        const url = String(input);
        const body = (data: unknown, status = 200): Response =>
          new Response(JSON.stringify(data), {
            status,
            headers: { "content-type": "application/json" },
          });
        if (url === "/api/v1/providers/keys") {
          return body(
            { key_ref: { secret_id: "openai", provider_id: "openai" } },
            201,
          );
        }
        if (url === "/api/v1/providers/connect") {
          return body({ provider: { provider_id: "openai" } });
        }
        return body({});
      },
    );
    try {
      const store = createMemorySecretStore("contract-sess");
      const onConnected = vi.fn();
      render(
        <ConnectDialog
          preset_id="openai"
          preset={contractOpenaiPreset()}
          open
          store={store}
          onClose={() => {}}
          onConnected={onConnected}
        />,
      );
      fireEvent.change(screen.getByLabelText("API key"), { target: { value: "sk-test" } });
      fireEvent.click(screen.getByText("Save"));
      expect(await screen.findByText(/Reference saved/)).toBeTruthy();
      expect(onConnected).toHaveBeenCalledTimes(1);
      expect(onConnected.mock.calls[0][0]).toBe("openai");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("mismatch: visible refusal, no store.save", async () => {
    const store = createMemorySecretStore("contract-sess");
    const saveSpy = vi.spyOn(store, "save");
    const onConnected = vi.fn();
    render(
      <ConnectDialog
        preset_id="ollama"
        preset={contractOpenaiPreset()}
        open
        store={store}
        onClose={() => {}}
        onConnected={onConnected}
      />,
    );
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText(/Refused: preset mismatch/)).toBeTruthy();
    expect(saveSpy).not.toHaveBeenCalled();
    expect(onConnected).not.toHaveBeenCalled();
  });
});

describe("k04-iface DisconnectDialog contract", () => {
  it("match: remove runs and onDisconnected reports the secret id", async () => {
    const store = createMemorySecretStore("contract-sess");
    const secretId = secretIdForProvider("openai");
    await store.save(contractRefFor(secretId, "openai"));
    const onDisconnected = vi.fn();
    render(
      <DisconnectDialog
        provider_id="openai"
        providerLabel="OpenAI"
        secretId={secretId}
        open
        store={store}
        sessionToken="contract-sess"
        onClose={() => {}}
        onDisconnected={onDisconnected}
      />,
    );
    fireEvent.click(screen.getByText("Disconnect"));
    await waitFor(() => expect(onDisconnected).toHaveBeenCalledWith(secretId));
    expect(await store.list("agent_si/provider/")).toHaveLength(0);
  });

  it("mismatch: visible refusal, no store.remove", async () => {
    const store = createMemorySecretStore("contract-sess");
    const secretId = secretIdForProvider("openai");
    await store.save(contractRefFor(secretId, "openai"));
    const removeSpy = vi.spyOn(store, "remove");
    const onDisconnected = vi.fn();
    render(
      <DisconnectDialog
        provider_id="ollama"
        providerLabel="Ollama"
        secretId={secretId}
        open
        store={store}
        sessionToken="contract-sess"
        onClose={() => {}}
        onDisconnected={onDisconnected}
      />,
    );
    fireEvent.click(screen.getByText("Disconnect"));
    expect(await screen.findByText(/Refused: secret .* is not bound to provider ollama/)).toBeTruthy();
    expect(removeSpy).not.toHaveBeenCalled();
    expect(onDisconnected).not.toHaveBeenCalled();
    expect(await store.list("agent_si/provider/")).toHaveLength(1);
  });
});

describe("k04-iface LeftoverKeyFinder contract", () => {
  async function contractSeededKeys() {
    const store = createMemorySecretStore("contract-sess");
    await store.save(contractRefFor("agent_si/provider/openai", "openai"));
    await store.save(contractRefFor("agent_si/provider/old", "old"));
    await store.save(contractRefFor("unrelated/other", "other"));
    return store;
  }

  it("token-less delete is refused and the entry is kept", async () => {
    const store = await contractSeededKeys();
    render(<LeftoverKeyFinder store={store} sessionToken="" linkedSecretIds={[]} />);
    await screen.findByText("agent_si/provider/old");
    fireEvent.click(screen.getByLabelText("Delete agent_si/provider/old"));
    expect(await screen.findByText("Confirm delete")).toBeTruthy();
    fireEvent.click(screen.getByText("Confirm delete"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("agent_si/provider/old")).toBeTruthy();
    expect(await store.list("agent_si/provider/")).toHaveLength(2);
  });

  it("token-ok: names plus dates listed, per-entry confirm delete works, audit-logged", async () => {
    const store = await contractSeededKeys();
    render(<LeftoverKeyFinder store={store} sessionToken="contract-sess" linkedSecretIds={[]} />);
    expect(await screen.findByText("agent_si/provider/openai")).toBeTruthy();
    expect(screen.getByText("agent_si/provider/old")).toBeTruthy();
    expect(screen.queryByText("unrelated/other")).toBeNull();
    expect(screen.getAllByText(/2026-01-01/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByLabelText("Delete agent_si/provider/old"));
    expect(await screen.findByText("Confirm delete")).toBeTruthy();
    fireEvent.click(screen.getByText("Confirm delete"));
    await waitFor(() => expect(screen.queryByText("agent_si/provider/old")).toBeNull());
    expect(await store.list("agent_si/provider/")).toHaveLength(1);
    expect(store.audit().map((record) => record.entryName)).toContain("agent_si/provider/old");
  });
});

import type {
  ChatModelSaveRequest,
  ChatModelSaveResult,
} from "./k04-iface";

describe("k04-iface chat-model save shapes", () => {
  it("request/response types mirror the PUT route JSON body and 200 payload", () => {
    const body: ChatModelSaveRequest = {
      project_id: "local",
      model_id: "openai/model-1",
    };
    const result: ChatModelSaveResult = {
      ok: true,
      project_id: body.project_id,
      model_id: body.model_id,
    };
    expect(JSON.stringify(body)).toBe(
      '{"project_id":"local","model_id":"openai/model-1"}',
    );
    expect(JSON.stringify(body)).not.toContain("session_token");
    expect(result.ok).toBe(true);
  });
});
