/** @vitest-environment jsdom */
// FXR3B on the REAL page (FAKE seam only at fetch): J1 engine verdict +
// steps disclosure; J3 empty state with samples; J5 single error line;
// J6 textarea composer; J9 named buttons. RED first.
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

const PROJECT_ID = "p-3";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const ENGINE_LOG = [
  "count_words_in_file reading utf-8 file",
  "Part p1: PASS (checks green, auditor PASS)",
  "Part p2: attempt 1",
  "Check p2 $ C:\\tool\\python.EXE -m pytest test_wordcount.py -v -> exit 4",
  "Auditor for p2: FAIL (no file changes were made)",
  "Part p2: checks red, attempt 2",
  "Check p2 $ C:\\tool\\python.EXE -m pytest test_wordcount.py -v -> exit 0",
  "Auditor for p2: PASS (test_wordcount.py created, [files: test_wordcount.py] 18 tests)",
  "Part p2: PASS (checks green, auditor PASS)",
  "run success: all 2 parts PASS",
].join("\n");

let historyTurns: unknown[];
let historyPosts: SeenPost[];
let streamReplies: (() => Response)[];

interface SeenPost {
  url: string;
  method: string;
  body: unknown;
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
    if (url.startsWith("/api/v1/chat/history")) {
      if (method === "POST") {
        historyPosts.push({ url, method, body });
        return jsonBody({ ok: true });
      }
      return jsonBody({ turns: historyTurns });
    }
    if (url.includes("/api/v1/chat/stream") && method === "POST") {
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
  executed: boolean,
  runEndReason = "",
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
    executed,
    run_end_reason: runEndReason,
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

function renderChat(): void {
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <ChatArea projectId={PROJECT_ID} />
    </ApiClientProvider>,
  );
}

describe("J1 finished engine turn", () => {
  it("shows the verdict first and the steps in a disclosure", async () => {
    historyTurns = [
      turn("t-eng", "count words", ENGINE_LOG, "ok", true),
    ];
    renderChat();
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).toContain("Done");
    expect(verdict.textContent).toContain("2 parts");
    expect(verdict.textContent).toContain("test_wordcount.py");
    // Steps stay in the DOM, toggle closed on success.
    const toggle = await screen.findByTestId("run-steps-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByText(/Auditor for p2: PASS/)).toBeTruthy();
    expect(screen.getByTestId("run-steps").hasAttribute("hidden")).toBe(true);
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });

  it("failed engine turn shows Failed, the next step, and an open disclosure", async () => {
    historyTurns = [
      turn(
        "t-engfail",
        "fix it",
        "Part p1: FAIL (red)\nrun failed: part p1 red",
        "failed",
        true,
      ),
    ];
    renderChat();
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).toContain("Failed");
    expect(verdict.textContent).toContain("Next");
    const toggle = await screen.findByTestId("run-steps-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("run-steps").hasAttribute("hidden")).toBe(
      false,
    );
  });

  it("live engine completion marks the waiting proposal, no card", async () => {
    historyTurns = [];
    streamReplies.push(() =>
      sseBody([
        `data: {"type":"start","stream_id":"srv-e","run_id":"r-e"}`,
        `data: {"type":"delta","stream_id":"srv-e","run_id":"r-e","text":"Part p1: PASS"}`,
        `data: {"type":"done","stream_id":"srv-e","run_id":"r-e","text":"Part p1: PASS","executed":true}`,
        "",
      ]),
    );
    renderChat();
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "run it" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(await screen.findByTestId("run-verdict")).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(screen.queryByTestId("approval-accept")).toBeNull();
  });
});

describe("disconnect-ended run names itself, never UNKNOWN", () => {
  it("shows the window-closed sentence with stored text plus resend", async () => {
    historyTurns = [
      turn(
        "t-disc",
        "deploy it",
        "half deployed",
        "running",
        false,
        "run ended (client disconnect: children reaped)",
      ),
    ];
    renderChat();
    const bubbles = await screen.findAllByTestId("chat-assistant-message");
    expect(
      bubbles.some(
        (node) =>
          node.textContent?.includes(
            "The run stopped when the window closed",
          ) === true &&
          node.textContent?.includes("Files so far are kept") === true,
      ),
    ).toBe(true);
    expect(await screen.findByText("deploy it")).toBeTruthy();
    expect(await screen.findByTestId("chat-resend")).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(document.body.textContent).not.toContain("UNKNOWN");
    expect(document.body.textContent).not.toContain("Something went wrong");
  });
});

describe("J3 fresh project empty state", () => {
  it("names what to do and offers two samples that fill the composer", async () => {
    historyTurns = [];
    renderChat();
    expect(await screen.findByTestId("chat-empty-state")).toBeTruthy();
    expect(screen.getByTestId("chat-empty-state").textContent).toContain(
      "Describe a task",
    );
    const samples = await screen.findAllByTestId(/chat-sample-[12]/);
    expect(samples).toHaveLength(2);
    fireEvent.click(screen.getByTestId("chat-sample-1"));
    expect(
      (screen.getByTestId("chat-prompt") as HTMLTextAreaElement).value,
    ).not.toBe("");
  });
});

describe("J5 single error line", () => {
  it("shows what failed plus retry, never the bare code", async () => {
    streamReplies.push(() =>
      sseBody([
        `data: {"type":"start","stream_id":"srv-e","run_id":"r-e"}`,
        `data: {"type":"error","stream_id":"srv-e","run_id":"r-e","code":"BUDGET_CAPPED","message":"wire"}`,
        "",
      ]),
    );
    renderChat();
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "do the thing" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    const line = await screen.findByTestId("chat-error-line");
    expect(line.textContent).toContain("do the thing");
    const retry = await screen.findByTestId("kit-error-retry");
    expect(retry.textContent).toBe("Retry");
    const page = document.body.textContent ?? "";
    expect(page).not.toContain("UNKNOWN");
    expect(screen.queryByTestId("kit-error-code")).toBeNull();
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    expect(screen.queryAllByTestId("chat-error-line")).toHaveLength(1);
    streamReplies.push(() =>
      sseBody([
        `data: {"type":"start","stream_id":"srv-r","run_id":"r-r"}`,
        `data: {"type":"delta","stream_id":"srv-r","run_id":"r-r","text":"back"}`,
        `data: {"type":"done","stream_id":"srv-r","run_id":"r-r","text":"back"}`,
        "",
      ]),
    );
    fireEvent.click(retry);
    await waitFor(() => {
      expect(historyPosts.length).toBeGreaterThan(0);
    });
  });
});

describe("J6 composer", () => {
  it("is an auto-grow textarea with calm focus and no Draft label", async () => {
    historyTurns = [];
    renderChat();
    const field = (await screen.findByTestId(
      "chat-prompt",
    )) as HTMLTextAreaElement;
    expect(field.tagName).toBe("TEXTAREA");
    fireEvent.change(field, { target: { value: "hello" } });
    expect(screen.queryByTestId("chat-draft-chip")).toBeNull();
    const statusline = await screen.findByTestId("chat-statusline");
    expect(statusline.getAttribute("title")).toBeTruthy();
  });
});

describe("J9 named buttons", () => {
  it("every icon-only button in chat has a name", async () => {
    historyTurns = [];
    streamReplies.push(() =>
      sseBody([
        `data: {"type":"start","stream_id":"srv-j","run_id":"r-j"}`,
        `data: {"type":"delta","stream_id":"srv-j","run_id":"r-j","text":"answer here"}`,
        `data: {"type":"done","stream_id":"srv-j","run_id":"r-j","text":"answer here"}`,
        "",
      ]),
    );
    renderChat();
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(await screen.findByTestId("chat-copy")).toBeTruthy();
    const buttons = screen
      .getByTestId("chat-area")
      .querySelectorAll("button");
    const unnamed: string[] = [];
    buttons.forEach((button) => {
      const name =
        button.getAttribute("aria-label") ??
        (button.textContent ?? "").trim();
      if (name === "") {
        unnamed.push(
          button.getAttribute("data-testid") ?? button.outerHTML.slice(0, 80),
        );
      }
    });
    expect(unnamed).toEqual([]);
  });
});
