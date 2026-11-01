/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProvidersPage } from "./ProvidersPage";
import { APP_NAMESPACE_PREFIX } from "./types";

const FX_TOKEN = "fxleftover-ui-token";
const ENTRY = "agent_si/provider/old";
const STAMP = "2026-01-01T00:00:00.000Z";

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

function callsTo(seen: SeenCall[], url: string): SeenCall[] {
  return seen.filter((call) => call.url === url);
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

describe("fxleftover real page over the leftover routes", () => {
  it("route leftover entry shows; Delete+Confirm calls the route and the row goes", async () => {
    const seen = programFetch((url) => {
      if (url === "/api/v1/providers") {
        return ok({ providers: [] });
      }
      if (url.startsWith("/api/v1/budget/providers/leftover-keys")) {
        return ok({ entries: [{ name: ENTRY, last_used_at: STAMP }] });
      }
      if (url === "/api/v1/budget/providers/leftover-delete") {
        return ok({ removed: true, entry: ENTRY });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);

    expect(await screen.findByText(ENTRY)).toBeTruthy();

    const listCalls = seen.filter((call) =>
      call.url.startsWith("/api/v1/budget/providers/leftover-keys"),
    );
    expect(listCalls).toHaveLength(1);
    expect(listCalls[0].url).toContain(`app_prefix=${encodeURIComponent(APP_NAMESPACE_PREFIX)}`);

    fireEvent.click(screen.getByLabelText(`Delete ${ENTRY}`));
    expect(await screen.findByText("Confirm delete")).toBeTruthy();
    fireEvent.click(screen.getByText("Confirm delete"));

    await waitFor(() => expect(screen.queryByText(ENTRY)).toBeNull());

    const deletes = callsTo(seen, "/api/v1/budget/providers/leftover-delete");
    expect(deletes).toHaveLength(1);
    expect(deletes[0].init.method).toBe("POST");
    expect(deletes[0].init.headers?.["x-ui-session-token"]).toBe(FX_TOKEN);
    expect(JSON.parse(deletes[0].init.body as string)).toEqual({
      app_prefix: APP_NAMESPACE_PREFIX,
      name: ENTRY,
      confirmed: true,
      session_token: FX_TOKEN,
    });
  });

  it("empty route list shows No leftover keys.", async () => {
    programFetch((url) => {
      if (url === "/api/v1/providers") {
        return ok({ providers: [] });
      }
      if (url.startsWith("/api/v1/budget/providers/leftover-keys")) {
        return ok({ entries: [] });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);

    expect(await screen.findByText("No leftover keys.")).toBeTruthy();
    expect(screen.queryByTestId("leftover-entry")).toBeNull();
  });
});
