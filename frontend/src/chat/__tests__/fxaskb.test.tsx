/** @vitest-environment jsdom */
// FXASKB: the devrun-hold dialog (B2) plus the recorded-answer journal
// post (B3) over the REAL chat screen. Only the fetch boundary is faked:
// first stream serves the held `approval` event carrying the command's
// install tool id, POST /api/v1/permissions/decide records the decision,
// and the resend serves a finished run. The dialog shows regardless of
// the asked-once flag, Allow/Deny posts the decision with the session
// token and resends the same prompt, and the second run does not ask.
// B3: Accept/Reject under a finished answer each post one journal row
// through token-guarded POST /api/v1/chat/decision.
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
import { clearUiToken, setUiToken } from "../../api/errors";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ChatArea } from "../index";

const PROJECT_ID = "p-fxaskb";
const TOOL = "install:p-fxaskb:fxaskbcmd";
const SESSION_TOKEN = "fxaskb-test-token";
const STREAM_URL = "/api/v1/chat/stream";
const CHECK_URL = "/api/v1/permissions/check";
const DECIDE_URL = "/api/v1/permissions/decide";
const CHAT_DECISION_URL = "/api/v1/chat/decision";

interface SeenPost {
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

let streams: number;
let checkPosts: SeenPost[];
let decidePosts: SeenPost[];
let decisionPosts: SeenPost[];

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function holdStream(): Response {
  const lines = [
    `data: {"type":"start","stream_id":"srv-b","run_id":"r-b"}`,
    `data: {"type":"approval","stream_id":"srv-b","run_id":"r-b","tool_id":"${TOOL}","reason":"run held: install permission needed"}`,
    "",
  ].join("\n");
  return new Response(lines, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function doneStream(text: string): Response {
  const lines = [
    `data: {"type":"start","stream_id":"srv-b","run_id":"r-b"}`,
    `data: {"type":"delta","stream_id":"srv-b","run_id":"r-b","text":"${text}"}`,
    `data: {"type":"done","stream_id":"srv-b","run_id":"r-b"}`,
    "",
  ].join("\n");
  return new Response(lines, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function readHeaders(init?: RequestInit): Record<string, string> {
  const raw = init?.headers;
  if (raw !== undefined && typeof raw === "object" && !(raw instanceof Headers)) {
    if (Array.isArray(raw)) {
      const out: Record<string, string> = {};
      for (const [key, value] of raw as Array<[string, string]>) {
        out[key] = value;
      }
      return out;
    }
    return { ...(raw as Record<string, string>) };
  }
  return {};
}

function readBody(init?: RequestInit): unknown {
  try {
    return typeof init?.body === "string" ? JSON.parse(init.body) : null;
  } catch {
    return null;
  }
}

function stubHoldBoundary(secondText: string): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes(STREAM_URL) && method === "POST") {
      streams += 1;
      return streams === 1 ? holdStream() : doneStream(secondText);
    }
    if (url === CHECK_URL && method === "POST") {
      checkPosts.push({ url, headers: readHeaders(init), body: readBody(init) });
      return jsonBody({ allowed: false, asked_once: false });
    }
    if (url === DECIDE_URL && method === "POST") {
      decidePosts.push({ url, headers: readHeaders(init), body: readBody(init) });
      return jsonBody({ ok: true });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

function stubDoneBoundary(): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.includes(STREAM_URL) && method === "POST") {
      return doneStream("done deal");
    }
    if (url === CHAT_DECISION_URL && method === "POST") {
      decisionPosts.push({ url, headers: readHeaders(init), body: readBody(init) });
      return jsonBody({ ok: true });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  clearUiToken();
  setUiToken(SESSION_TOKEN);
  streams = 0;
  checkPosts = [];
  decidePosts = [];
  decisionPosts = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  clearUiToken();
  resetLocaleForTests();
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

describe("fxaskb devrun-hold dialog", () => {
  it("Allow posts the decision with the token and resends without asking", async () => {
    stubHoldBoundary("second run done");
    renderChat();
    promptAndSend("please install the helper");
    const dialog = await screen.findByTestId("permission-dialog");
    expect(dialog).toBeTruthy();
    expect(screen.getByTestId("permission-tool").textContent).toBe(
      "fxaskbcmd",
    );
    fireEvent.click(screen.getByTestId("permission-allow"));
    await waitFor(() => {
      expect(decidePosts.length).toBe(1);
    });
    expect(decidePosts[0]?.headers["x-ui-session-token"]).toBe(SESSION_TOKEN);
    expect(decidePosts[0]?.body).toEqual({
      tool_id: TOOL,
      decision: "allow",
      project_id: PROJECT_ID,
    });
    // The same prompt resends automatically: the second run finishes
    // with the stored answer and never asks again.
    await waitFor(() => {
      expect(streams).toBe(2);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("permission-dialog")).toBeNull();
    });
    expect(await screen.findAllByText("second run done")).toHaveLength(2);
    expect(checkPosts.length).toBe(0);
  });

  it("Deny posts deny with the token and closes without resending", async () => {
    stubHoldBoundary("run refused, continuing");
    renderChat();
    promptAndSend("please install the helper");
    await screen.findByTestId("permission-dialog");
    fireEvent.click(screen.getByTestId("permission-deny"));
    await waitFor(() => {
      expect(decidePosts.length).toBe(1);
    });
    expect(decidePosts[0]?.headers["x-ui-session-token"]).toBe(SESSION_TOKEN);
    expect(decidePosts[0]?.body).toEqual({
      tool_id: TOOL,
      decision: "deny",
      project_id: PROJECT_ID,
    });
    // The denied part closes with a plain FAILED line: the held message
    // keeps only the receipt, the run does not loop, no resend.
    await waitFor(() => {
      expect(screen.queryByTestId("permission-dialog")).toBeNull();
    });
    expect(
      await screen.findByText("Install permission denied for fxaskbcmd"),
    ).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(streams).toBe(1);
    expect(checkPosts.length).toBe(0);
  });
});

describe("fxaskb recorded-answer journal post", () => {
  it("Accept posts one journal row with the session token", async () => {
    stubDoneBoundary();
    renderChat();
    promptAndSend("please do it");
    fireEvent.click(await screen.findByTestId("approval-accept"));
    await waitFor(() => {
      expect(decisionPosts.length).toBe(1);
    });
    expect(decisionPosts[0]?.headers["x-ui-session-token"]).toBe(SESSION_TOKEN);
    const body = decisionPosts[0]?.body as Record<string, unknown>;
    expect(body["project_id"]).toBe(PROJECT_ID);
    expect(body["decision"]).toBe("accepted");
    expect(typeof body["proposal"]).toBe("string");
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });

  it("Reject posts one journal row with the session token", async () => {
    stubDoneBoundary();
    renderChat();
    promptAndSend("please do it");
    fireEvent.click(await screen.findByTestId("approval-reject"));
    await waitFor(() => {
      expect(decisionPosts.length).toBe(1);
    });
    expect(decisionPosts[0]?.headers["x-ui-session-token"]).toBe(SESSION_TOKEN);
    const body = decisionPosts[0]?.body as Record<string, unknown>;
    expect(body["project_id"]).toBe(PROJECT_ID);
    expect(body["decision"]).toBe("rejected");
  });
});
