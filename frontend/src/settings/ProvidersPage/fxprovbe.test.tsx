/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProvidersPage } from "./ProvidersPage";

const FX_TOKEN = "fx-ui-token-be";

type SeenCall = {
  url: string;
  init: { method?: string; headers?: Record<string, string>; body?: string };
};

function programFetch(handler: (url: string, init: SeenCall["init"]) => unknown) {
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

const NEW_SHAPE = {
  provider_id: "openai",
  models: [
    { id: "openai/gpt-4o-mini", name: "gpt-4o-mini", price: 3.0, kb_known: true },
    { id: "openai/gpt-4o", name: "gpt-4o", price: null, kb_known: false },
  ],
  source: "provider",
  enabled: ["openai/gpt-4o-mini"],
};

const REFRESHED_SHAPE = {
  provider_id: "openai",
  models: [
    { id: "openai/gpt-4o-mini", name: "gpt-4o-mini", price: 3.0, kb_known: true },
    { id: "openai/gpt-4o", name: "gpt-4o", price: null, kb_known: false },
    { id: "openai/o3", name: "o3", price: null, kb_known: false },
  ],
  source: "provider",
  enabled: ["openai/gpt-4o-mini"],
};

function baseHandler(url: string): unknown {
  if (url === "/api/v1/providers") {
    return ok({ providers: [] });
  }
  if (url === "/api/v1/providers/keys") {
    return { ok: true, status: 201, json: async () => ({ key_ref: { secret_id: "openai", provider_id: "openai" } }) };
  }
  if (url === "/api/v1/providers/connect") {
    return ok({ provider: { provider_id: "openai" } });
  }
  if (url === "/api/v1/providers/openai/models") {
    return ok(NEW_SHAPE);
  }
  return ok({});
}

async function openStep2() {
  render(<ProvidersPage project_id="local" />);
  setUiToken(FX_TOKEN);
  fireEvent.click(screen.getByLabelText("Connect OpenAI"));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("API key"), { target: { value: "sk-test-1" } });
  // FXR2E two-step (416ddaa, merged 0661228): Check before Save.
  fireEvent.click(within(dialog).getByText("Check"));
  await within(dialog).findByText("Key checked. Save to connect.");
  fireEvent.click(within(dialog).getByText("Save"));
  await within(dialog).findByText("Connected OpenAI. Reference saved.");
  return dialog;
}

beforeEach(() => {
  setLocale("en");
  setUiToken(FX_TOKEN);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
});

describe("fxprovbe done PUTs ticks and refresh re-reads", () => {
  it("Done PUTs ticked ids; Manage reopens from the served enabled list", async () => {
    const seen = programFetch((url) => baseHandler(url));
    const dialog = await openStep2();
    // Served truth ticks only the default model.
    const boxes = within(dialog).getAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    // Tick the second model too, then Done.
    fireEvent.click(boxes[1]);
    fireEvent.click(within(dialog).getByText("Done"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const puts = seen.filter(
      (call) => call.url === "/api/v1/providers/openai/models" && call.init.method === "PUT",
    );
    expect(puts).toHaveLength(1);
    expect(JSON.parse(puts[0].init.body as string)).toEqual({
      ids: ["openai/gpt-4o-mini", "openai/gpt-4o"],
    });
  });

  it("Refresh button POSTs the refresh route and shows the new row", async () => {
    const seen = programFetch((url, init) => {
      if (url === "/api/v1/providers/openai/models/refresh" && init.method === "POST") {
        return ok(REFRESHED_SHAPE);
      }
      return baseHandler(url);
    });
    const dialog = await openStep2();
    fireEvent.click(within(dialog).getByText("Refresh models"));
    await within(dialog).findByText("o3");
    const posts = seen.filter(
      (call) => call.url === "/api/v1/providers/openai/models/refresh",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0].init.method).toBe("POST");
  });

  it("a failed refresh keeps the last list plus a calm line", async () => {
    programFetch((url, init) => {
      if (url === "/api/v1/providers/openai/models/refresh" && init.method === "POST") {
        return { ok: false, status: 502, json: async () => ({ error: "provider model list unavailable (keeping the last list)" }) };
      }
      return baseHandler(url);
    });
    const dialog = await openStep2();
    expect(within(dialog).getByText("gpt-4o-mini")).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Refresh models"));
    await within(dialog).findByText("Couldn't refresh the live list — keeping the last list.");
    // The last list is still there.
    expect(within(dialog).getByText("gpt-4o-mini")).toBeTruthy();
  });
});
