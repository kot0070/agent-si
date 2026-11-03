/**
 * @vitest-environment jsdom
 */
// FXSMALL item 1 RED-first: disconnecting a LOCAL preset must POST the local
// disconnect route, never the providers registry route. The backend has no
// /api/v1/providers/ollama/disconnect (404 CONTEXT_MISSING, TRIAL3 log
// 20:20:32); POST /api/v1/local/disconnect detaches the runtime and the card
// flips back to Connect.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProvidersPage } from "./ProvidersPage";

const FX_TOKEN = "fx-ui-token-01";

type SeenCall = {
  url: string;
  init: { method?: string; headers?: Record<string, string>; body?: string };
};

function programFetch(handler: (url: string) => unknown) {
  const seen: SeenCall[] = [];
  const mock = vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    seen.push({
      url,
      init: {
        method: (init?.method ?? "GET").toUpperCase(),
        headers: { ...((init?.headers ?? {}) as Record<string, string>) },
        body: typeof init?.body === "string" ? init.body : "",
      },
    });
    return handler(url);
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
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
});

describe("fxsmall1 local preset disconnect", () => {
  it("Disconnect on the Ollama card posts /api/v1/local/disconnect and the card flips to Connect", async () => {
    // Stateful fake: the local route detaches the runtime, so later model
    // reads no longer list it (the page re-reads served state after
    // disconnect and the union refresh keeps the card disconnected).
    let detached = false;
    const seen = programFetch((url) => {
      if (url === "/api/v1/providers") {
        return ok({ providers: [] });
      }
      // Served local runtime attached at the Ollama base URL: the card
      // mounts connected without any key save.
      if (url === "/api/v1/local/models") {
        return detached ? ok({ models: [] }) : ok({ models: [{ model: "http://localhost:11434" }] });
      }
      // Real backend behavior: no registry row for a local preset.
      if (url === "/api/v1/providers/ollama/disconnect") {
        return httpError(404, { code: "CONTEXT_MISSING" });
      }
      if (url === "/api/v1/local/disconnect") {
        detached = true;
        return ok({ status: "NOT_CONFIGURED", reason: "runtime detached" });
      }
      return ok({});
    });
    render(<ProvidersPage project_id="local" />);
    // RED on the old code: the dialog posts the providers URL, the 404
    // keeps the dialog open and the card stays Disconnect.
    fireEvent.click(await screen.findByLabelText("Disconnect Ollama"));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByText("Disconnect"));
    await waitFor(() => expect(screen.getByLabelText("Connect Ollama")).toBeTruthy());
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(callsTo(seen, "/api/v1/local/disconnect")).toHaveLength(1);
    expect(callsTo(seen, "/api/v1/providers/ollama/disconnect")).toHaveLength(0);
  });
});
