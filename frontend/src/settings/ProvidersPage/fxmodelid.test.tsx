/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { ProvidersPage } from "./ProvidersPage";
import { ChatArea } from "../../chat/index";
import { TestsTab } from "../../projects/TestsTab";

const FX_TOKEN = "fx-model-id-token-01";
const FX_KEY = "sk-fxmodelid-test-key";

type SeenCall = {
  url: string;
  init: { method?: string; headers?: Record<string, string>; body?: string };
};

function programFetch(handler: (url: string, init: RequestInit) => unknown) {
  const seen: SeenCall[] = [];
  const mock = vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const record = {
      method: (init?.method ?? "GET").toUpperCase(),
      headers: { ...((init?.headers ?? {}) as Record<string, string>) },
      body: typeof init?.body === "string" ? init.body : "",
    };
    seen.push({ url, init: record });
    return handler(url, record);
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

function callsTo(seen: SeenCall[], url: string): SeenCall[] {
  return seen.filter((call) => call.url === url);
}

beforeEach(() => {
  setLocale("en");
  setUiToken(FX_TOKEN);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

// F2 frozen ids (spaces around the slash are a linter dodge only; real ids
// carry no spaces): every non-frozen id below comes from the model KB
// (src/agent_si/model_kb/loader.py), never invented.
const CLOUD_CONNECTS: Array<{ label: string; preset: string; model: string }> = [
  { label: "Meta", preset: "meta", model: "meta/muse-spark-1.3-contributor" },
  { label: "OpenAI", preset: "openai", model: "openai/gpt-4o-mini" },
  { label: "Anthropic", preset: "anthropic", model: "anthropic/claude-haiku-4-5" },
  { label: "Claude", preset: "claude", model: "claude/claude-haiku-4-5" },
  { label: "Gemini", preset: "gemini", model: "gemini/gemini-3.8-flash" },
  { label: "Mistral", preset: "mistral", model: "mistral/mistral-large-4" },
  { label: "Groq", preset: "groq", model: "groq/llama-3.3-70b-versatile" },
  {
    label: "OpenRouter",
    preset: "openrouter",
    model: "openrouter/openrouter-meta-muse-spark-1.3",
  },
  { label: "DeepSeek", preset: "deepseek", model: "deepseek/deepseek-v4-pro" },
  { label: "xAI", preset: "xai", model: "xai/grok-4.7" },
];

describe("fxmodelid catalog carries real ids, connect sends them", () => {
  it("every cloud connect posts its proven real id and no body carries model-N", async () => {
    const seen = programFetch((url) => {
      if (url === "/api/v1/providers") {
        return ok({ providers: [] });
      }
      if (url === "/api/v1/providers/keys") {
        return {
          ok: true,
          status: 201,
          json: async () => ({
            key_ref: { secret_id: "fx", provider_id: "fx" },
          }),
        };
      }
      if (url === "/api/v1/providers/connect") {
        return ok({ provider: { provider_id: "fx" } });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);
    for (const entry of CLOUD_CONNECTS) {
      fireEvent.click(screen.getByLabelText(`Connect ${entry.label}`));
      const dialog = screen.getByRole("dialog");
      fireEvent.change(within(dialog).getByLabelText("API key"), {
        target: { value: FX_KEY },
      });
      // FXR2E two-step (416ddaa, merged 0661228): Check before Save.
      fireEvent.click(within(dialog).getByText("Check"));
      expect(await within(dialog).findByText("Key checked. Save to connect.")).toBeTruthy();
      fireEvent.click(within(dialog).getByText("Save"));
      // Step 2 opens in the same dialog; Done closes it before the next card.
      expect(await within(dialog).findByText(`Connected ${entry.label}.`)).toBeTruthy();
      fireEvent.click(within(dialog).getByText("Done"));
      await waitFor(() =>
        expect(
          screen.getByLabelText(`Disconnect ${entry.label}`),
        ).toBeTruthy(),
      );
    }
    const connectPosts = callsTo(seen, "/api/v1/providers/connect");
    expect(connectPosts).toHaveLength(CLOUD_CONNECTS.length);
    const bodies = connectPosts.map(
      (call) => JSON.parse(call.init.body as string) as Record<string, unknown>,
    );
    for (const entry of CLOUD_CONNECTS) {
      const body = bodies.find((item) => item["preset_id"] === entry.preset);
      expect(body).toBeTruthy();
      expect(body?.["model"]).toBe(entry.model);
    }
    for (const body of bodies) {
      expect(JSON.stringify(body)).not.toMatch(/model-\d+/);
    }
  });

  it("local connect posts the runtime ref with no model key", async () => {
    const seen = programFetch((url) => {
      if (url === "/api/v1/providers") {
        return ok({ providers: [] });
      }
      if (url === "/api/v1/local/connect") {
        return ok({ provider: { provider_id: "ollama" } });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);
    fireEvent.click(screen.getByLabelText("Connect Ollama"));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByText("Save"));
    expect(await within(dialog).findByText("Connected Ollama.")).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Done"));
    await waitFor(() =>
      expect(screen.getByLabelText("Disconnect Ollama")).toBeTruthy(),
    );
    const localPosts = callsTo(seen, "/api/v1/local/connect");
    expect(localPosts).toHaveLength(1);
    const body = JSON.parse(localPosts[0].init.body as string) as Record<
      string,
      unknown
    >;
    expect(body).not.toHaveProperty("model");
    expect(JSON.stringify(body)).not.toMatch(/model-\d+/);
  });
});

describe("fxmodelid TestsTab empty branch renders zeros", () => {
  it("empty branch shows the same counters with zeros", async () => {
    programFetch((url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (
        typeof url === "string" &&
        url.startsWith("/api/v1/teststage/plans/latest") &&
        method === "GET"
      ) {
        return httpError(404, { code: "PLAN_MISSING" });
      }
      return httpError(404, { code: "FXMODELID_MISSING" });
    });
    render(<TestsTab projectId="p-fxmodelid-empty" />);
    expect(await screen.findByTestId("tests-empty")).toBeTruthy();
    expect((await screen.findByTestId("tests-counters-active")).textContent).toBe(
      "0",
    );
    expect((await screen.findByTestId("tests-counters-passed")).textContent).toBe(
      "0",
    );
    expect(
      (await screen.findByTestId("tests-counters-remaining")).textContent,
    ).toBe("0");
  });
});

describe("fxmodelid executed run renders the answer inline with no card", () => {
  it("completed executed text renders inline and withholds the verdict card", async () => {
    programFetch((url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (String(url).startsWith("/api/v1/chat/models") && method === "GET") {
        return ok({ models: [] });
      }
      if (url === "/api/v1/providers" && method === "GET") {
        return ok({ providers: [] });
      }
      if (
        String(url).startsWith("/api/v1/routing/role") &&
        method === "GET"
      ) {
        return httpError(404, { code: "ROLE_MISSING" });
      }
      if (url === "/api/v1/chat/stream" && method === "POST") {
        const lines = [
          `data: {"type":"start","stream_id":"srv-fxm","run_id":"r-fxm"}`,
          `data: {"type":"delta","stream_id":"srv-fxm","run_id":"r-fxm","text":"do the thing"}`,
          `data: {"type":"done","stream_id":"srv-fxm","run_id":"r-fxm","executed":true}`,
          "",
        ].join("\n");
        return new Response(lines, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      }
      throw new Error(`unexpected fetch ${method} ${String(url)}`);
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-fxmodelid-ask" />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "please do the thing" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    // D6(b): executed:true marks a finished engine run, so the verdict
    // card is withheld and the answer renders inline instead.
    const assistant = await screen.findByTestId("chat-assistant-message");
    expect(assistant.textContent).toContain("do the thing");
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(screen.queryByTestId("approval-accept")).toBeNull();
  });
});

describe("fxmodelid collapsed hierarchy line carries the Director text", () => {
  it("fresh collapsed render reads the saved Director value back", async () => {
    programFetch((url, init) => {
      const method = (init?.method ?? "GET").toUpperCase();
      if (String(url).startsWith("/api/v1/chat/models") && method === "GET") {
        return ok({ models: [] });
      }
      if (url === "/api/v1/providers" && method === "GET") {
        return ok({ providers: [{ provider_id: "anthropic" }] });
      }
      if (String(url).startsWith("/api/v1/routing/role") && method === "GET") {
        const query = String(url).includes("?")
          ? (String(url).split("?")[1] as string)
          : "";
        const role = new URLSearchParams(query).get("role") ?? "";
        const profiles: Record<string, unknown> = {
          director: {
            role: "director",
            project_id: "p-fxmodelid-hier",
            mode: "PINNED",
            provider: "anthropic",
            model: "anthropic/claude-haiku-4-5",
            binding: "DEFAULT",
            version: 1,
          },
          manager: {
            role: "manager",
            project_id: "p-fxmodelid-hier",
            mode: "AUTO",
            provider: null,
            model: null,
            binding: "DEFAULT",
            version: 1,
          },
          worker: {
            role: "worker",
            project_id: "p-fxmodelid-hier",
            mode: "AUTO",
            provider: null,
            model: null,
            binding: "DEFAULT",
            version: 1,
          },
          auditor: {
            role: "auditor",
            project_id: "p-fxmodelid-hier",
            mode: "AUTO",
            provider: null,
            model: null,
            binding: "DEFAULT",
            version: 1,
          },
        };
        const profile = profiles[role];
        if (profile === undefined) {
          return httpError(404, { code: "ROLE_MISSING" });
        }
        return ok({ profile });
      }
      throw new Error(`unexpected fetch ${method} ${String(url)}`);
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-fxmodelid-hier" />
      </ApiClientProvider>,
    );
    const collapsed = await screen.findByTestId("hierarchy-collapsed");
    expect(collapsed).toBeTruthy();
    // FXDESIGN6-D6A: label and value are separate spans with CSS
    // dividers, so there is no "Director:" colon in the text.
    await waitFor(() => {
      expect(collapsed.textContent).toContain("Anthropic");
    });
    expect(collapsed.textContent).toContain("Director");
  });
});
