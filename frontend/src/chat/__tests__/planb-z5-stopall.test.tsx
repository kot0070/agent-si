/** @vitest-environment jsdom */
// PLANB Z5 (DEFECT-40): after Stop all the chat said "Nothing was built - the
// plan had no parts" plus "Something went wrong. Try again.". The server ends
// the run with the line "run stopped: user stop" and a cancelled event; the
// chat must say the run was stopped by the user. The real ChatArea runs; only
// fetch (the network boundary) is faked with the real SSE wire.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea } from "../index";

const PROJECT_ID = "p-1";
let historyPosts: Array<Record<string, unknown>>;

function sse(events: Array<Record<string, unknown>>): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("");
  return new Response(body, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function stubBoundary(reply: () => Response): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.startsWith("/api/v1/chat/history")) {
      if (method === "POST") {
        historyPosts.push(JSON.parse(String(init?.body)));
        return new Response('{"ok":true}', { status: 200 });
      }
      return new Response('{"turns":[]}', { status: 200 });
    }
    if (url.includes("/api/v1/chat/stream") && method === "POST") {
      return reply();
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return new Response(JSON.stringify({ project_id: PROJECT_ID, models: [] }), { status: 200 });
    }
    return new Response("{}", { status: 404 });
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
  historyPosts = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
});

describe("PLANB Z5 stop all in the chat", () => {
  it("a run ended by Stop all says it was stopped by the user, no error", async () => {
    stubBoundary(() =>
      sse([
        { type: "start", stream_id: "srv-1", run_id: "r-1" },
        { type: "delta", text: "Director: planning the work" },
        { type: "delta", text: "run stopped: user stop", run_id: "r-1" },
        { type: "cancelled", text: "run stopped: user stop", run_id: "r-1" },
      ]),
    );
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId={PROJECT_ID} />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "Build a small Node project named node-add" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).toContain("Stopped by you");
    expect(document.body.textContent).not.toContain("Nothing was built");
    expect(document.body.textContent).not.toContain("Something went wrong");
    await waitFor(() => {
      expect(historyPosts.some((post) => post["status"] === "stopped")).toBe(true);
    });
    expect(historyPosts.some((post) => post["status"] === "failed")).toBe(false);
  });
});
