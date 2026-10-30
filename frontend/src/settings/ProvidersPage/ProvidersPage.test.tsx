/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { PROVIDER_CATALOG, getPreset } from "./catalog";
import { ChatSelector, enabledChatChoices } from "./ChatSelector";
import { ConnectDialog } from "./ConnectDialog";
import { DisconnectDialog } from "./DisconnectDialog";
import { LeftoverFinder } from "./LeftoverFinder";
import { ProvidersPage } from "./ProvidersPage";
import { ChatModelSelector } from "./ChatModelSelector";
import { LeftoverKeyFinder } from "./LeftoverKeyFinder";
import { RolePoolPicker, choicesToPoolOptions, defaultPoolResolver } from "./RolePoolPicker";
import { SetupWizard } from "./SetupWizard";
import { createMemorySecretStore, secretIdForProvider } from "./secretStore";
import type { SecretStorePort } from "./secretStore";
import { AUTO_SENTINEL, ROLE_KEYS } from "./types";
import type { ProviderState, SecretRef } from "./types";
import { resetLocaleForTests, setLocale } from "../../locale/index";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function openaiPreset() {
  const preset = getPreset(PROVIDER_CATALOG, "openai");
  if (!preset) {
    throw new Error("openai preset missing");
  }
  return preset;
}

// FAKE-OF: ./types (SecretRef seed rows for the memory store)
function refFor(secretId: string, providerId: string): SecretRef {
  return {
    secret_id: secretId,
    provider_id: providerId,
    type: "api-key",
    scope: "providers",
    source: "test",
    created_at: "2026-01-01T00:00:00.000Z",
    last_rotated_at: null,
  };
}

describe("ConnectDialog", () => {
  it("key-only connect fills id, type and base URL from the preset", () => {
    const store = createMemorySecretStore("sess");
    render(
      <ConnectDialog preset_id="openai" preset={openaiPreset()} open store={store} onClose={() => {}} onConnected={() => {}} />,
    );
    expect(screen.getByText("openai")).toBeTruthy();
    expect(screen.getByText("cloud")).toBeTruthy();
    expect(screen.getByText("https://api.openai.com/v1")).toBeTruthy();
    expect(screen.getByText(/Starts with sk-/)).toBeTruthy();
    expect(screen.getByLabelText("API key")).toBeTruthy();
  });

  it("bounded save shows a visible timeout result", async () => {
    // FAKE-OF: ./secretStore (never-resolving save to exercise the bounded timeout)
    const hanging: SecretStorePort = {
      list: async () => [],
      save: () => new Promise<void>(() => {}),
      remove: async () => {},
      audit: () => [],
    };
    render(
      <ConnectDialog
        preset_id="openai"
        preset={openaiPreset()}
        open
        store={hanging}
        timeoutMs={20}
        onClose={() => {}}
        onConnected={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText(/timed out/i)).toBeTruthy();
  });

  it("successful save shows a visible result and reports the reference", async () => {
    const store = createMemorySecretStore("sess");
    const onConnected = vi.fn();
    render(
      <ConnectDialog preset_id="openai" preset={openaiPreset()} open store={store} onClose={() => {}} onConnected={onConnected} />,
    );
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText(/Reference saved/)).toBeTruthy();
    expect(onConnected).toHaveBeenCalledTimes(1);
    expect(await store.list("agent_si/provider/")).toHaveLength(1);
  });

  it("passes the frozen preset_id value to the callback on match", async () => {
    const store = createMemorySecretStore("sess");
    const onConnected = vi.fn();
    render(
      <ConnectDialog preset_id="openai" preset={openaiPreset()} open store={store} onClose={() => {}} onConnected={onConnected} />,
    );
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText(/Reference saved/)).toBeTruthy();
    expect(onConnected).toHaveBeenCalledTimes(1);
    expect(onConnected.mock.calls[0][0]).toBe("openai");
    const rows = await store.list("agent_si/provider/");
    expect(rows).toHaveLength(1);
    expect(rows[0].provider_id).toBe("openai");
    expect(rows[0].secret_id).toBe(secretIdForProvider("openai"));
  });

  it("refuses a preset mismatch with no store save", async () => {
    const store = createMemorySecretStore("sess");
    const saveSpy = vi.spyOn(store, "save");
    const onConnected = vi.fn();
    render(
      <ConnectDialog preset_id="ollama" preset={openaiPreset()} open store={store} onClose={() => {}} onConnected={onConnected} />,
    );
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText(/Refused: preset mismatch/)).toBeTruthy();
    expect(saveSpy).not.toHaveBeenCalled();
    expect(onConnected).not.toHaveBeenCalled();
    expect(await store.list("agent_si/provider/")).toHaveLength(0);
  });

  it("closes via Escape, X and Cancel", () => {
    const modes = ["esc", "x", "cancel"] as const;
    for (const mode of modes) {
      const onClose = vi.fn();
      render(
        <ConnectDialog
          preset_id="openai"
          preset={openaiPreset()}
          open
          store={createMemorySecretStore("s")}
          onClose={onClose}
          onConnected={() => {}}
        />,
      );
      if (mode === "esc") {
        fireEvent.keyDown(document, { key: "Escape" });
      } else if (mode === "x") {
        fireEvent.click(screen.getByLabelText("Close"));
      } else {
        fireEvent.click(screen.getByText("Cancel"));
      }
      expect(onClose).toHaveBeenCalledTimes(1);
      cleanup();
    }
  });
});

describe("DisconnectDialog", () => {
  it("clean Disconnect removes the store entry and reports it", async () => {
    const store = createMemorySecretStore("sess");
    const secretId = secretIdForProvider("openai");
    await store.save(refFor(secretId, "openai"));
    const onDisconnected = vi.fn();
    render(
      <DisconnectDialog
        provider_id="openai"
        providerLabel="OpenAI"
        secretId={secretId}
        open
        store={store}
        sessionToken="sess"
        onClose={() => {}}
        onDisconnected={onDisconnected}
      />,
    );
    fireEvent.click(screen.getByText("Disconnect"));
    await waitFor(() => expect(onDisconnected).toHaveBeenCalledWith(secretId));
    expect(await store.list("agent_si/provider/")).toHaveLength(0);
  });

  it("refuses a provider mismatch with no store remove", async () => {
    const store = createMemorySecretStore("sess");
    const secretId = secretIdForProvider("openai");
    await store.save(refFor(secretId, "openai"));
    const removeSpy = vi.spyOn(store, "remove");
    const onDisconnected = vi.fn();
    render(
      <DisconnectDialog
        provider_id="ollama"
        providerLabel="Ollama"
        secretId={secretId}
        open
        store={store}
        sessionToken="sess"
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

  it("closes via Escape, X and Cancel", () => {
    const modes = ["esc", "x", "cancel"] as const;
    for (const mode of modes) {
      const onClose = vi.fn();
      render(
        <DisconnectDialog
          provider_id="openai"
          providerLabel="OpenAI"
          secretId={secretIdForProvider("openai")}
          open
          store={createMemorySecretStore("s")}
          sessionToken="s"
          onClose={onClose}
          onDisconnected={() => {}}
        />,
      );
      if (mode === "esc") {
        fireEvent.keyDown(document, { key: "Escape" });
      } else if (mode === "x") {
        fireEvent.click(screen.getByLabelText("Close"));
      } else {
        fireEvent.click(screen.getByText("Cancel"));
      }
      expect(onClose).toHaveBeenCalledTimes(1);
      cleanup();
    }
  });
});

describe("ChatSelector", () => {
  it("lists enabled models only, by label", () => {
    const states: Record<string, ProviderState> = {
      openai: { presetId: "openai", connected: true, enabledModels: ["openai/model-1"] },
      ollama: { presetId: "ollama", connected: false, enabledModels: ["ollama/model-1"] },
    };
    const choices = enabledChatChoices(PROVIDER_CATALOG, states);
    expect(choices.map((choice) => choice.modelId)).toEqual(["openai/model-1"]);
    render(<ChatSelector catalog={PROVIDER_CATALOG} states={states} value="" onChange={() => {}} />);
    const text = screen
      .getAllByRole("option")
      .map((option) => option.textContent ?? "")
      .join(" ");
    expect(text).toContain("Standard");
    expect(text).not.toContain("model-1");
  });
});

describe("ProvidersPage", () => {
  it("search box placeholder follows the locale (en plus uk default)", () => {
    try {
      setLocale("en");
      const enView = render(<ProvidersPage />);
      expect(screen.getByPlaceholderText("Search providers or models")).toBeTruthy();
      enView.unmount();
      cleanup();
      setLocale("uk");
      render(<ProvidersPage />);
      expect(screen.getByPlaceholderText("Шукати постачальників або моделі")).toBeTruthy();
    } finally {
      resetLocaleForTests();
    }
  });

  it("checkbox plus search filters the model list", () => {
    render(<ProvidersPage />);
    expect(screen.getAllByTestId("model-row").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Search models"), { target: { value: "zzz-no-such-model" } });
    expect(screen.queryAllByTestId("model-row")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Search models"), { target: { value: "Standard" } });
    expect(screen.getAllByTestId("model-row").length).toBeGreaterThan(0);
  });

  it("provider order is stable across updates and remounts", () => {
    const first = render(<ProvidersPage />);
    const order = (): Array<string | null> =>
      screen.getAllByTestId("provider-card").map((el) => el.getAttribute("data-provider-id"));
    const before = order();
    expect(before.length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Search models"), { target: { value: "Standard" } });
    fireEvent.change(screen.getByLabelText("Search models"), { target: { value: "" } });
    expect(order()).toEqual(before);
    first.unmount();
    render(<ProvidersPage />);
    expect(order()).toEqual(before);
  });

  it("connect enables per-model toggles and Disconnect cleans up", async () => {
    const store = createMemorySecretStore("sess");
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const connectDialog = screen.getByRole("dialog");
    fireEvent.change(within(connectDialog).getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(within(connectDialog).getByText("Save"));
    expect(await within(connectDialog).findByText(/Reference saved/)).toBeTruthy();
    fireEvent.click(within(connectDialog).getByLabelText("Close"));
    const box = screen.getByLabelText("OpenAI Standard") as HTMLInputElement;
    expect(box.disabled).toBe(false);
    fireEvent.click(box);
    expect((screen.getByLabelText("OpenAI Standard") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole("combobox").textContent ?? "").toContain("Standard");
    fireEvent.click(screen.getByLabelText("Disconnect OpenAI"));
    const disconnectDialog = screen.getByRole("dialog");
    fireEvent.click(within(disconnectDialog).getByText("Disconnect"));
    await waitFor(() => expect(screen.getByLabelText("Connect OpenAI")).toBeTruthy());
    expect(await store.list("agent_si/provider/")).toHaveLength(0);
    expect((screen.getByLabelText("OpenAI Standard") as HTMLInputElement).checked).toBe(false);
  });
});

describe("SetupWizard", () => {
  const choices = [{ providerId: "openai", modelId: "openai/model-1", label: "OpenAI \u2014 Standard" }];

  it("defaults every role to AUTO with no vendor or model preselected", () => {
    render(<SetupWizard choices={choices} onDone={() => {}} />);
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    expect(selects).toHaveLength(5);
    for (const select of selects) {
      expect(select.value).toBe(AUTO_SENTINEL);
    }
    for (const option of screen.getAllByRole("option")) {
      expect(option.textContent ?? "").not.toContain("/");
    }
  });

  it("returns the per-role pick on finish", () => {
    const onDone = vi.fn();
    render(<SetupWizard choices={choices} onDone={onDone} />);
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    fireEvent.change(selects[0], { target: { value: "openai/model-1" } });
    fireEvent.click(screen.getByText("Finish setup"));
    expect(onDone).toHaveBeenCalledTimes(1);
    const assignment = onDone.mock.calls[0][0] as Record<string, string>;
    expect(assignment.director).toBe("openai/model-1");
    expect(assignment.manager).toBe(AUTO_SENTINEL);
  });
});

describe("LeftoverFinder", () => {
  async function seeded(): Promise<SecretStorePort> {
    const store = createMemorySecretStore("sess");
    await store.save(refFor("agent_si/provider/openai", "openai"));
    await store.save(refFor("agent_si/provider/ollama", "ollama"));
    await store.save(refFor("unrelated/other", "other"));
    return store;
  }

  it("lists names and dates under the app prefix only", async () => {
    const store = await seeded();
    render(<LeftoverFinder store={store} sessionToken="sess" linkedSecretIds={[]} />);
    expect(await screen.findByText("agent_si/provider/openai")).toBeTruthy();
    expect(screen.getByText("agent_si/provider/ollama")).toBeTruthy();
    expect(screen.queryByText("unrelated/other")).toBeNull();
    expect(screen.getAllByText(/2026-01-01/).length).toBeGreaterThan(0);
  });

  it("deletes only after per-entry confirm and audit-logs the name", async () => {
    const store = await seeded();
    render(<LeftoverFinder store={store} sessionToken="sess" linkedSecretIds={[]} />);
    await screen.findByText("agent_si/provider/openai");
    fireEvent.click(screen.getByLabelText("Delete agent_si/provider/openai"));
    expect(await store.list("agent_si/provider/")).toHaveLength(2);
    expect(screen.getByText("Confirm delete")).toBeTruthy();
    fireEvent.click(screen.getByText("Confirm delete"));
    await waitFor(() => expect(screen.queryByText("agent_si/provider/openai")).toBeNull());
    expect(await store.list("agent_si/provider/")).toHaveLength(1);
    expect(store.audit().map((record) => record.entryName)).toContain("agent_si/provider/openai");
  });

  it("never deletes a live-provider-linked entry", async () => {
    const store = await seeded();
    render(
      <LeftoverFinder
        store={store}
        sessionToken="sess"
        linkedSecretIds={["agent_si/provider/openai"]}
      />,
    );
    await screen.findByText("agent_si/provider/openai");
    expect(screen.queryByLabelText("Delete agent_si/provider/openai")).toBeNull();
    expect(await store.list("agent_si/provider/")).toHaveLength(2);
  });

  it("secret-store key delete removes the entry and rejects a bad token", async () => {
    const store = await seeded();
    await expect(store.remove("agent_si/provider/openai", "wrong")).rejects.toThrow();
    expect(await store.list("agent_si/provider/")).toHaveLength(2);
    await store.remove("agent_si/provider/openai", "sess");
    expect(await store.list("agent_si/provider/")).toHaveLength(1);
  });
});


describe("RolePoolPicker", () => {
  it("defaults to AUTO with no model preselected", () => {
    render(<RolePoolPicker role="worker" project_id="local" />);
    expect((screen.getByLabelText("Automatic") as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("resolves opaque keys through the default in-memory map", () => {
    const converted = choicesToPoolOptions([
      { providerId: "openai", modelId: "openai/model-1", label: "OpenAI — Standard" },
    ]);
    expect(converted).toHaveLength(1);
    expect(converted[0].key).not.toContain("/");
    expect(converted[0].label).toBe("OpenAI — Standard");
    const resolve = defaultPoolResolver(converted);
    expect(resolve(converted[0].key)).toEqual({ provider: "openai", model: "openai/model-1" });
    expect(resolve("missing")).toBeUndefined();
  });
});

describe("ProvidersPage role pools wiring (page-level)", () => {
  async function connectOpenaiAndEnableStandard() {
    const fetchMock = vi.fn(async () => ({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const connectDialog = screen.getByRole("dialog");
    fireEvent.change(within(connectDialog).getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(within(connectDialog).getByText("Save"));
    expect(await within(connectDialog).findByText(/Reference saved/)).toBeTruthy();
    fireEvent.click(within(connectDialog).getByLabelText("Close"));
    fireEvent.click(screen.getByLabelText("OpenAI Standard"));
    expect((screen.getByLabelText("OpenAI Standard") as HTMLInputElement).checked).toBe(true);
    return fetchMock;
  }

  function roleCard(role: string): HTMLElement {
    const section = screen.getByRole("region", { name: "Role pools" });
    const card = within(section)
      .getAllByTestId("role-pool-picker")
      .find((el) => el.getAttribute("data-role") === role);
    if (!card) {
      throw new Error(`role card missing: ${role}`);
    }
    return card;
  }

  function lastFetchCall(fetchMock: { mock: { calls: unknown[][] } }): {
    url: string;
    init: { method?: string; headers?: Record<string, string>; body?: string };
  } {
    const calls = fetchMock.mock.calls as Array<
      [string, { method?: string; headers?: Record<string, string>; body?: string }]
    >;
    const last = calls[calls.length - 1];
    return { url: last[0], init: last[1] };
  }

  it("role pickers list the real enabled option by label, never raw ids", async () => {
    await connectOpenaiAndEnableStandard();
    const worker = roleCard("worker");
    fireEvent.click(within(worker).getByLabelText("Pinned model"));
    const select = within(worker).getByLabelText("Worker pinned model") as HTMLSelectElement;
    const labels = Array.from(select.options)
      .map((option) => option.textContent ?? "")
      .join(" | ");
    expect(labels).toContain("OpenAI — Standard");
    const text = worker.textContent ?? "";
    expect(text).toContain("OpenAI — Standard");
    expect(text).not.toContain("openai/model-1");
    expect(text).not.toContain("pool-opt-1");
  });

  it("pinning a role PUTs project/role/mode/provider/model header-only, never in the URL", async () => {
    const fetchMock = await connectOpenaiAndEnableStandard();
    const worker = roleCard("worker");
    fireEvent.click(within(worker).getByLabelText("Pinned model"));
    const select = within(worker).getByLabelText("Worker pinned model") as HTMLSelectElement;
    const target = Array.from(select.options).find((option) =>
      (option.textContent ?? "").includes("OpenAI"),
    );
    expect(target).toBeTruthy();
    fireEvent.change(select, { target: { value: (target as HTMLOptionElement).value } });
    expect(await screen.findByText("Saved worker.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalled();
    const { url, init } = lastFetchCall(fetchMock);
    expect(init.method).toBe("PUT");
    expect(url).toBe("/api/v1/roles/pools");
    expect(url).not.toContain("session_token");
    expect(url).not.toContain("local-session");
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body).toMatchObject({
      project_id: "local",
      role: "worker",
      mode: "PINNED",
      provider: "openai",
      model: "openai/model-1",
    });
    expect(body["pool"]).toEqual([]);
    expect(JSON.stringify(body)).not.toContain("session_token");
    expect(init.headers).toMatchObject({ "content-type": "application/json" });
    fetchMock.mockClear();
    fireEvent.click(within(worker).getByLabelText("Automatic"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const autoBody = JSON.parse(lastFetchCall(fetchMock).init.body as string) as Record<
      string,
      unknown
    >;
    expect(autoBody).toMatchObject({ project_id: "local", role: "worker", mode: "AUTO" });
    expect(autoBody["pool"]).toEqual([]);
    expect(autoBody["provider"]).toBeUndefined();
    expect(autoBody["model"]).toBeUndefined();
  });

  it("pool members save with provider/model entries and a plain-language strategy", async () => {
    const fetchMock = await connectOpenaiAndEnableStandard();
    const worker = roleCard("worker");
    fireEvent.click(within(worker).getByLabelText("Model pool"));
    fireEvent.click(within(worker).getByLabelText("OpenAI — Standard"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(await screen.findByText("Saved worker.")).toBeTruthy();
    const { init } = lastFetchCall(fetchMock);
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body).toMatchObject({ project_id: "local", role: "worker", mode: "pool" });
    expect(body["pool"]).toEqual([{ provider_id: "openai", model: "openai/model-1" }]);
    const strategy = within(worker).getByLabelText("Worker pool strategy") as HTMLSelectElement;
    const labels = Array.from(strategy.options)
      .map((option) => option.textContent ?? "")
      .join(" | ");
    expect(labels).toMatch(/fall back/i);
    expect(labels).not.toContain("_");
  });

  it("chat picker lists the real enabled option by label, never raw ids", async () => {
    await connectOpenaiAndEnableStandard();
    const chat = screen.getByTestId("chat-model-selector");
    const select = within(chat).getByLabelText("Chat model") as HTMLSelectElement;
    const labels = Array.from(select.options)
      .map((option) => option.textContent ?? "")
      .join(" | ");
    expect(labels).toContain("OpenAI — Standard");
    const text = chat.textContent ?? "";
    expect(text).not.toContain("openai/model-1");
  });

  it("chat picker change keeps the real enabled option selected by label", async () => {
    await connectOpenaiAndEnableStandard();
    const chat = screen.getByTestId("chat-model-selector");
    const select = within(chat).getByLabelText("Chat model") as HTMLSelectElement;
    const target = Array.from(select.options).find((option) =>
      (option.textContent ?? "").includes("OpenAI"),
    );
    expect(target).toBeTruthy();
    fireEvent.change(select, { target: { value: (target as HTMLOptionElement).value } });
    expect(select.value).toBe((target as HTMLOptionElement).value);
    const selectedLabel =
      Array.from(select.options).find((option) => option.value === select.value)?.textContent ?? "";
    expect(selectedLabel).toContain("Standard");
    const text = chat.textContent ?? "";
    expect(text).not.toContain("openai/model-1");
  });
});

describe("ChatModelSelector", () => {
  it("carries the project id and tolerates missing states", () => {
    render(<ChatModelSelector project_id="proj-7" />);
    expect(screen.getByTestId("chat-model-selector").getAttribute("data-project-id")).toBe("proj-7");
  });
});

describe("LeftoverKeyFinder", () => {
  async function seededKeys(): Promise<SecretStorePort> {
    const store = createMemorySecretStore("sess");
    await store.save(refFor("agent_si/provider/openai", "openai"));
    await store.save(refFor("agent_si/provider/old", "old"));
    await store.save(refFor("unrelated/other", "other"));
    return store;
  }

  it("lists names plus dates under the app prefix only", async () => {
    const store = await seededKeys();
    render(<LeftoverKeyFinder store={store} sessionToken="sess" linkedSecretIds={[]} />);
    expect(await screen.findByText("agent_si/provider/openai")).toBeTruthy();
    expect(screen.getByText("agent_si/provider/old")).toBeTruthy();
    expect(screen.queryByText("unrelated/other")).toBeNull();
    expect(screen.getAllByText(/2026-01-01/).length).toBeGreaterThan(0);
  });

  it("confirms per entry, guards linked entries, audit-logs by name", async () => {
    const store = await seededKeys();
    render(
      <LeftoverKeyFinder store={store} sessionToken="sess" linkedSecretIds={["agent_si/provider/openai"]} />,
    );
    await screen.findByText("agent_si/provider/old");
    expect(screen.queryByLabelText("Delete agent_si/provider/openai")).toBeNull();
    fireEvent.click(screen.getByLabelText("Delete agent_si/provider/old"));
    expect(await screen.findByText("Confirm delete")).toBeTruthy();
    fireEvent.click(screen.getByText("Confirm delete"));
    await waitFor(() => expect(screen.queryByText("agent_si/provider/old")).toBeNull());
    expect(store.audit().map((record) => record.entryName)).toContain("agent_si/provider/old");
  });

  it("loads from a custom loadEntries source when provided", async () => {
    const store = createMemorySecretStore("sess");
    const custom = [refFor("agent_si/provider/custom", "custom")];
    render(
      <LeftoverKeyFinder
        store={store}
        sessionToken="sess"
        linkedSecretIds={[]}
        loadEntries={async () => custom}
      />,
    );
    expect(await screen.findByText("agent_si/provider/custom")).toBeTruthy();
  });

  it("refuses a token-less delete and keeps the entry", async () => {
    const store = await seededKeys();
    render(<LeftoverKeyFinder store={store} sessionToken="" linkedSecretIds={[]} />);
    await screen.findByText("agent_si/provider/old");
    fireEvent.click(screen.getByLabelText("Delete agent_si/provider/old"));
    expect(await screen.findByText("Confirm delete")).toBeTruthy();
    fireEvent.click(screen.getByText("Confirm delete"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("agent_si/provider/old")).toBeTruthy();
    expect(await store.list("agent_si/provider/")).toHaveLength(2);
  });
});

describe("ProvidersPage project setup", () => {
  it("defaults project_id to local and threads it to chat and pool rows", () => {
    render(<ProvidersPage />);
    expect(screen.getByTestId("chat-model-selector").getAttribute("data-project-id")).toBe("local");
    const rows = screen.getAllByTestId("role-pool-picker");
    expect(rows).toHaveLength(ROLE_KEYS.length);
    for (const row of rows) {
      expect(row.getAttribute("data-project-id")).toBe("local");
    }
  });

  it("embeds the setup wizard with every role on AUTO and no defaults", () => {
    render(<ProvidersPage project_id="proj-7" />);
    fireEvent.click(screen.getByText("Show setup wizard"));
    const setup = screen.getByRole("region", { name: "Setup" });
    const selects = within(setup).getAllByRole("combobox") as HTMLSelectElement[];
    expect(selects).toHaveLength(ROLE_KEYS.length);
    for (const select of selects) {
      expect(select.value).toBe(AUTO_SENTINEL);
    }
    expect(screen.getByTestId("chat-model-selector").getAttribute("data-project-id")).toBe("proj-7");
    expect(screen.getAllByTestId("role-pool-picker")[0].getAttribute("data-project-id")).toBe("proj-7");
  });
});

describe("ProvidersPage chat model save wiring (page-level)", () => {
  async function connectOpenaiAndEnableStandardForChat() {
    const fetchMock = vi.fn(
      async (
        _url: string,
        _init: {
          method?: string;
          headers?: Record<string, string>;
          body?: string;
        },
      ) => ({ ok: true }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const connectDialog = screen.getByRole("dialog");
    fireEvent.change(within(connectDialog).getByLabelText("API key"), { target: { value: "sk-test" } });
    fireEvent.click(within(connectDialog).getByText("Save"));
    expect(await within(connectDialog).findByText(/Reference saved/)).toBeTruthy();
    fireEvent.click(within(connectDialog).getByLabelText("Close"));
    fireEvent.click(screen.getByLabelText("OpenAI Standard"));
    expect((screen.getByLabelText("OpenAI Standard") as HTMLInputElement).checked).toBe(true);
    return fetchMock;
  }

  it("chat save PUTs project/model with the header token and keeps the new model shown", async () => {
    const fetchMock = await connectOpenaiAndEnableStandardForChat();
    fetchMock.mockClear();
    const chat = screen.getByTestId("chat-model-selector");
    const select = within(chat).getByLabelText("Chat model") as HTMLSelectElement;
    const target = Array.from(select.options).find((option) =>
      (option.textContent ?? "").includes("OpenAI"),
    );
    expect(target).toBeTruthy();
    fireEvent.change(select, { target: { value: (target as HTMLOptionElement).value } });
    expect(await screen.findByText("Saved chat model.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("PUT");
    expect(url).toBe("/api/v1/roles/chat-model");
    expect(url).not.toContain("session_token");
    expect(url).not.toContain("?");
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
      "x-ui-session-token": "local-session",
    });
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body).toEqual({ project_id: "local", model_id: "openai/model-1" });
    expect(JSON.stringify(body)).not.toContain("session_token");
    expect(JSON.stringify(body)).not.toContain("local-session");
    expect(select.value).toBe("openai/model-1");
    const selectedLabel =
      Array.from(select.options).find((option) => option.value === select.value)?.textContent ?? "";
    expect(selectedLabel).toContain("Standard");
  });
});
