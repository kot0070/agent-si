/** @vitest-environment jsdom */
// K07NEXT4 LIVE0B-05: the REAL ChatTaskBox over a fresh HttpApiClient
// (only global fetch replaced, quoting the served chat task schema
// from src/agent_si/http/k07next4.py chat_task).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { ChatTaskBox } from "../ChatTaskBox";

const TOKEN = "tok-k07next4-live0b05";
const WINDOW_TOKEN_KEY = "__AGENT_SI_UI_TOKEN";

const SERVED_CHAT_TASK = {
  row: "LIVE0B-05",
  task_id: "t-k07next4-1",
  prompt_ref: "k07next4-hello",
  status: "started",
};

const seen: string[] = [];

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
    seen.push(`${init?.method ?? "GET"} ${String(input)}`);
    if (String(input) === "/api/v1/app/chat-task") {
      return jsonBody(SERVED_CHAT_TASK);
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

describe("k07next4 LIVE0B-05 chat box over the real screen", () => {
  it("starts a task from the message box", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatTaskBox />
      </ApiClientProvider>,
    );
    await screen.findByTestId("k07next4-chat-task");
    expect(screen.getByPlaceholderText(en.chat.composer.prompt)).toBeTruthy();
    fireEvent.change(
      screen.getByPlaceholderText(en.chat.composer.prompt),
      { target: { value: "k07next4-hello" } },
    );
    fireEvent.click(screen.getByText(en.chat.composer.send));
    await screen.findByText("started");
    expect(seen).toContain("POST /api/v1/app/chat-task");
  });
});
