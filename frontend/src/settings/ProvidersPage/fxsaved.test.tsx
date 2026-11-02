/**
 * @vitest-environment jsdom
 * FXSAVED restart-persistence tests (RED first): after a restart
 * (unmount + remount) the page shows what the user saved, and the
 * load itself never writes (PUT count unchanged by the load).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { setLocale, resetLocaleForTests, t } from "../../locale/index";
import { LocaleProvider } from "../../locale/index";
import uk from "../../locale/uk.json";
import { ChatModelSelector } from "./ChatModelSelector";
import { RolePoolPicker } from "./RolePoolPicker";
import type { ProviderPreset } from "./types";

type SeenCall = {
  url: string;
  method: string;
  body: string;
};

function programFetch(handler: (url: string, init: RequestInit) => unknown) {
  const seen: SeenCall[] = [];
  const mock = vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    seen.push({
      url,
      method: (init?.method ?? "GET").toUpperCase(),
      body: typeof init?.body === "string" ? init.body : "",
    });
    return handler(url, init ?? {});
  });
  vi.stubGlobal("fetch", mock);
  return seen;
}

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

function httpError(status: number, body: unknown) {
  return { ok: false, status, json: async () => body };
}

function putsTo(seen: SeenCall[], url: string): SeenCall[] {
  return seen.filter((call) => call.url === url && call.method === "PUT");
}

const CATALOG: ProviderPreset[] = [
  {
    id: "openai",
    label: "OpenAI",
    kind: "cloud",
    group: "Cloud",
    baseUrl: "https://api.openai.com",
    keyHint: "hint",
    keyStartsWith: "sk-",
    models: [{ id: "openai/gpt-4o-mini", label: "GPT-4o mini" }],
  },
];

const STATES = {
  openai: {
    presetId: "openai",
    connected: true,
    enabledModels: ["openai/gpt-4o-mini"],
  },
};

function chatLabel(): string {
  return t("providers.chat.label");
}

beforeEach(() => {
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("FXSAVED item 1: chat model survives restart", () => {
  it("mount shows the saved model and the load fires no PUT", async () => {
    const seen = programFetch((url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.startsWith("/api/v1/roles/chat-model") && method === "GET") {
        return ok({ project_id: "p1", model_id: "openai/gpt-4o-mini" });
      }
      return ok({});
    });
    const first = render(
      <ChatModelSelector
        project_id="p1"
        states={STATES}
        catalog={CATALOG}
        onChange={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(
        (screen.getByLabelText(chatLabel()) as HTMLSelectElement).value,
      ).toBe("openai/gpt-4o-mini");
    });
    expect(putsTo(seen, "/api/v1/roles/chat-model")).toHaveLength(0);
    first.unmount();
    render(
      <ChatModelSelector
        project_id="p1"
        states={STATES}
        catalog={CATALOG}
        onChange={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(
        (screen.getByLabelText(chatLabel()) as HTMLSelectElement).value,
      ).toBe("openai/gpt-4o-mini");
    });
    expect(putsTo(seen, "/api/v1/roles/chat-model")).toHaveLength(0);
  });
});

describe("FXSAVED item 2: role pools survive restart", () => {
  it("PINNED role shows the saved key and the load fires no PUT", async () => {
    const seen = programFetch((url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.startsWith("/api/v1/routing/role") && method === "GET") {
        return ok({
          profile: {
            role: "worker",
            project_id: "p1",
            mode: "PINNED",
            provider: "openai",
            model: "openai/model-1",
            binding: "DEFAULT",
            version: 1,
          },
        });
      }
      return ok({});
    });
    const options = [
      {
        key: "pool-opt-1",
        label: "OpenAI — Standard",
        providerId: "openai",
        modelId: "openai/model-1",
      },
    ];
    const first = render(
      <RolePoolPicker role="worker" project_id="p1" options={options} />,
    );
    await waitFor(() => {
      const radios = screen.getAllByRole("radio");
      const pinned = radios[0] as HTMLInputElement;
      expect(pinned.checked).toBe(true);
    });
    expect(putsTo(seen, "/api/v1/roles/pools")).toHaveLength(0);
    first.unmount();
    render(<RolePoolPicker role="worker" project_id="p1" options={options} />);
    await waitFor(() => {
      const radios = screen.getAllByRole("radio");
      expect((radios[0] as HTMLInputElement).checked).toBe(true);
    });
    expect(putsTo(seen, "/api/v1/roles/pools")).toHaveLength(0);
  });

  it("a pinned key missing from options still shows, marked unavailable", async () => {
    programFetch((url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.startsWith("/api/v1/routing/role") && method === "GET") {
        return ok({
          profile: {
            role: "worker",
            project_id: "p1",
            mode: "PINNED",
            provider: "gone-provider",
            model: "gone-model",
            binding: "DEFAULT",
            version: 1,
          },
        });
      }
      return ok({});
    });
    render(<RolePoolPicker role="worker" project_id="p1" options={[]} />);
    await waitFor(() => {
      const radios = screen.getAllByRole("radio");
      expect((radios[0] as HTMLInputElement).checked).toBe(true);
    });
    const selects = screen.getAllByRole("combobox");
    expect(selects.length).toBeGreaterThan(0);
    const pinned = selects[0] as HTMLSelectElement;
    expect(pinned.value).not.toBe("");
    expect(pinned.textContent).toMatch(/unavailable/);
    const auto = screen.getAllByRole("radio")[2] as HTMLInputElement;
    expect(auto.checked).toBe(false);
  });
});

describe("FXSAVED item 4: stored locale paints on first render", () => {
  it("uk in storage renders Ukrainian with no TopBar mounted", () => {
    window.localStorage.setItem("agentsi.locale", "uk");
    function Probe(): ReactElement {
      return <span data-testid="probe">{t("shell.sidebar.chat")}</span>;
    }
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("probe").textContent).toBe(
      (uk as unknown as Record<string, Record<string, Record<string, string>>>)
        .shell.sidebar.chat,
    );
  });
});
