/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { clearUiToken, getUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProvidersPage } from "./ProvidersPage";

const FX_TOKEN = "fx-ui-token-01";
const FX_KEY = "fixture-connect-value";

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

function setFxTokenAfterMount(): void {
  // The mounted page keeps its frozen session default; the operator token
  // arrives after mount (login completes later), so set it after render.
  setUiToken(FX_TOKEN);
  expect(getUiToken()).toBe(FX_TOKEN);
}

// The default locale is uk; these assertions read the English labels. The
// page reads the window token, so the suite provides it before mount.
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

describe("fxconnect save posts the connect route with the operator token", () => {
  it("fill key + Save posts keys then one connect POST; 200 connects and clears the field", async () => {
    const seen = programFetch((url) => {
      if (url === "/api/v1/providers") {
        return ok({ providers: [] });
      }
      if (url === "/api/v1/providers/keys") {
        return { ok: true, status: 201, json: async () => ({ key_ref: { secret_id: "openai", provider_id: "openai" } }) };
      }
      if (url === "/api/v1/providers/connect") {
        return ok({ provider: { provider_id: "openai" } });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);
    setFxTokenAfterMount();
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("API key"), { target: { value: FX_KEY } });
    fireEvent.click(within(dialog).getByText("Save"));
    // Step 1 done: the same dialog moves to step 2 (Connected line plus
    // the tickable list); the key field is gone with step 1.
    expect(await within(dialog).findByText("Connected OpenAI. Reference saved.")).toBeTruthy();
    expect(screen.queryByLabelText("API key")).toBeNull();
    fireEvent.click(within(dialog).getByText("Done"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByLabelText("Disconnect OpenAI")).toBeTruthy();
    expect(screen.getByText("Connected OpenAI. Reference saved.")).toBeTruthy();

    const keyPosts = callsTo(seen, "/api/v1/providers/keys");
    expect(keyPosts).toHaveLength(1);
    expect(keyPosts[0].init.method).toBe("POST");
    expect(keyPosts[0].init.headers?.["x-ui-session-token"]).toBe(FX_TOKEN);
    expect(JSON.parse(keyPosts[0].init.body as string)).toEqual({
      preset_id: "openai",
      key_value: FX_KEY,
    });

    const connectPosts = callsTo(seen, "/api/v1/providers/connect");
    expect(connectPosts).toHaveLength(1);
    expect(connectPosts[0].init.method).toBe("POST");
    const connectHeaders = connectPosts[0].init.headers ?? {};
    expect(connectHeaders["x-ui-session-token"]).toBe(FX_TOKEN);
    expect(connectHeaders["x-ui-session-token"]).not.toBe("local-session");
    const connectBody = JSON.parse(connectPosts[0].init.body as string) as Record<string, unknown>;
    expect(connectBody["preset_id"]).toBe("openai");
    expect(connectBody["model"]).toBe("openai/gpt-4o-mini");
    expect(connectBody["key_ref"]).toEqual({ secret_id: "openai", provider_id: "openai" });
    expect(JSON.stringify(connectBody)).not.toContain("session_token");

    // The key leaves with step 1: no key field stays on screen.
    expect(screen.queryByLabelText("API key")).toBeNull();
  });

  it("connect 400 shows the reason and leaves the card disconnected", async () => {
    const seen = programFetch((url) => {
      if (url === "/api/v1/providers") {
        return ok({ providers: [] });
      }
      if (url === "/api/v1/providers/keys") {
        return { ok: true, status: 201, json: async () => ({ key_ref: { secret_id: "openai", provider_id: "openai" } }) };
      }
      if (url === "/api/v1/providers/connect") {
        return httpError(400, { code: "CREDENTIAL_ENTRY_MISSING" });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);
    setFxTokenAfterMount();
    fireEvent.click(screen.getByLabelText("Connect OpenAI"));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("API key"), { target: { value: FX_KEY } });
    fireEvent.click(within(dialog).getByText("Save"));
    expect(await within(dialog).findByText(/CREDENTIAL_ENTRY_MISSING/)).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
    const cards = screen.getAllByTestId("provider-card");
    const openaiCard = cards.find((c) => c.getAttribute("data-provider-id") === "openai");
    expect(openaiCard).toBeTruthy();
    expect(within(openaiCard as HTMLElement).getByLabelText("Connect OpenAI")).toBeTruthy();
    expect(within(openaiCard as HTMLElement).queryByLabelText("Disconnect OpenAI")).toBeNull();
    fireEvent.click(within(dialog).getByText("Cancel"));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByLabelText("Connect OpenAI")).toBeTruthy();
    expect(callsTo(seen, "/api/v1/providers/connect")).toHaveLength(1);
  });
});

describe("fxconnect cards state follows the GET answer and disconnect follows the POST", () => {
  it("open page with a listed provider shows it connected without any save", async () => {
    const seen = programFetch((url) => {
      if (url === "/api/v1/providers") {
        return ok({ providers: [{ provider_id: "openai", type: "cloud", base_url: "https://api.openai.com/v1", health: "ONLINE", evidenced: true }] });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);
    setFxTokenAfterMount();
    expect(await screen.findByLabelText("Disconnect OpenAI")).toBeTruthy();
    expect(seen.filter((call) => call.init.method === "POST")).toHaveLength(0);
  });

  it("Disconnect posts the disconnect route and the card follows the answer", async () => {
    // Stateful fake: the real route drops the provider, so later GETs no
    // longer list it (the page re-reads served state after disconnect).
    const dropped = new Set<string>();
    const seen = programFetch((url) => {
      if (url === "/api/v1/providers") {
        const providers = dropped.has("openai")
          ? []
          : [{ provider_id: "openai", type: "cloud", base_url: "https://api.openai.com/v1", health: "ONLINE", evidenced: true }];
        return ok({ providers });
      }
      if (url === "/api/v1/providers/openai/disconnect") {
        dropped.add("openai");
        return ok({ removed: true, provider_id: "openai" });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);
    setFxTokenAfterMount();
    fireEvent.click(await screen.findByLabelText("Disconnect OpenAI"));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByText("Disconnect"));
    await waitFor(() => expect(screen.getByLabelText("Connect OpenAI")).toBeTruthy());
    const discPosts = callsTo(seen, "/api/v1/providers/openai/disconnect");
    expect(discPosts).toHaveLength(1);
    expect(discPosts[0].init.method).toBe("POST");
    expect(discPosts[0].init.headers?.["x-ui-session-token"]).toBe(FX_TOKEN);
  });
});
