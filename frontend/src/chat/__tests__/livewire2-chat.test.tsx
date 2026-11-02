/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import {HttpApiClient} from "../../api/client";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { ChatArea } from "../index";

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

function sseResponse(
  text: string,
  headers: Record<string, string> = {},
): Response {
  return new Response(text, {
    status: 200,
    headers: { "content-type": "text/event-stream", ...headers },
  });
}

function errorPanelMessage(): string | null {
  const panel = screen.queryByTestId("chat-error-line");
  return panel?.querySelector("p")?.textContent ?? null;
}

describe("L0B-15 one send shows one assistant block", () => {
  it("shows a done-carried repeat and a double done only once", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        sseResponse(
          [
            'data: {"type":"start","stream_id":"srv-1","run_id":"r-1"}',
            'data: {"type":"delta","stream_id":"srv-1","run_id":"r-1","text":"Hel"}',
            'data: {"type":"delta","stream_id":"srv-1","run_id":"r-1","text":"lo"}',
            'data: {"type":"done","stream_id":"srv-1","run_id":"r-1","text":"Hello","output_ref":"artifact:run/r-1/output"}',
            'data: {"type":"done","stream_id":"srv-1","run_id":"r-1"}',
            "",
          ].join("\n"),
          { "x-stream-id": "srv-1" },
        ),
    );
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    const blocks = await screen.findAllByTestId("chat-assistant-message");
    expect(blocks).toHaveLength(1);
    expect(blocks[0]?.querySelector("p")?.textContent).toBe("Hello");
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
  });

  it("shows one assistant block for one send on the fake path", async () => {
    const client = new FakeApiClient({ chatDeltas: ["Hel", "lo"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    const blocks = await screen.findAllByTestId("chat-assistant-message");
    expect(blocks).toHaveLength(1);
    expect(blocks[0]?.querySelector("p")?.textContent).toBe("Hello");
  });
});

describe("chat cancel uses the server stream id", () => {
  it("posts the start-event id to the cancel route on abort", async () => {
    const cancelled: unknown[] = [];
    const encoder = new TextEncoder();
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    vi.stubGlobal("fetch", async (url: unknown, init?: RequestInit) => {
      const target = String(url);
      if (target.includes("/api/v1/chat/cancel")) {
        const raw = init?.body;
        cancelled.push(
          typeof raw === "string" && raw.length > 0
            ? (JSON.parse(raw) as unknown)
            : undefined,
        );
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      // BOTH behaviours kept: FXTURN 5da7197 fresh stream per chat open
      // (no locked share) + FXRED route-aware JSON for incidental reads
      // (history/models must not consume the chat stream).
      if (target.includes("/api/v1/chat/stream")) {
        const streamBody = new ReadableStream<Uint8Array>({
          start(entry) {
            controller = entry;
          },
        });
        return new Response(streamBody, {
          status: 200,
          headers: {
            "content-type": "text/event-stream",
            "x-stream-id": "srv-9",
          },
        });
      }
      if (target.includes("/api/v1/chat/history")) {
        return new Response(JSON.stringify({ turns: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      if (target.includes("/api/v1/chat/models")) {
        return new Response(JSON.stringify({ models: [] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      // Incidental reads (hierarchy and anything else) answer on their
      // own body: sharing one stream across responses locks it and the
      // stream reader throws, which this cancel test never covers.
      return new Response(
        JSON.stringify({ code: "FXCHAT_UNEXPECTED_API" }),
        {
          status: 404,
          headers: { "content-type": "application/json" },
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
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    controller.enqueue(
      encoder.encode(
        'data: {"type":"start","stream_id":"srv-9","run_id":"r-9"}\n\n',
      ),
    );
    controller.enqueue(
      encoder.encode(
        'data: {"type":"delta","stream_id":"srv-9","run_id":"r-9","text":"Hel"}\n\n',
      ),
    );
    expect(await screen.findByText("Hel")).toBeTruthy();
    fireEvent.click(screen.getByTestId("chat-abort"));
    expect(cancelled).toEqual([{ stream_id: "srv-9" }]);
    controller.enqueue(
      encoder.encode(
        'data: {"type":"done","stream_id":"srv-9","run_id":"r-9"}\n\n',
      ),
    );
    controller.close();
    await screen.findByText("hello");
    expect(screen.queryByTestId("chat-spinner")).toBeNull();
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });
});

describe("L0B-11 localized chat errors", () => {
  function stubErrorEvent(code: string): void {
    vi.stubGlobal(
      "fetch",
      async () =>
        sseResponse(
          'data: {"type":"start","stream_id":"srv-e","run_id":"r-e"}\n\n' +
            `data: {"type":"error","stream_id":"srv-e","run_id":"r-e","code":${JSON.stringify(code)},"message":"wire"}\n\n`,
        ),
    );
  }

  it("shows the localized message, never the raw code (en)", async () => {
    stubErrorEvent("BUDGET_CAPPED");
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    await screen.findByTestId("chat-error-line");
    expect(errorPanelMessage()).toContain(t("api.error.budget_capped"));
    expect(errorPanelMessage()).not.toContain("BUDGET_CAPPED");
  });

  it("shows the localized message, never the raw code (uk)", async () => {
    setLocale("uk");
    stubErrorEvent("BUDGET_CAPPED");
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("привіт");
    await screen.findByTestId("chat-error-line");
    expect(errorPanelMessage()).toContain(t("api.error.budget_capped"));
    expect(errorPanelMessage()).not.toBe("BUDGET_CAPPED");
  });

  it("shows the localized generic for an unknown code", async () => {
    stubErrorEvent("WIBBLE_X9");
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    await screen.findByTestId("chat-error-line");
    expect(errorPanelMessage()).toContain(t("errors.generic"));
    expect(errorPanelMessage()).not.toContain("WIBBLE_X9");
  });

  it("shows the connect-provider message with no raw code (en and uk)", async () => {
    stubErrorEvent("NO_PROVIDER_BOUND");
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    await screen.findByTestId("chat-error-line");
    expect(errorPanelMessage()).toContain(t("firstrun.steps.connectProvider"));
    expect(errorPanelMessage()).not.toContain("NO_PROVIDER_BOUND");
    cleanup();
    setLocale("uk");
    stubErrorEvent("NO_PROVIDER_BOUND");
    const clientUk = new HttpApiClient();
    render(
      <ApiClientProvider client={clientUk}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("привіт");
    await screen.findByTestId("chat-error-line");
    expect(errorPanelMessage()).toContain(t("firstrun.steps.connectProvider"));
    expect(errorPanelMessage()).not.toContain("NO_PROVIDER_BOUND");
  });

  it("maps a legacy no-provider 404 to the connect-provider message", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ detail: "no live chat engine" }), {
          status: 404,
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
    await screen.findByTestId("chat-error-line");
    expect(errorPanelMessage()).toContain(t("firstrun.steps.connectProvider"));
  });
});
