/** @vitest-environment jsdom */
// FXASK A8 RED: the run waits in place. An `ask` event mid-stream shows
// the card without closing the stream; Allow with the stream open only
// records the decision (no resend); the run then finishes on the same
// stream.
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
import { ChatArea } from "../index";

const PROJECT_ID = "p-wait";
const TOOL = "install:p-wait:npm";
const STREAM_URL = "/api/v1/chat/stream";
const DECIDE_URL = "/api/v1/permissions/decide";
const ASK_argv = ["npm", "install"];

interface SeenPost {
  url: string;
  body: unknown;
}

const posts: SeenPost[] = [];
let streamPosts = 0;
let releaseDone: (() => void) | null = null;

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function askStream(): Response {
  const encoder = new TextEncoder();
  const head = [
    `data: {"type":"start","stream_id":"srv-w","run_id":"r-w"}`,
    `data: {"type":"delta","stream_id":"srv-w","run_id":"r-w","text":"Waiting for your permission to run npm install."}`,
    `data: {"type":"ask","stream_id":"srv-w","run_id":"r-w","tool_id":"${TOOL}","argv":["npm","install"],"text":"Waiting for your permission to run npm install."}`,
    "",
  ].join("\n");
  const tail = [
    `data: {"type":"done","stream_id":"srv-w","run_id":"r-w","executed":true}`,
    "",
  ].join("\n");
  // Production shape: the stream stays open (the run waits in place)
  // until the decision lands; only then does done arrive.
  const gate = new Promise<void>((resolve) => {
    releaseDone = resolve;
  });
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(encoder.encode(head + "\n"));
      await gate;
      controller.enqueue(encoder.encode(tail + "\n"));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function stubBoundary(): void {
  posts.length = 0;
  streamPosts = 0;
  releaseDone = null;
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes(STREAM_URL) && method === "POST") {
      streamPosts += 1;
      return askStream();
    }
    if (url === DECIDE_URL && method === "POST") {
      let body: unknown = null;
      try {
        body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
      } catch {
        body = null;
      }
      posts.push({ url, body });
      releaseDone?.();
      return jsonBody({ tool_id: TOOL, decision: "allow" });
    }
    if (url.includes("/api/v1/permissions/install-request")) {
      return jsonBody({ tool_id: TOOL, argv: ASK_argv });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.sessionStorage.clear();
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.sessionStorage.clear();
});

function renderChat(): void {
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <ChatArea projectId={PROJECT_ID} />
    </ApiClientProvider>,
  );
}

describe("fxask A8 run waits in place", () => {
  it("ask event shows the card and the same stream finishes", async () => {
    renderChat();
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "install it" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    const dialog = await screen.findByTestId("permission-dialog");
    expect(dialog).toBeTruthy();
    expect(screen.getByTestId("permission-tool").textContent).toContain(
      "npm",
    );
    expect(streamPosts).toBe(1);
  });

  it("Allow with the stream open records only, never resends", async () => {
    renderChat();
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "install it" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    await screen.findByTestId("permission-dialog");
    fireEvent.click(screen.getByTestId("permission-allow"));
    await waitFor(() => {
      expect(
        posts.some((post) => post.url === DECIDE_URL),
      ).toBe(true);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("permission-dialog")).toBeNull();
    });
    expect(streamPosts).toBe(1);
  });
});
