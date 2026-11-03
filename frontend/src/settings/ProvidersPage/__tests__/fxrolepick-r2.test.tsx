// FXROLEPICK R2: the local card with a connected runtime lists the
// real served names (fake at the network only), warns quietly on a
// model with no capability row, and Use for agents pins the worker
// through the normal role save.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../../api/errors";
import { resetLocaleForTests, setLocale } from "../../../locale/index";
import { LocalConnectSection } from "../LocalConnectSection";

const OLLAMA_MODELS = {
  provider_id: "ollama",
  models: [
    {
      id: "ollama/llama3.2",
      name: "llama3.2",
      price: null,
      kb_known: false,
    },
    {
      id: "ollama/mistral-7b",
      name: "mistral-7b",
      price: null,
      kb_known: true,
    },
  ],
  source: "local",
  enabled: [],
};

type SeenCall = { url: string; init: { method?: string; body?: string } };

function stubNetwork(): SeenCall[] {
  const calls: SeenCall[] = [];
  const json = (data: unknown, status = 200): Response =>
    new Response(JSON.stringify(data), {
      status,
      headers: { "content-type": "application/json" },
    });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      calls.push({ url, init: { method, body: String(init?.body ?? "") } });
      if (url === "/api/v1/providers") {
        return json({ providers: [] });
      }
      if (url.startsWith("/api/v1/local/bench/check")) {
        const endpoint = new URL(url, "http://x").searchParams.get("endpoint") ?? "";
        const reachable = endpoint.includes("11434");
        return json({ reachable, reason: reachable ? "open" : "closed" });
      }
      if (url === "/api/v1/local/models") {
        return json([
          { model: "http://localhost:11434", evidence_tier: "PROXY", status: "READY" },
        ]);
      }
      if (url === "/api/v1/providers/ollama/models") {
        return json(OLLAMA_MODELS);
      }
      if (url === "/api/v1/roles/pools" && method === "PUT") {
        return json({ ok: true });
      }
      return json({});
    }),
  );
  return calls;
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  clearUiToken();
  setUiToken("r2-token");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("R2 local card", () => {
  it("lists real names, warns on no capability row, pins the worker", async () => {
    const calls = stubNetwork();
    render(<LocalConnectSection />);
    const card = await screen.findByTestId("local-preset-ollama");
    const select = await within(card).findByTestId(
      "local-models-ollama",
    ) as HTMLSelectElement;
    expect(card.textContent).toContain("Connected Ollama, 2 models.");
    const names = Array.from(select.options).map((option) => option.textContent ?? "");
    expect(names).toEqual(["llama3.2", "mistral-7b"]);
    expect(card.textContent).toContain(
      "No capability data for llama3.2; it can still be used.",
    );
    expect(card.textContent).not.toContain("ollama/model-");
    fireEvent.change(select, { target: { value: "ollama/llama3.2" } });
    fireEvent.click(within(card).getByTestId("local-use-ollama"));
    expect(await within(card).findByText("Worker model set to llama3.2.")).toBeTruthy();
    const puts = calls.filter(
      (call) => call.url === "/api/v1/roles/pools" && call.init.method === "PUT",
    );
    expect(puts).toHaveLength(1);
    expect(JSON.parse(puts[0].init.body as string)).toMatchObject({
      project_id: "local",
      role: "worker",
      mode: "PINNED",
      provider: "ollama",
      model: "ollama/llama3.2",
    });
  });

  it("not running reads the plain sentence with one Connect button", async () => {
    stubNetwork();
    render(<LocalConnectSection />);
    const card = await screen.findByTestId("local-preset-lm-studio");
    expect(card.textContent).toContain("Local server is not running");
    expect(within(card).queryByTestId("local-models-lm-studio")).toBeNull();
  });
});
