/** @vitest-environment jsdom */
// FXANSWER RED first: plain answers read as the answer itself; Stop is not
// an error; one click stops a stalled stream; the reconcile banner only
// shows for reconcile-marked rows; /projects keeps its form on failure.
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
import { apiErrorLocaleKey } from "../../api/errors";
import { parseErrorBody } from "../../api/errors";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import {
  ChatArea,
  engineVerdictLine,
  summarizeEngineTurn,
} from "../index";
import { ProjectsPage } from "../../projects/ProjectsPage";

const PROJECT_ID = "p-1";
const STREAM_URL = "/api/v1/chat/stream";
const HISTORY_URL = "/api/v1/chat/history";

const MARKER = "run answered: plain answer, no parts";
const ANSWER_TEXT =
  `Team off: one worker, no audit\n` +
  `pear\n` +
  `Total: 10 input + 5 output = 15 tokens; cost not known (no price)\n` +
  `${MARKER}`;

let historyTurns: unknown[];
let historyPosts: unknown[];
let streamPosts: { url: string; method: string; body: unknown }[];
let cancelPosts: unknown[];
let streamReplies: (() => Response)[];
let lastStreamSignal: AbortSignal | null;

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
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
        (historyPosts as unknown[]).push(body);
        return jsonBody({ ok: true });
      }
      return jsonBody({ turns: historyTurns });
    }
    if (url.includes(STREAM_URL) && method === "POST") {
      streamPosts.push({ url, method, body });
      // Real fetch honors the abort signal: capture it so the stalled
      // test can error the stream on abort like the network would.
      const signal = init?.signal;
      lastStreamSignal =
        signal instanceof AbortSignal ? signal : null;
      const reply = streamReplies.shift();
      if (reply === undefined) {
        throw new Error("no stubbed stream reply left");
      }
      return reply();
    }
    if (url.includes("/api/v1/chat/cancel")) {
      cancelPosts.push(body);
      return jsonBody({ ok: true });
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: PROJECT_ID, models: [] });
    }
    if (url.includes("/api/v1/projects") && method === "GET") {
      return jsonBody({ surprise: true });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

function turn(
  id: string,
  userText: string,
  assistantText: string,
  status = "ok",
  extra: Record<string, unknown> = {},
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
    ...extra,
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
  streamPosts = [];
  cancelPosts = [];
  streamReplies = [];
  lastStreamSignal = null;
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

describe("fxanswer plain-answer verdict", () => {
  it("the visible reply is the answer text itself, en", () => {
    const summary = summarizeEngineTurn(ANSWER_TEXT, "ok");
    expect(summary.done).toBe(true);
    const line = engineVerdictLine(summary);
    expect(line).toContain("pear");
    expect(line).not.toContain("Nothing was built");
    expect(line).not.toContain("0 parts");
  });

  it("a 0-part run with no answer still never says Done", () => {
    const summary = summarizeEngineTurn("log line 1\nlog line 2", "ok");
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toContain("Nothing was built");
    expect(engineVerdictLine(summary)).not.toContain("Done");
  });
});

describe("fxanswer stopped is not an error", () => {
  it("a stored stopped turn says Stopped, no error line, no retry", async () => {
    historyTurns = [
      turn("t-stop", "map the fence", "Working folder Team", "stopped"),
    ];
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId={PROJECT_ID} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("chat-stopped-line")).toBeTruthy();
    expect(screen.queryByTestId("chat-error-line")).toBeNull();
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    expect(screen.queryByTestId("kit-error-retry")).toBeNull();
    expect(screen.queryByText("Something went wrong. Try again.")).toBeNull();
  });
});

describe("fxanswer reconcile banner", () => {
  it("a running row without the reconcile mark shows no app-closed banner", async () => {
    historyTurns = [
      turn("t-run", "finish this", "partial work", "running"),
    ];
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId={PROJECT_ID} />
      </ApiClientProvider>,
    );
    await screen.findByText("partial work");
    expect(
      screen.queryByText("Interrupted when the app closed"),
    ).toBeNull();
  });

  it("a reconcile-marked interrupted row keeps the banner with resend", async () => {
    historyTurns = [
      turn("t-int", "finish this", "partial work", "interrupted", {
        run_end_reason: "restart reconcile: dated earlier run",
      }),
    ];
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId={PROJECT_ID} />
      </ApiClientProvider>,
    );
    await screen.findByText(/Interrupted when the app closed/);
    expect(await screen.findByTestId("chat-resend")).toBeTruthy();
  });
});

describe("fxanswer one click stops a stalled stream", () => {
  it("abort posts cancel and shows Stopped with no further chunks", async () => {
    const encoder = new TextEncoder();
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const stalled = new ReadableStream<Uint8Array>({
      start(entry) {
        controller = entry;
      },
    });
    streamReplies.push(
      () =>
        new Response(stalled, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId={PROJECT_ID} />
      </ApiClientProvider>,
    );
    promptAndSend("stop this stall");
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    controller.enqueue(
      encoder.encode(
        `data: {"type":"start","stream_id":"srv-9","run_id":"r-9"}\n\n`,
      ),
    );
    await screen.findByText("stop this stall");
    // No delta ever arrives: the server is stalled mid-model-call.
    // Wire abort to the parked reader, exactly like real fetch: the
    // abort errors the pending read so the run closes at once.
    const failStalled = (): void => {
      try {
        controller.error(
          new DOMException("The operation was aborted.", "AbortError"),
        );
      } catch {
        // The reader already left: nothing to fail.
      }
    };
    if (lastStreamSignal !== null) {
      if (lastStreamSignal.aborted) {
        failStalled();
      } else {
        lastStreamSignal.addEventListener("abort", failStalled, {
          once: true,
        });
      }
    }
    // One click is enough: the run closes as stopped with no more chunks.
    fireEvent.click(screen.getByTestId("chat-abort"));
    await waitFor(() => {
      expect(cancelPosts).toHaveLength(1);
    });
    expect(cancelPosts).toEqual([{ stream_id: "srv-9" }]);
    await screen.findByTestId("chat-stopped-line");
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
    try {
      controller.close();
    } catch {
      // The abort already errored the parked reader.
    }
  });
});

describe("fxanswer generic fallback", () => {
  it("a codeless 500 body maps to errors.generic, never the contract code", () => {
    const error = parseErrorBody({ surprise: true }, 500);
    expect(apiErrorLocaleKey(error.code)).toBe("errors.generic");
    expect(error.code).not.toBe("CONTEXT_WRONG_CONTRACT_VERSION");
    expect(t("errors.generic")).toBe("Something went wrong. Try again.");
  });

  it("/projects keeps its form with a Retry on a failed first load", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ProjectsPage />
      </ApiClientProvider>,
    );
    await screen.findByTestId("project-add-form");
    expect(await screen.findByTestId("kit-error-retry")).toBeTruthy();
    expect(
      screen.queryByText(/wrong contract version/),
    ).toBeNull();
    expect(
      screen.queryByText("CONTEXT_WRONG_CONTRACT_VERSION"),
    ).toBeNull();
  });
});
