/** @vitest-environment jsdom */
// PLANB X5 (DEFECT-34): the stream open carries the client run id, the
// client's own history write uses the same id and never stores live
// waiting lines; real ChatArea, fake only at the fetch boundary.
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
import { ChatArea } from "../index";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Seen = { url: string; method: string; headers: Record<string, string>; body: string };

function stubHangingStream(seen: Seen[]): {
  enqueue: (text: string) => void;
} {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const live = new ReadableStream<Uint8Array>({
    start(entry) {
      controller = entry;
    },
  });
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    seen.push({
      url,
      method: (init?.method ?? "GET").toUpperCase(),
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: typeof init?.body === "string" ? init.body : "",
    });
    if (url.startsWith("/api/v1/chat/history")) {
      return jsonBody({ turns: [] });
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: "p-x5", models: [] });
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
    if (url === "/api/v1/chat/history") {
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

describe("X5 one history row per run", () => {
  it("sends x-run-id on open and records the same id without waiting lines", async () => {
    const seen: Seen[] = [];
    const stream = stubHangingStream(seen);
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-x5" />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "one row" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    await screen.findByTestId("chat-spinner");
    stream.enqueue('data: {"type":"start","stream_id":"srv-x5","run_id":"r-x5"}\n\n');
    stream.enqueue(
      `data: ${JSON.stringify({ type: "delta", stream_id: "srv-x5", run_id: "r-x5", text: "Waiting for the model: director on m1, 10 s\n", live: "director" })}\n\n`,
    );
    stream.enqueue(
      `data: ${JSON.stringify({ type: "delta", stream_id: "srv-x5", run_id: "r-x5", text: "run success: all 1 parts PASS\n" })}\n\n`,
    );
    stream.enqueue('data: {"type":"done","stream_id":"srv-x5","run_id":"r-x5","executed":true}\n\n');
    const records = (): Seen[] =>
      seen.filter((c) => c.url === "/api/v1/chat/history" && c.method === "POST");
    await waitFor(() => {
      expect(records().some((c) => JSON.parse(c.body).status === "ok")).toBe(true);
    });
    const open = seen.find((c) => c.url.includes("/api/v1/chat/stream"));
    expect(open).toBeTruthy();
    const runId = open?.headers["x-run-id"] ?? "";
    expect(runId).not.toBe("");
    expect(JSON.parse(open?.body ?? "{}")).toEqual({ project: "p-x5", message: "one row" });
    for (const record of records()) {
      expect(JSON.parse(record.body).run_id).toBe(runId);
    }
    const terminal = records().map((c) => JSON.parse(c.body)).find((b) => b.status === "ok");
    expect(terminal.assistant_text).toContain("run success");
    expect(terminal.assistant_text).not.toContain("Waiting for the model");
  });
});