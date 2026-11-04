/** @vitest-environment jsdom */
// PLANB X1 (DEFECT-27): one live waiting line per model call, updated in
// place; real ChatArea, fake only at the fetch boundary.
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
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { applyLiveDelta } from "../chatApi";
import { ChatArea } from "../index";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubHangingStream(): {
  enqueue: (text: string) => void;
} {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const live = new ReadableStream<Uint8Array>({
    start(entry) {
      controller = entry;
    },
  });
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url.startsWith("/api/v1/chat/history")) {
      return jsonBody({ turns: [] });
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: "p-x1", models: [] });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [] });
    }
    if (url.includes("/api/v1/chat/stream")) {
      return new Response(live, {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      });
    }
    if (url.includes("/api/v1/chat/cancel")) {
      return jsonBody({ ok: true });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  return {
    enqueue: (text: string) => {
      controller.enqueue(encoder.encode(text));
    },
  };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function sse(text: string, live?: string): string {
  const event: Record<string, unknown> = {
    type: "delta",
    stream_id: "srv-x1",
    run_id: "r-x1",
    text,
  };
  if (live !== undefined) {
    event["live"] = live;
  }
  return `data: ${JSON.stringify(event)}\n\n`;
}

describe("X1 live waiting line", () => {
  it("one line per model call: refreshed in place, a later call starts a new line", async () => {
    const stream = stubHangingStream();
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-x1" />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "wait me" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    await screen.findByTestId("chat-spinner");
    stream.enqueue('data: {"type":"start","stream_id":"srv-x1","run_id":"r-x1"}\n\n');
    stream.enqueue(sse("Director: plan\n"));
    stream.enqueue(sse("Waiting for the model: director on m1, 10 s\n", "director"));
    stream.enqueue(sse("Waiting for the model: director on m1, 25 s\n", "director"));
    stream.enqueue(sse("Waiting for the model: director on m1, 40 s\n", "director"));
    const log = async (): Promise<string> =>
      (await screen.findAllByText(/Director: plan/))[0]?.textContent ?? "";
    await waitFor(async () => {
      expect(await log()).toContain("director on m1, 40 s");
    });
    let text = await log();
    expect(text.match(/Waiting for the model/g)).toHaveLength(1);
    expect(text).not.toContain("10 s");
    expect(text).not.toContain("25 s");
    stream.enqueue(sse("Part p1: attempt 1\n"));
    stream.enqueue(sse("Waiting for the model: director on m1, 10 s\n", "director"));
    await waitFor(async () => {
      expect((await log()).match(/Waiting for the model/g)).toHaveLength(2);
    });
    text = await log();
    expect(text).toContain("director on m1, 40 s");
    expect(text.indexOf("40 s")).toBeLessThan(text.indexOf("Part p1"));
    expect(text.indexOf("Part p1")).toBeLessThan(text.lastIndexOf("10 s"));
  });
});

describe("applyLiveDelta", () => {
  it("plain text appends and clears the live memory", () => {
    const lines = new Map<string, string>([["a", "x\n"]]);
    expect(applyLiveDelta("t", "u", undefined, lines)).toBe("tu");
    expect(lines.size).toBe(0);
  });
});