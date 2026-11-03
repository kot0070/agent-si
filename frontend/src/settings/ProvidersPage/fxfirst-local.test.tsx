/** @vitest-environment jsdom */
// FXFIRST item 1: local presets Check/Save with an empty key and really
// probe the local URL (bench check + local-models count). Cloud rows keep
// the key-first two-step and the FXC2 check-first hint. Network boundary
// ONLY (global fetch); FAKE key material only.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { getPreset, PROVIDER_CATALOG } from "./catalog";
import type { ProviderPreset } from "./types";
import { ConnectDialog } from "./ConnectDialog";
import { createMemorySecretStore } from "./secretStore";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { clearUiToken, setUiToken } from "../../api/errors";

function preset(id: string): ProviderPreset {
  const found = getPreset(PROVIDER_CATALOG, id);
  if (!found) {
    throw new Error(`${id} preset missing`);
  }
  return found;
}

function body(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function installFetch(handlers: Record<string, (url: string, body: unknown) => Response>): string[] {
  const seen: string[] = [];
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: { method?: string; body?: string }) => {
      const url = String(input);
      seen.push(url);
      let parsed: unknown = null;
      try {
        parsed = init?.body === undefined ? null : JSON.parse(init.body);
      } catch {
        parsed = null;
      }
      for (const [prefix, handle] of Object.entries(handlers)) {
        if (url.startsWith(prefix)) {
          return handle(url, parsed);
        }
      }
      return body({});
    },
  );
  return seen;
}

function renderDialog(presetId: string, onConnected: () => void = () => undefined) {
  const store = createMemorySecretStore("fxfirst-local-sess");
  render(
    <ConnectDialog
      preset_id={presetId}
      preset={preset(presetId)}
      open
      store={store}
      onClose={() => undefined}
      onConnected={onConnected}
    />,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  setUiToken("fxfirst-token");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
});

describe("fxfirst local preset check plus save with empty key", () => {
  it("Check stays enabled empty and reports the probed model count", async () => {
    const seen = installFetch({
      "/api/v1/local/bench/check": () => body({ reachable: true, reason: "IDLE" }),
      "/api/v1/local/models": () =>
        body({ models: [{ model: "http://localhost:11434" }, { model: "http://localhost:11434" }] }),
    });
    renderDialog("ollama");
    const dialog = await screen.findByRole("dialog");
    const check = within(dialog).getByRole("button", { name: en.providers.connect.check });
    expect((check as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(check);
    await within(dialog).findByText(
      en.providers.connect.localFound.replace("{count}", "2"),
    );
    expect(seen.some((url) => url.startsWith("/api/v1/local/bench/check"))).toBe(true);
    expect(
      seen.some((url) => url.includes(`endpoint=${encodeURIComponent("http://localhost:11434")}`)),
    ).toBe(true);
    expect(seen).toContain("/api/v1/local/models");
  });

  it("Check names a down server plainly with no raw code in the sentence", async () => {
    installFetch({
      "/api/v1/local/bench/check": () => body({ reachable: false, reason: "unreachable" }),
    });
    renderDialog("ollama");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: en.providers.connect.check }));
    const line = await within(dialog).findByText(
      en.providers.connect.localNotRunning.replace("{label}", "Ollama"),
    );
    expect(line.textContent).not.toContain("CONTEXT_");
    expect(line.textContent).not.toContain("reachable");
  });

  it("Save stays enabled empty and attaches through connectLocal", async () => {
    let connectedBody: unknown = null;
    const seen = installFetch({
      "/api/v1/local/connect": (_url, parsed) => {
        connectedBody = parsed;
        return body({ connected: true });
      },
      "/api/v1/providers/ollama/models": () => body({}),
    });
    let connected = 0;
    renderDialog("ollama", () => {
      connected += 1;
    });
    const dialog = await screen.findByRole("dialog");
    const save = within(dialog).getByRole("button", { name: en.providers.connect.save });
    expect((save as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(save);
    await within(dialog).findByText(
      en.providers.connect.connected.replace("{label}", "Ollama"),
    );
    expect(connected).toBe(1);
    expect(seen).toContain("/api/v1/local/connect");
    expect(connectedBody).toEqual({ runtime_ref: "http://localhost:11434" });
  });

  it("local rows never show the cloud check-first hint", async () => {
    installFetch({
      "/api/v1/local/bench/check": () => body({ reachable: true, reason: "IDLE" }),
      "/api/v1/local/models": () => body({ models: [] }),
    });
    renderDialog("ollama");
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(en.providers.connect.apiKey), {
      target: { value: "fx-fake-key" },
    });
    expect(within(dialog).queryByTestId("connect-check-first")).toBeNull();
  });

  it("cloud rows keep the key-first two-step with empty key disabled", async () => {
    installFetch({
      "/api/v1/providers/keys/check": () => body({ ok: true }),
    });
    renderDialog("openai");
    const dialog = await screen.findByRole("dialog");
    const check = within(dialog).getByRole("button", { name: en.providers.connect.check });
    const save = within(dialog).getByRole("button", { name: en.providers.connect.save });
    expect((check as HTMLButtonElement).disabled).toBe(true);
    expect((save as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(en.providers.connect.apiKey), {
      target: { value: "sk-test" },
    });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    expect(await within(dialog).findByTestId("connect-check-first")).toBeTruthy();
    fireEvent.click(check);
    await within(dialog).findByText(en.providers.connect.checked);
    expect((save as HTMLButtonElement).disabled).toBe(false);
  });

  it("uk locale resolves the local probe sentence", async () => {
    setLocale("uk");
    installFetch({
      "/api/v1/local/bench/check": () => body({ reachable: true, reason: "IDLE" }),
      "/api/v1/local/models": () => body({ models: [{ model: "http://localhost:11434" }] }),
    });
    renderDialog("ollama");
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: uk.providers.connect.check }));
    await within(dialog).findByText(
      uk.providers.connect.localFound.replace("{count}", "1"),
    );
  });
});
