/** @vitest-environment jsdom */
// FXR1B: stopped/failed/engine turns never show the approval card;
// a stopped turn shows one plain stopped line; a real proposal keeps
// the card. B3 verifies the stop path (Ready + partial text restart).
// FAKE seam only at the fetch boundary.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea } from "../index";

const PROJECT_ID = "p-1";
const STREAM_URL = "/api/v1/chat/stream";
const HISTORY_URL = "/api/v1/chat/history";

interface SeenPost {
  url: string;
  method: string;
  body: unknown;
}

let historyTurns: unknown[];
let historyPosts: SeenPost[];
let streamReplies: (() => Response)[];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function sseBody(lines: string[]): Response {
  return new Response(lines.join("\n"), {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function stubBoundary(): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const body =
      typeof init?.body === "string" ? JSON.parse(init.body) : null;
    if (url.startsWith(HISTORY_URL)) {
      if (method === "POST") {
        historyPosts.push({ url, method, body });
        return jsonBody({ ok: true });
      }
      return jsonBody({ turns: historyTurns });
    }
    if (url.includes(STREAM_URL) && method === "POST") {
      const reply = streamReplies.shift();
      if (reply === undefined) {
        throw new Error("no stubbed stream reply left");
      }
      return reply();
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: PROJECT_ID, models: [] });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [] });
    }
    if (url.includes("/api/v1/chat/cancel")) {
      return jsonBody({ ok: true });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

function turn(
  id: string,
  userText: string,
  assistantText: string,
  status: string,
): unknown {
  return {
    project_id: PROJECT_ID,
    user_text: userText,
    assistant_text: assistantText,
    time: "2026-01-01T00:00:00Z",
    id,
    status,
    run_id: `run-${id}`,
    error_code: status === "stopped" ? "STOPPED" : "",
  };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
  historyTurns = [];
  historyPosts = [];
  streamReplies = [];
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function promptAndSend(text: string): void {
  fireEvent.change(screen.getByTestId("chat-prompt"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByTestId("chat-send"));
}

function renderChat(): void {
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <ChatArea projectId={PROJECT_ID} />
    </ApiClientProvider>,
  );
}

describe("B1 stopped turn never shows the approval card", () => {
  it("renders the partial text with one plain stopped line, no card", async () => {
    historyTurns = [
      turn("t-stop", "map the north fence", "Working folder Team", "stopped"),
    ];
    renderChat();
    expect(await screen.findByText("Working folder Team")).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(screen.queryByTestId("approval-accept")).toBeNull();
    const line = await screen.findByTestId("chat-stopped-line");
    expect(line.textContent).toBe("Stopped");
  });

  it("renders a stored failed turn with no approval card", async () => {
    historyTurns = [
      turn("t-fail", "do it", "half an answer", "failed"),
    ];
    renderChat();
    expect(await screen.findByText("half an answer")).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
    const line = await screen.findByTestId("chat-error-line");
    expect(line.textContent).toContain("do it");
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
  });
});

describe("B3 stop path keeps Ready and the partial text", () => {
  it("abort returns Ready, stores stopped with partial text, reload keeps it", async () => {
    const encoder = new TextEncoder();
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const live = new ReadableStream<Uint8Array>({
      start(entry) {
        controller = entry;
      },
    });
    streamReplies.push(
      () =>
        new Response(live, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );
    const first = render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId={PROJECT_ID} />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    await screen.findByText("hello");
    controller.enqueue(
      encoder.encode(
        `data: {"type":"start","stream_id":"srv-9","run_id":"r-9"}\n\n`,
      ),
    );
    controller.enqueue(
      encoder.encode(
        `data: {"type":"delta","stream_id":"srv-9","run_id":"r-9","text":"Hel"}\n\n`,
      ),
    );
    expect(await screen.findByText("Hel")).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
    fireEvent.click(screen.getByTestId("chat-abort"));
    // The server ends the stream on cancel: done arrives, the run
    // closes as stopped.
    controller.enqueue(
      encoder.encode(
        `data: {"type":"done","stream_id":"srv-9","run_id":"r-9"}\n\n`,
      ),
    );
    controller.close();
    await waitFor(() => {
      expect(
        historyPosts.filter(
          (post) => (post.body as { status?: unknown }).status === "stopped",
        ),
      ).toHaveLength(1);
    });
    const stopped = historyPosts.find(
      (post) => (post.body as { status?: unknown }).status === "stopped",
    );
    expect((stopped?.body as { assistant_text?: unknown }).assistant_text).toBe(
      "Hel",
    );
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
    first.unmount();
    // Restart: the stored stopped turn keeps the partial text, no card.
    historyTurns = [
      turn("t-9", "hello", "Hel", "stopped"),
    ];
    cleanup();
    resetChatStore();
    renderChat();
    expect(await screen.findByText("Hel")).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(await screen.findByTestId("chat-stopped-line")).toBeTruthy();
  });
});
