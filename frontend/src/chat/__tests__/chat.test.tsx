/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import {HttpApiClient} from "../../api/client";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { ENDPOINTS } from "../../api/endpoints";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { ChatArea } from "../index";

type Nested = Record<string, unknown>;

function leafValues(node: Nested, acc: string[] = []): string[] {
  for (const key of Object.keys(node)) {
    const value = node[key];
    if (typeof value === "object" && value !== null) {
      leafValues(value as Nested, acc);
    } else {
      acc.push(value as string);
    }
  }
  return acc;
}

const LOCALE_TEXT = new Set<string>([
  ...leafValues(en as unknown as Nested),
  ...leafValues(uk as unknown as Nested),
]);

function visibleTexts(container: HTMLElement): string[] {
  const walker = container.ownerDocument.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
  );
  const out: string[] = [];
  let node = walker.nextNode();
  while (node) {
    const text = (node.textContent ?? "").trim();
    if (text.length > 0) {
      out.push(text);
    }
    node = walker.nextNode();
  }
  return out;
}

const ONLINE = Object.getOwnPropertyDescriptor(window.navigator, "onLine");

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  if (ONLINE !== undefined) {
    Object.defineProperty(window.navigator, "onLine", ONLINE);
  } else {
    Object.defineProperty(window.navigator, "onLine", {
      value: true,
      configurable: true,
    });
  }
});

function promptAndSend(text: string): void {
  fireEvent.change(screen.getByTestId("chat-prompt"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByTestId("chat-send"));
}

function streamSse(delta: string): Response {
  return new Response(
    `data: ${JSON.stringify({ stream_id: "s-x", delta, done: true })}\n`,
    {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    },
  );
}

describe("chat area streaming", () => {
  it("posts a prompt and renders streamed tokens incrementally", async () => {
    const client = new FakeApiClient({ chatDeltas: ["Hel", "lo"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    expect(await screen.findByText("hello")).toBeTruthy();
    const streamed = await screen.findAllByText("Hello");
    expect(streamed.length).toBe(2);
  });

  it("streams through the client entry to the chat stream route", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      seen.push(String(url));
      return new Response(
        'data: {"stream_id":"s-9","delta":"hi","done":true}\n',
        {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        },
      );
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    const streamed = await screen.findAllByText("hi");
    expect(streamed.length).toBe(2);
    expect(seen).toContain(ENDPOINTS.chatStream);
  });

  it("aborts the stream cleanly and cancels the run", async () => {
    let release!: () => void;
    const gate = new Promise<Response>((resolve) => {
      release = () => resolve(streamSse("late"));
    });
    const cancelled: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      const target = String(url);
      if (target.includes("/api/v1/chat/cancel")) {
        cancelled.push(target);
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      if (target.includes("/api/v1/chat/stream")) {
        return gate;
      }
      throw new Error(`unexpected fetch to ${target}`);
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("chat-abort"));
    await act(async () => {
      release();
    });
    await screen.findByText("hello");
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
    expect(cancelled.length).toBe(1);
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });

  it("shows the draft chip, spinner, timestamp and offline dot", async () => {
    const client = new FakeApiClient({ chatDeltas: ["ok"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "draft text" },
    });
    // J6: no "Draft" label; the typed text stays in the box.
    expect(screen.queryByTestId("chat-draft-chip")).toBeNull();
    expect(
      (screen.getByTestId("chat-prompt") as HTMLTextAreaElement).value,
    ).toBe("draft text");
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    const streamed = await screen.findAllByText("ok");
    expect(streamed.length).toBe(2);
    const stamps = await screen.findAllByTestId("chat-timestamp");
    expect(stamps.length).toBeGreaterThanOrEqual(2);
    Object.defineProperty(window.navigator, "onLine", {
      value: false,
      configurable: true,
    });
    await act(async () => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(await screen.findByTestId("chat-offline-dot")).toBeTruthy();
    expect(screen.getByTestId("chat-offline-dot").textContent).toBe(
      t("chat.stream.offline"),
    );
  });

  it("queues prompts offline and flushes them on reconnect", async () => {
    Object.defineProperty(window.navigator, "onLine", {
      value: false,
      configurable: true,
    });
    const client = new FakeApiClient({ chatDeltas: ["back"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("chat-offline-dot")).toBeTruthy();
    promptAndSend("queued hello");
    expect(await screen.findByTestId("chat-toast")).toBeTruthy();
    expect(screen.queryByText("queued hello")).toBeNull();
    Object.defineProperty(window.navigator, "onLine", {
      value: true,
      configurable: true,
    });
    await act(async () => {
      window.dispatchEvent(new Event("online"));
    });
    expect(await screen.findByText("queued hello")).toBeTruthy();
    const flushed = await screen.findAllByText("back");
    expect(flushed.length).toBe(2);
  });

  it("renders the three-button approval card after a completed stream", async () => {
    const client = new FakeApiClient({ chatDeltas: ["done deal"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("please do it");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    expect(await screen.findByTestId("approval-edit")).toBeTruthy();
    expect(await screen.findByTestId("approval-reject")).toBeTruthy();
    fireEvent.click(screen.getByTestId("approval-edit"));
    const field = await screen.findByTestId("approval-edit-field");
    fireEvent.change(field, { target: { value: "revised deal" } });
    fireEvent.click(await screen.findByTestId("approval-edit-save"));
    expect(
      (screen.getByTestId("chat-prompt") as HTMLInputElement).value,
    ).toBe("revised deal");
    fireEvent.click(screen.getByTestId("approval-accept"));
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });

  it("keeps a chat-first layout with no graph canvas", async () => {
    const client = new FakeApiClient({ chatDeltas: ["x"] });
    const view = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("chat-area")).toBeTruthy();
    expect(await screen.findByTestId("chat-layout")).toBeTruthy();
    expect(await screen.findByTestId("chat-composer")).toBeTruthy();
    expect(screen.queryByTestId("graph-canvas")).toBeNull();
    expect(view.container.querySelector("canvas")).toBeNull();
    promptAndSend("hello");
    const streamed = await screen.findAllByText("x");
    expect(streamed.length).toBe(2);
    expect(view.container.querySelector("canvas")).toBeNull();
  });

  it("shows blocking errors inline and never as toasts", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ code: "BUDGET_CAPPED" }), {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
    );
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    const line = await screen.findByTestId("chat-error-line");
    expect(line.textContent).toContain(t("api.error.budget_capped"));
    expect(screen.queryByTestId("chat-toast")).toBeNull();
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
  });

  it("toasts background cancel failures only", async () => {
    let release!: () => void;
    const gate = new Promise<Response>((resolve) => {
      release = () => resolve(streamSse("late"));
    });
    vi.stubGlobal("fetch", async (url: unknown) => {
      const target = String(url);
      if (target.includes("/api/v1/chat/cancel")) {
        return new Response(JSON.stringify({ code: "CONTEXT_MISSING" }), {
          status: 500,
          headers: { "content-type": "application/json" },
        });
      }
      if (target.includes("/api/v1/chat/stream")) {
        return gate;
      }
      throw new Error(`unexpected fetch to ${target}`);
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    fireEvent.click(await screen.findByTestId("chat-abort"));
    expect(await screen.findByTestId("chat-toast")).toBeTruthy();
    await act(async () => {
      release();
    });
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
  });

  it("renders no hard-coded strings outside locale files", async () => {
    const client = new FakeApiClient({ chatDeltas: ["Hi"] });
    const view = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    const streamed = await screen.findAllByText("Hi");
    expect(streamed.length).toBe(2);
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    const stamps = await screen.findAllByTestId("chat-timestamp");
    const extra = new Set<string>([
      "hello",
      "Hi",
      ...stamps.map((node) => (node.textContent ?? "").trim()),
    ]);
    const stray = visibleTexts(view.container).filter(
      (text) => !LOCALE_TEXT.has(text) && !extra.has(text),
    );
    expect(stray).toEqual([]);
  });

  it("resolves every used key in both frozen locales", async () => {
    const client = new FakeApiClient({ chatDeltas: ["ok"] });
    setLocale("en");
    const english = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    const streamedEn = await screen.findAllByText("ok");
    expect(streamedEn.length).toBe(2);
    const englishText = english.container.textContent ?? "";
    english.unmount();
    cleanup();
    setLocale("uk");
    const clientUk = new FakeApiClient({ chatDeltas: ["ok"] });
    render(
      <ApiClientProvider client={clientUk}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    const streamedUk = await screen.findAllByText("ok");
    expect(streamedUk.length).toBe(2);
    expect(await screen.findByTestId("chat-send")).toBeTruthy();
    expect(screen.getByTestId("chat-send").textContent).toBe(
      t("chat.composer.send"),
    );
    expect(englishText).toContain(en.chat.composer.send);
    expect(screen.getByTestId("chat-send").textContent).toBe(
      uk.chat.composer.send,
    );
    expect(/[\u0400-\u04FF]/.test(englishText)).toBe(false);
  });
});
