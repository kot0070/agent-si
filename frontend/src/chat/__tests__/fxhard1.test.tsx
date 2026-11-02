/** @vitest-environment jsdom */
// FXHARD1 chat hardening over the REAL chat screen (FAKE seam only at
// the fetch boundary): id-keyed merge, wait line, failed/stopped and
// interrupted turns, Allow-replays-once, load-earlier cursor.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea } from "../index";

const PROJECT_ID = "p-1";
const STREAM_URL = "/api/v1/chat/stream";
const HISTORY_URL = "/api/v1/chat/history";
const DECIDE_URL = "/api/v1/permissions/decide";

interface SeenPost {
  url: string;
  method: string;
  body: unknown;
}

interface Page {
  turns: unknown[];
  next_before: string | null;
}

let historyTurns: unknown[];
let historyFirstPage: Page | null;
let historyPosts: SeenPost[];
let streamPosts: SeenPost[];
let streamReplies: (() => Response)[];
let decidePosts: SeenPost[];

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

function successStream(text: string): Response {
  return sseBody([
    `data: {"type":"start","stream_id":"srv-1","run_id":"r-1"}`,
    `data: {"type":"delta","stream_id":"srv-1","run_id":"r-1","text":"${text}"}`,
    `data: {"type":"done","stream_id":"srv-1","run_id":"r-1","text":"${text}"}`,
    "",
  ]);
}

function errorStream(code: string): Response {
  return sseBody([
    `data: {"type":"start","stream_id":"srv-e","run_id":"r-e"}`,
    `data: {"type":"error","stream_id":"srv-e","run_id":"r-e","code":"${code}","message":"wire"}`,
    "",
  ]);
}

function installHoldStream(tool: string): Response {
  return sseBody([
    `data: {"type":"start","stream_id":"srv-fx","run_id":"r-fx"}`,
    `data: {"type":"approval","stream_id":"srv-fx","run_id":"r-fx","tool_id":"${tool}","reason":"run held: install permission needed"}`,
    "",
  ]);
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
      const parsed = new URL(url, "http://localhost");
      const before = parsed.searchParams.get("before");
      if (before === null && historyFirstPage !== null) {
        return jsonBody({
          turns: historyFirstPage.turns,
          next_before: historyFirstPage.next_before,
          total: 201,
        });
      }
      if (before !== null) {
        const index = historyTurns.findIndex(
          (turn) =>
            typeof turn === "object" &&
            turn !== null &&
            (turn as { id?: unknown }).id === before,
        );
        const older = index < 0 ? [] : historyTurns.slice(0, index);
        return jsonBody({ turns: older, next_before: null, total: 0 });
      }
      return jsonBody({ turns: historyTurns });
    }
    if (url.includes(STREAM_URL) && method === "POST") {
      streamPosts.push({ url, method, body });
      const reply = streamReplies.shift();
      if (reply === undefined) {
        throw new Error("no stubbed stream reply left");
      }
      return reply();
    }
    if (url === DECIDE_URL && method === "POST") {
      decidePosts.push({ url, method, body });
      return jsonBody({ ok: true });
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
    error_code: "",
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
  historyFirstPage = null;
  historyPosts = [];
  streamPosts = [];
  streamReplies = [];
  decidePosts = [];
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

function renderChat(client?: FakeApiClient | HttpApiClient): void {
  render(
    <ApiClientProvider client={client ?? new HttpApiClient()}>
      <ChatArea projectId={PROJECT_ID} />
    </ApiClientProvider>,
  );
}

describe("id-keyed history merge", () => {
  it("keeps identical user texts as separate turns", async () => {
    historyTurns = [
      turn("t-1", "hello", "first answer"),
      turn("t-2", "hello", "second answer"),
    ];
    renderChat();
    const users = await screen.findAllByTestId("chat-user-message");
    expect(users).toHaveLength(2);
    // Each served answer renders once: history never shows a card.
    expect(await screen.findAllByText("first answer")).toHaveLength(1);
    expect(await screen.findAllByText("second answer")).toHaveLength(1);
  });
});

describe("second send while a stream runs", () => {
  it("keeps the draft, disables send, shows the wait line", async () => {
    streamReplies.push(
      () =>
        new Response(
          new ReadableStream<Uint8Array>({
            start() {
              // Never emits: the stream stays live for the whole test.
            },
          }),
          {
            status: 200,
            headers: { "content-type": "text/event-stream" },
          },
        ),
    );
    renderChat();
    promptAndSend("first");
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "second" },
    });
    // Draft stays in the box, send is disabled, one quiet line.
    expect(
      (screen.getByTestId("chat-prompt") as HTMLInputElement).value,
    ).toBe("second");
    expect(screen.getByTestId("chat-send")).toHaveProperty(
      "disabled",
      true,
    );
    const wait = await screen.findByTestId("chat-wait-line");
    expect(wait.textContent).toBe("Wait for this to finish or press Stop");
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(
      (screen.getByTestId("chat-prompt") as HTMLInputElement).value,
    ).toBe("second");
    expect(streamPosts).toHaveLength(1);
  });
});

describe("failed and stopped turns", () => {
  it("stores a failed turn and restores the error card on reopen", async () => {
    streamReplies.push(() => errorStream("BUDGET_CAPPED"));
    renderChat();
    promptAndSend("do it");
    expect(await screen.findByTestId("kit-error-panel")).toBeTruthy();
    await waitFor(() => {
      expect(
        historyPosts.filter(
          (post) =>
            (post.body as { status?: unknown }).status === "failed",
        ),
      ).toHaveLength(1);
    });
    const failed = historyPosts.find(
      (post) => (post.body as { status?: unknown }).status === "failed",
    );
    expect((failed?.body as { run_id?: unknown }).run_id).not.toBe("");
    expect((failed?.body as { error_code?: unknown }).error_code).toBe(
      "BUDGET_CAPPED",
    );
    // Reopen from the stored failed turn: the card returns, Ready.
    historyTurns = [
      turn("t-f", "do it", "half", "failed", {
        error_code: "BUDGET_CAPPED",
      }),
    ];
    cleanup();
    resetChatStore();
    renderChat();
    expect(await screen.findByTestId("kit-error-panel")).toBeTruthy();
    expect(
      await screen.findByTestId("chat-health-degraded"),
    ).toBeTruthy();
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
    expect(
      (await screen.findByTestId("chat-statusline")).textContent,
    ).toContain(t("chat.composer.statusReady"));
  });

  it("stores a stopped turn when the user presses Stop", async () => {
    const client = new FakeApiClient({ chatDeltas: ["Hel", "lo"] });
    renderChat(client);
    promptAndSend("stop me");
    // Same tick: the abort lands before the fake chunks are consumed.
    fireEvent.click(screen.getByTestId("chat-abort"));
    await waitFor(() => {
      expect(
        historyPosts.filter(
          (post) =>
            (post.body as { status?: unknown }).status === "stopped",
        ),
      ).toHaveLength(1);
    });
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
  });
});

describe("interrupted restart", () => {
  it("shows the stored text plus interrupted, never Working, with resend", async () => {
    historyTurns = [turn("t-r", "finish this", "partial work", "running")];
    renderChat();
    // The note renders with the stored text in one bubble.
    const bubbles = await screen.findAllByTestId("chat-assistant-message");
    expect(
      bubbles.some(
        (node) =>
          node.textContent?.includes("partial work") === true &&
          node.textContent?.includes("Interrupted when the app closed") ===
            true,
      ),
    ).toBe(true);
    expect(await screen.findByText("finish this")).toBeTruthy();
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
    expect(
      (await screen.findByTestId("chat-statusline")).textContent,
    ).toContain(t("chat.composer.statusReady"));
    streamReplies.push(() => successStream("resumed"));
    fireEvent.click(await screen.findByTestId("chat-resend"));
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    await waitFor(() => {
      expect(streamPosts).toHaveLength(1);
    });
  });
});

describe("install Allow replays once", () => {
  const TOOL = "install:p-1:npm";

  it("reuses the held turn and posts one stream, Deny never resends", async () => {
    streamReplies.push(
      () => installHoldStream(TOOL),
      () => successStream("installed"),
    );
    renderChat();
    promptAndSend("install me");
    fireEvent.click(await screen.findByTestId("permission-allow"));
    await waitFor(() => {
      expect(streamPosts).toHaveLength(2);
    });
    const users = screen.getAllByTestId("chat-user-message");
    expect(
      users.filter((node) => node.textContent?.includes("install me")),
    ).toHaveLength(1);
    expect(decidePosts).toHaveLength(1);
    expect((decidePosts[0]?.body as { decision?: unknown }).decision).toBe(
      "allow",
    );
    // The held running turn upserts into one stored turn, status ok.
    await waitFor(() => {
      expect(
        historyPosts.filter(
          (post) => (post.body as { status?: unknown }).status === "ok",
        ),
      ).toHaveLength(1);
    });
    expect(
      historyPosts.filter(
        (post) => (post.body as { status?: unknown }).status === "failed",
      ),
    ).toHaveLength(0);
  });

  it("keeps the pending card across leaving the page", async () => {
    streamReplies.push(() => installHoldStream(TOOL));
    const client = new HttpApiClient();
    const first = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId={PROJECT_ID} />
      </ApiClientProvider>,
    );
    promptAndSend("install me");
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
    first.unmount();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId={PROJECT_ID} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
    // Restart (fresh client): the served running turn shows interrupted.
    historyTurns = [turn("t-h", "install me", "", "running")];
    cleanup();
    resetChatStore();
    renderChat();
    const notes = await screen.findAllByText(
      "Interrupted when the app closed",
    );
    expect(notes.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByTestId("chat-resend")).toBeTruthy();
  });
});

describe("load earlier cursor", () => {
  it("prepends older turns above the newest window", async () => {
    historyTurns = [
      turn("t-1", "older", "older answer"),
      turn("t-2", "newer", "newer answer"),
    ];
    historyFirstPage = {
      turns: [turn("t-2", "newer", "newer answer")],
      next_before: "t-2",
    };
    renderChat();
    expect(await screen.findByText("newer")).toBeTruthy();
    expect(screen.queryByText("older")).toBeNull();
    fireEvent.click(await screen.findByTestId("chat-load-earlier"));
    expect(await screen.findByText("older")).toBeTruthy();
    const users = screen.getAllByTestId("chat-user-message");
    expect(
      users.map((node) => node.textContent?.startsWith("older") ?? false),
    ).toEqual([true, false]);
    expect(
      users.map((node) => node.textContent?.startsWith("newer") ?? false),
    ).toEqual([false, true]);
    expect(screen.queryByTestId("chat-load-earlier")).toBeNull();
  });
});

describe("empty-answer stream", () => {
  it("records a dropped stream as a failed line, never stuck Working", async () => {
    streamReplies.push(() =>
      sseBody([
        `data: {"type":"start","stream_id":"srv-d","run_id":"r-d"}`,
        `data: {"type":"done","stream_id":"srv-d","run_id":"r-d"}`,
        "",
      ]),
    );
    renderChat();
    promptAndSend("answer me");
    expect(await screen.findByTestId("kit-error-panel")).toBeTruthy();
    await waitFor(() => {
      expect(
        historyPosts.filter(
          (post) => (post.body as { status?: unknown }).status === "failed",
        ),
      ).toHaveLength(1);
    });
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
  });
});
