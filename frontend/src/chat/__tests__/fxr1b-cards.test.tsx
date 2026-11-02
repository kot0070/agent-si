/** @vitest-environment jsdom */
// FXR1B card-cause: a card shows ONLY for a live proposal the stream's
// own terminal event marks; default no card. History (success, failed,
// stopped, held) never shows one, before or after remount; a decided
// turn never does; a real live waiting proposal shows exactly one.
// FAKE seam only at the fetch boundary.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea } from "../index";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function turn(
  id: string,
  userText: string,
  assistantText: string,
  status: string,
): unknown {
  return {
    project_id: "p-cards",
    user_text: userText,
    assistant_text: assistantText,
    time: "2026-01-01T00:00:00Z",
    id,
    status,
    run_id: `run-${id}`,
    error_code: status === "failed" ? "BUDGET_CAPPED" : "STOPPED",
  };
}

const MIXED_TURNS = [
  turn("t-ok", "map the fence", "fence mapped", "ok"),
  turn("t-fail", "dig the ditch", "half a ditch", "failed"),
  turn("t-stop", "raise the barn", "half a barn", "stopped"),
  turn("t-hold", "paint the gate", "primed", "running"),
];

function stubHistory(): void {
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url.startsWith("/api/v1/chat/history")) {
      const project = new URL(url, "http://localhost").searchParams.get(
        "project_id",
      );
      return jsonBody({ turns: project === "p-cards" ? MIXED_TURNS : [] });
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: "p-cards", models: [] });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [] });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
  stubHistory();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderChat(client?: FakeApiClient): void {
  render(
    <ApiClientProvider client={client ?? new FakeApiClient({})}>
      <ChatArea projectId="p-cards" />
    </ApiClientProvider>,
  );
}

describe("history never shows a card", () => {
  it("zero cards for success, failed, stopped and held turns, also after remount", async () => {
    const client = new FakeApiClient({});
    const first = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-cards" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText("fence mapped")).toBeTruthy();
    expect(await screen.findByText("half a ditch")).toBeTruthy();
    expect(await screen.findByText("half a barn")).toBeTruthy();
    expect(screen.queryAllByTestId("approval-card")).toHaveLength(0);
    expect(screen.queryAllByTestId("approval-accept")).toHaveLength(0);
    // Leaving and returning to the chat changes nothing.
    first.unmount();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-cards" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText("fence mapped")).toBeTruthy();
    expect(screen.queryAllByTestId("approval-card")).toHaveLength(0);
    // A restart (fresh store) still shows no card.
    cleanup();
    resetChatStore();
    renderChat();
    expect(await screen.findByText("half a barn")).toBeTruthy();
    expect(screen.queryAllByTestId("approval-card")).toHaveLength(0);
  });
});

describe("live waiting proposal shows exactly one card", () => {
  it("marks the card on the stream terminal event, hides it after decide", async () => {
    const client = new FakeApiClient({ chatDeltas: ["fresh answer"] });
    const first = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-live" />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "propose this" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(await screen.findByTestId("approval-card")).toBeTruthy();
    expect(screen.queryAllByTestId("approval-card")).toHaveLength(1);
    // The live mark survives leaving and returning mid-session.
    first.unmount();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-live" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("approval-card")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("approval-accept"));
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });
});
