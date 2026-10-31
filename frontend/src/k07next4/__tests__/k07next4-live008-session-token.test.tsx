/** @vitest-environment jsdom */
// K07NEXT4 LIVE0-08: the REAL SessionTokenCard over a fresh HttpApiClient
// (only global fetch replaced, quoting the served session write schema
// from src/agent_si/http/k07next4.py session_write).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { SessionTokenCard } from "../SessionTokenCard";

const TOKEN = "tok-k07next4-live008";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

const SERVED_TOKEN_OK = {
  row: "LIVE0-08",
  token_ok: true,
  actor: "ui",
};

const seen: Array<{
  url: string;
  method: string;
  headers: Record<string, string>;
}> = [];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  seen.length = 0;
  (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY] = TOKEN;
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    seen.push({
      url: String(input),
      method: (init?.method ?? "GET").toUpperCase(),
      headers: { ...((init?.headers ?? {}) as Record<string, string>) },
    });
    if (String(input) === "/api/v1/k07next4/session-write") {
      return jsonBody(SERVED_TOKEN_OK);
    }
    throw new Error(`unexpected fetch ${String(input)}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (window as unknown as Record<string, unknown>)[WINDOW_TOKEN_KEY];
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("k07next4 LIVE0-08 session token over the real screen", () => {
  it("carries the token header on the write from the first call", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <SessionTokenCard />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next4-session-token");
    const posts = seen.filter(
      (request) =>
        request.url === "/api/v1/k07next4/session-write" &&
        request.method === "POST",
    );
    expect(posts).toHaveLength(1);
    expect(posts[0]?.headers["x-ui-session-token"]).toBe(TOKEN);
    expect(posts[0]?.headers["x-actor"]).toBe("ui");
    expect(screen.getByText(en.chat.composer.send)).toBeTruthy();
    expect(screen.getByText("ui")).toBeTruthy();
  });
});
