/** @vitest-environment jsdom */
// FXLOCAL L1: the Local LLM settings route connects local presets on the page.
// Network boundary ONLY (global fetch); no real Ollama or LM Studio.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { SETTINGS_ROUTES } from "../index";
import { SettingsLayout } from "../../shell/SettingsLayout";
import { LocalConnectSection } from "../ProvidersPage/LocalConnectSection";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { clearUiToken, setUiToken } from "../../api/errors";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";

function body(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Handler = (url: string, parsed: unknown) => Response;

function installFetch(handlers: Record<string, Handler>): string[] {
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

// Down servers: no registry rows, no local runtime, probes unreachable.
function installDownServers(): void {
  installFetch({
    "/api/v1/providers": () => body({ providers: [] }),
    "/api/v1/local/models": () => body({ models: [] }),
    "/api/v1/local/bench/check": () =>
      body({ reachable: false, reason: "unreachable" }),
  });
}

function renderRealLocalRoute(): void {
  const route = SETTINGS_ROUTES.find((entry) => entry.path === "localAI");
  if (route === undefined) {
    throw new Error("missing localAI settings route");
  }
  render(
    <SettingsLayout
      titleKey={route.titleKey}
      purposeKey={route.purposeKey}
      needItNowKey={route.needItNowKey}
    >
      <LocalConnectSection />
    </SettingsLayout>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  setUiToken("fxlocal-token");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
});

describe("fxlocal connect section on the real settings route", () => {
  it("lists one row per local preset with its URL and a Connect button", async () => {
    installDownServers();
    renderRealLocalRoute();
    const ollama = await screen.findByTestId("local-preset-ollama");
    const lmstudio = await screen.findByTestId("local-preset-lm-studio");
    expect(within(ollama).getByText("Ollama")).toBeTruthy();
    expect(
      within(ollama).getByTestId("local-url-ollama").textContent,
    ).toBe("http://localhost:11434");
    expect(within(lmstudio).getByText("LM Studio")).toBeTruthy();
    expect(
      within(lmstudio).getByTestId("local-url-lm-studio").textContent,
    ).toBe("http://localhost:1234/v1");
    expect(
      within(ollama).getByRole("button", {
        name: en.providers.page.connectCta.replace("{label}", "Ollama"),
      }),
    ).toBeTruthy();
    expect(
      within(lmstudio).getByRole("button", {
        name: en.providers.page.connectCta.replace("{label}", "LM Studio"),
      }),
    ).toBeTruthy();
  });

  it("reads the existing not-running sentence when a server is down", async () => {
    installDownServers();
    renderRealLocalRoute();
    await screen.findByTestId("local-preset-ollama");
    expect(
      await screen.findByText(
        en.providers.connect.localNotRunning.replace("{label}", "Ollama"),
      ),
    ).toBeTruthy();
    expect(
      await screen.findByText(
        en.providers.connect.localNotRunning.replace("{label}", "LM Studio"),
      ),
    ).toBeTruthy();
  });

  it("Connect opens the same connect dialog for the preset", async () => {
    installDownServers();
    renderRealLocalRoute();
    const ollama = await screen.findByTestId("local-preset-ollama");
    fireEvent.click(
      within(ollama).getByRole("button", {
        name: en.providers.page.connectCta.replace("{label}", "Ollama"),
      }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(
        en.providers.connect.title.replace("{label}", "Ollama"),
      ),
    ).toBeTruthy();
  });

  it("the local dialog shows no API key field, Check and Save stay", async () => {
    installDownServers();
    renderRealLocalRoute();
    const ollama = await screen.findByTestId("local-preset-ollama");
    fireEvent.click(
      within(ollama).getByRole("button", {
        name: en.providers.page.connectCta.replace("{label}", "Ollama"),
      }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText(en.providers.connect.apiKey)).toBeNull();
    expect(dialog.querySelector("input")).toBeNull();
    expect(
      within(dialog).getByRole("button", { name: en.providers.connect.check }),
    ).toBeTruthy();
    expect(
      within(dialog).getByRole("button", { name: en.providers.connect.save }),
    ).toBeTruthy();
  });

  it("served connected state flips the button to Disconnect", async () => {
    installFetch({
      "/api/v1/providers": () => body({ providers: [] }),
      "/api/v1/local/models": () =>
        body({ models: [{ model: "http://localhost:11434" }] }),
      "/api/v1/local/bench/check": () =>
        body({ reachable: true, reason: "IDLE" }),
    });
    renderRealLocalRoute();
    const ollama = await screen.findByTestId("local-preset-ollama");
    expect(
      await within(ollama).findByRole("button", {
        name: en.providers.page.disconnectCta.replace("{label}", "Ollama"),
      }),
    ).toBeTruthy();
    expect(
      within(ollama).queryByRole("button", {
        name: en.providers.page.connectCta.replace("{label}", "Ollama"),
      }),
    ).toBeNull();
  });

  it("Save through the dialog flips the row to Disconnect", async () => {
    installFetch({
      "/api/v1/providers": () => body({ providers: [] }),
      "/api/v1/local/models": () => body({ models: [] }),
      "/api/v1/local/bench/check": () =>
        body({ reachable: true, reason: "IDLE" }),
      "/api/v1/local/connect": () => body({ connected: true }),
      "/api/v1/providers/ollama/models": () => body({}),
    });
    renderRealLocalRoute();
    const ollama = await screen.findByTestId("local-preset-ollama");
    fireEvent.click(
      within(ollama).getByRole("button", {
        name: en.providers.page.connectCta.replace("{label}", "Ollama"),
      }),
    );
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(
      within(dialog).getByRole("button", { name: en.providers.connect.save }),
    );
    // The dialog moves to step 2 itself; the row underneath flips.
    await within(dialog).findByText(
      en.providers.connect.connected.replace("{label}", "Ollama"),
    );
    expect(
      await within(ollama).findByRole("button", {
        name: en.providers.page.disconnectCta.replace("{label}", "Ollama"),
      }),
    ).toBeTruthy();
  });

  it("Disconnect opens the same disconnect dialog and confirm flips back", async () => {
    installFetch({
      "/api/v1/providers": () => body({ providers: [] }),
      "/api/v1/local/models": () =>
        body({ models: [{ model: "http://localhost:11434" }] }),
      "/api/v1/local/bench/check": () =>
        body({ reachable: true, reason: "IDLE" }),
      "/api/v1/local/disconnect": () => body({ disconnected: true }),
    });
    renderRealLocalRoute();
    const ollama = await screen.findByTestId("local-preset-ollama");
    fireEvent.click(
      await within(ollama).findByRole("button", {
        name: en.providers.page.disconnectCta.replace("{label}", "Ollama"),
      }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(
        en.providers.disconnect.title.replace("{label}", "Ollama"),
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByTestId("disconnect-confirm"));
    await within(ollama).findByRole("button", {
      name: en.providers.page.connectCta.replace("{label}", "Ollama"),
    });
  });
});

describe("fxlocal empty-state locale parity", () => {
  it("names the same one-sentence empty key in en and uk", () => {
    expect(en.settings.localAi.empty.length).toBeGreaterThan(0);
    expect(uk.settings.localAi.empty.length).toBeGreaterThan(0);
    expect(t("settings.localAi.empty")).toBe(en.settings.localAi.empty);
    setLocale("uk");
    expect(t("settings.localAi.empty")).toBe(uk.settings.localAi.empty);
  });
});
