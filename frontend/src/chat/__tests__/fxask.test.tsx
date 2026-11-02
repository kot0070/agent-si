/** @vitest-environment jsdom */
// FXASK2: install-permission-asked-once dialog over the REAL chat screen.
// Only the fetch boundary is faked: the chat stream serves served-shaped
// `approval` / held-`done` events carrying the held tool's id (guard
// tool_name), and POST /api/v1/permissions/check answers from an in-memory
// ask-once ledger. The dialog names the event's tool, answers POST it,
// and the served asked_once flag suppresses second runs per tool.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { ApiError } from "../../api/errors";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { startTaskRun } from "../../tasks/startTaskRun";
import { ChatArea } from "../index";
import { askPermission } from "../permissions";

const PROJECT_ID = "p-1";
// Guard-style tool name (sdk_adapter/tool_guard.py ToolCall.tool_name),
// carried by the approval event's tool_id field — never project-derived.
const TOOL = "helper-tool";
const CHECK_URL = "/api/v1/permissions/check";
const STREAM_URL = "/api/v1/chat/stream";

interface SeenPost {
  url: string;
  body: unknown;
}

const askedTools = new Set<string>();
const f1Posts: SeenPost[] = [];
let streamKind: "approval" | "manager-held" | "toolless" = "approval";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function approvalStream(): Response {
  const lines = [
    `data: {"type":"start","stream_id":"srv-fx","run_id":"r-fx"}`,
    `data: {"type":"approval","stream_id":"srv-fx","run_id":"r-fx","tool_id":"${TOOL}","reason":"run held: install permission needed"}`,
    "",
  ].join("\n");
  return new Response(lines, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function managerHeldStream(): Response {
  const lines = [
    `data: {"type":"start","stream_id":"srv-fx","run_id":"r-fx"}`,
    `data: {"type":"done","stream_id":"srv-fx","run_id":"r-fx","executed":false,"approval_requested":true,"tool_id":"${TOOL}","reason":"run held: install permission needed"}`,
    "",
  ].join("\n");
  return new Response(lines, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function toollessApprovalStream(): Response {
  const lines = [
    `data: {"type":"start","stream_id":"srv-fx","run_id":"r-fx"}`,
    `data: {"type":"approval","stream_id":"srv-fx","run_id":"r-fx","reason":"run held"}`,
    "",
  ].join("\n");
  return new Response(lines, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function stubBoundary(): void {
  askedTools.clear();
  f1Posts.length = 0;
  streamKind = "approval";
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes(STREAM_URL) && method === "POST") {
      if (streamKind === "manager-held") {
        return managerHeldStream();
      }
      if (streamKind === "toolless") {
        return toollessApprovalStream();
      }
      return approvalStream();
    }
    if (url === CHECK_URL && method === "POST") {
      let body: unknown = null;
      try {
        body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
      } catch {
        body = null;
      }
      f1Posts.push({ url, body });
      const toolId = (body as { tool_id?: unknown } | null)?.tool_id;
      const tool = typeof toolId === "string" ? toolId : "";
      const seen = askedTools.has(tool);
      if (tool !== "") {
        askedTools.add(tool);
      }
      return jsonBody({ allowed: true, asked_once: seen });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

function f1Tools(): string[] {
  return f1Posts.map((post) => {
    const body = post.body as { tool_id?: unknown } | null;
    return typeof body?.tool_id === "string" ? body.tool_id : "";
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

describe("fxask install-permission-asked-once dialog", () => {
  it("pending ask shows a dialog with the event tool id", async () => {
    renderChat();
    promptAndSend("please install the helper");
    const dialog = await screen.findByTestId("permission-dialog");
    expect(dialog).toBeTruthy();
    expect(screen.getByTestId("permission-tool").textContent).toBe(TOOL);
    expect(screen.getByTestId("permission-allow")).toBeTruthy();
    expect(screen.getByTestId("permission-deny")).toBeTruthy();
  });

  it("Allow posts F1 with that tool and closes the dialog", async () => {
    renderChat();
    promptAndSend("please install the helper");
    await screen.findByTestId("permission-dialog");
    fireEvent.click(screen.getByTestId("permission-allow"));
    await waitFor(() => {
      expect(f1Tools()).toContain(TOOL);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("permission-dialog")).toBeNull();
    });
    expect(
      await screen.findByText(`Install permission granted for ${TOOL}`),
    ).toBeTruthy();
  });

  it("reload with a stored answer shows no dialog", async () => {
    askedTools.add(TOOL);
    renderChat();
    promptAndSend("please install the helper");
    await waitFor(() => {
      expect(f1Posts.length).toBeGreaterThanOrEqual(1);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("permission-dialog")).toBeNull();
    });
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    expect(f1Tools()).toContain(TOOL);
  });

  it("renders real Ukrainian labels for the dialog keys", async () => {
    setLocale("uk");
    renderChat();
    promptAndSend("please install the helper");
    const dialog = await screen.findByTestId("permission-dialog");
    expect(dialog).toBeTruthy();
    expect(dialog.getAttribute("aria-label")).toBe("Дозвіл на встановлення");
    expect(screen.getByTestId("permission-allow").textContent).toBe(
      "Дозволити раз",
    );
  });

  it("Deny tells the run and closes the dialog", async () => {
    renderChat();
    promptAndSend("please install the helper");
    await screen.findByTestId("permission-dialog");
    fireEvent.click(screen.getByTestId("permission-deny"));
    await waitFor(() => {
      expect(f1Tools()).toContain(TOOL);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("permission-dialog")).toBeNull();
    });
    expect(
      await screen.findByText(`Install permission denied for ${TOOL}`),
    ).toBeTruthy();
  });

  it("a hold without a tool id keeps the blocking behavior, no dialog", async () => {
    streamKind = "toolless";
    renderChat();
    promptAndSend("please install the helper");
    await waitFor(() => {
      expect(screen.queryByTestId("kit-error-panel")).toBeTruthy();
    });
    expect(screen.queryByTestId("permission-dialog")).toBeNull();
    expect(f1Posts.length).toBe(0);
  });

  it("task-run path: chat approval hold rejects with the same tool id", async () => {
    const client = new HttpApiClient();
    const seen: string[] = [];
    const handle = startTaskRun(client, {
      projectId: PROJECT_ID,
      promptRef: "please install the helper",
      streamId: "task-run-1",
      onText: (text) => {
        seen.push(text);
      },
    });
    const failure = await handle.done.then(
      () => null,
      (cause: unknown) => cause,
    );
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe("APPROVAL_REQUIRED");
    expect((failure as ApiError).toolId).toBe(TOOL);
    const outcome = await askPermission(
      (failure as ApiError).toolId as string,
    );
    expect(outcome.askedOnce).toBe(false);
    expect(f1Tools()).toContain(TOOL);
    expect(seen).toEqual([]);
  });

  it("task-run path: manager held-done raises the same per-tool check", async () => {
    streamKind = "manager-held";
    const client = new HttpApiClient();
    const handle = startTaskRun(client, {
      projectId: PROJECT_ID,
      promptRef: "please install the helper",
      streamId: "task-run-2",
      onText: () => undefined,
    });
    const failure = await handle.done.then(
      () => null,
      (cause: unknown) => cause,
    );
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe("APPROVAL_REQUIRED");
    expect((failure as ApiError).toolId).toBe(TOOL);
    const outcome = await askPermission(
      (failure as ApiError).toolId as string,
    );
    expect(outcome.askedOnce).toBe(false);
    expect(f1Tools()).toContain(TOOL);
  });
});
