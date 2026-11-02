/** @vitest-environment jsdom */
// FXR1B grant dialog over the REAL chat screen (FAKE seam only at the
// fetch boundary): three buttons, real command display, once/project/
// deny semantics. RED first, then the dialog change.
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
import { InstallGrantsList } from "../../settings/index";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea } from "../index";

const PROJECT_ID = "p-1";
const TOOL = "install:p-1:npm";
const STREAM_URL = "/api/v1/chat/stream";
const HISTORY_URL = "/api/v1/chat/history";
const DECIDE_URL = "/api/v1/permissions/decide";
const GRANT_URL = "/api/v1/permissions/project-grant";
const ASK_ARGV_URL = "/api/v1/permissions/install-request";

interface SeenPost {
  url: string;
  method: string;
  body: unknown;
}

let historyPosts: SeenPost[];
let streamPosts: SeenPost[];
let streamReplies: (() => Response)[];
let decidePosts: SeenPost[];
let grantPosts: SeenPost[];

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

function holdStream(): Response {
  return sseBody([
    `data: {"type":"start","stream_id":"srv-fx","run_id":"r-fx"}`,
    `data: {"type":"approval","stream_id":"srv-fx","run_id":"r-fx","tool_id":"${TOOL}","reason":"run held: install permission needed"}`,
    "",
  ]);
}

function doneStream(text: string): Response {
  return sseBody([
    `data: {"type":"start","stream_id":"srv-fx","run_id":"r-fx"}`,
    `data: {"type":"delta","stream_id":"srv-fx","run_id":"r-fx","text":"${text}"}`,
    `data: {"type":"done","stream_id":"srv-fx","run_id":"r-fx","text":"${text}"}`,
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
      return jsonBody({ turns: [] });
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
    if (url === GRANT_URL && method === "POST") {
      grantPosts.push({ url, method, body });
      return jsonBody({
        project_id: PROJECT_ID,
        installer: "npm",
        subcommand: "install",
        time: "2026-01-01T00:00:00Z",
      });
    }
    if (url.startsWith(ASK_ARGV_URL) && method === "GET") {
      return jsonBody({
        tool_id: TOOL,
        argv: ["npm", "install", "lodash"],
      });
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

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
  historyPosts = [];
  streamPosts = [];
  streamReplies = [];
  decidePosts = [];
  grantPosts = [];
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

describe("grant dialog buttons and display", () => {
  it("shows three buttons, the real command, a why sentence, no raw key", async () => {
    streamReplies.push(() => holdStream());
    renderChat();
    promptAndSend("install lodash");
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
    expect(await screen.findByText("npm install")).toBeTruthy();
    expect(screen.getByTestId("permission-allow").textContent).toBe(
      "Allow once",
    );
    expect(
      screen.getByTestId("permission-allow-project").textContent,
    ).toBe("For this project");
    expect(screen.getByTestId("permission-deny").textContent).toBe("Deny");
    expect(screen.getByTestId("permission-tool").textContent).toBe(
      "npm install",
    );
    const page = document.body.textContent ?? "";
    expect(page).not.toContain("install:p-1:npm");
    expect(page).not.toContain("69cb70ed");
  });
});

describe("allow once", () => {
  it("replays the parked run, then asks again for the next install", async () => {
    streamReplies.push(
      () => holdStream(),
      () => doneStream("installed lodash"),
      () => holdStream(),
    );
    renderChat();
    promptAndSend("install lodash");
    fireEvent.click(await screen.findByTestId("permission-allow"));
    await waitFor(() => {
      expect(streamPosts).toHaveLength(2);
    });
    expect(decidePosts).toHaveLength(1);
    expect(
      (decidePosts[0]?.body as { decision?: unknown }).decision,
    ).toBe("allow");
    expect(grantPosts).toHaveLength(0);
    await screen.findByText("installed lodash");
    // Next install asks again.
    promptAndSend("install other");
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
    await waitFor(() => {
      expect(streamPosts).toHaveLength(3);
    });
  });
});

describe("for this project", () => {
  it("records the grant and replays without a new user turn", async () => {
    streamReplies.push(
      () => holdStream(),
      () => doneStream("installed lodash"),
    );
    renderChat();
    promptAndSend("install lodash");
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
    expect(await screen.findByText("npm install")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("permission-allow-project"));
    await waitFor(() => {
      expect(grantPosts).toHaveLength(1);
    });
    expect(grantPosts[0]?.body).toEqual({
      project_id: PROJECT_ID,
      tool_id: TOOL,
    });
    await waitFor(() => {
      expect(streamPosts).toHaveLength(2);
    });
    expect(decidePosts).toHaveLength(0);
    const users = screen.getAllByTestId("chat-user-message");
    expect(
      users.filter((node) =>
        node.textContent?.includes("install lodash"),
      ),
    ).toHaveLength(1);
    expect(
      await screen.findByText("Install permission granted for npm install"),
    ).toBeTruthy();
  });
});

describe("deny", () => {
  it("closes with a plain denied line and does not resend", async () => {
    streamReplies.push(() => holdStream());
    renderChat();
    promptAndSend("install lodash");
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
    expect(await screen.findByText("npm install")).toBeTruthy();
    fireEvent.click(screen.getByTestId("permission-deny"));
    await waitFor(() => {
      expect(decidePosts).toHaveLength(1);
    });
    expect(
      (decidePosts[0]?.body as { decision?: unknown }).decision,
    ).toBe("deny");
    expect(
      await screen.findByText("Install permission denied for npm install"),
    ).toBeTruthy();
    expect(streamPosts).toHaveLength(1);
    expect(screen.queryByTestId("approval-card")).toBeNull();
    await waitFor(() => {
      expect(
        historyPosts.filter(
          (post) => (post.body as { status?: unknown }).status === "failed",
        ),
      ).toHaveLength(1);
    });
    const failed = historyPosts.find(
      (post) => (post.body as { status?: unknown }).status === "failed",
    );
    expect((failed?.body as { error_code?: unknown }).error_code).toBe(
      "DENIED",
    );
  });
});

describe("install grants list with remove", () => {
  const GRANTS_URL = "/api/v1/permissions/project-grants";

  function stubGrantsBoundary(): void {
    let removed = false;
    vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (url.startsWith(GRANTS_URL) && method === "GET") {
        return jsonBody({
          grants: removed
            ? []
            : [
                {
                  project_id: PROJECT_ID,
                  installer: "npm",
                  subcommand: "install",
                  time: "2026-01-01T00:00:00Z",
                },
              ],
        });
      }
      if (url === GRANT_URL && method === "DELETE") {
        const body =
          typeof init?.body === "string" ? JSON.parse(init.body) : null;
        expect(body).toEqual({
          project_id: PROJECT_ID,
          installer: "npm",
          subcommand: "install",
        });
        removed = true;
        return jsonBody({ removed: true });
      }
      throw new Error(`unexpected fetch ${method} ${url}`);
    });
  }

  it("lists grants and removes one", async () => {
    stubGrantsBoundary();
    render(<InstallGrantsList projectId={PROJECT_ID} />);
    expect(await screen.findByTestId("install-grants")).toBeTruthy();
    expect(await screen.findByText("npm install")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("install-grant-remove"));
    await waitFor(() => {
      expect(screen.queryByText("npm install")).toBeNull();
    });
    expect(await screen.findByTestId("install-grants")).toBeTruthy();
  });
});
