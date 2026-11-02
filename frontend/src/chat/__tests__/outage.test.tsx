/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
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

function okJson(): Response {
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function sse(delta: string): Response {
  return new Response(
    `data: ${JSON.stringify({ stream_id: "s-h", delta, done: true })}\n`,
    {
      status: 200,
      headers: { "content-type": "text/event-stream" },
    },
  );
}

describe("outage and health transitions", () => {
  it("marks the channel degraded on stream failure and recovers on retry", async () => {
    let mode: "fail" | "ok" = "fail";
    vi.stubGlobal("fetch", async (url: unknown) => {
      const target = String(url);
      if (target.includes("/api/v1/chat/cancel")) {
        return okJson();
      }
      if (target.includes("/api/v1/chat/stream")) {
        if (mode === "fail") {
          return new Response(JSON.stringify({ code: "BUDGET_CAPPED" }), {
            status: 422,
            headers: { "content-type": "application/json" },
          });
        }
        return sse("recovered");
      }
      throw new Error(`unexpected fetch to ${target}`);
    });
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(screen.queryByTestId("chat-error-line")).toBeNull();
    promptAndSend("hello");
    const line = await screen.findByTestId("chat-error-line");
    expect(line.textContent).toContain("hello");
    expect(screen.queryByTestId("chat-health-degraded")).toBeNull();
    expect(await screen.findByTestId("kit-error-retry")).toBeTruthy();
    mode = "ok";
    fireEvent.click(screen.getByTestId("kit-error-retry"));
    const answered = await screen.findAllByText("recovered");
    expect(answered.length).toBe(2);
    await waitFor(() => {
      expect(screen.queryByTestId("chat-error-line")).toBeNull();
    });
  });

  it("shows reconnecting after offline-to-online until the next stream verifies", async () => {
    const client = new FakeApiClient({ chatDeltas: ["back"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(screen.queryByTestId("chat-health-reconnecting")).toBeNull();
    Object.defineProperty(window.navigator, "onLine", {
      value: false,
      configurable: true,
    });
    await act(async () => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(await screen.findByTestId("chat-offline-dot")).toBeTruthy();
    expect(screen.queryByTestId("chat-health-reconnecting")).toBeNull();
    Object.defineProperty(window.navigator, "onLine", {
      value: true,
      configurable: true,
    });
    await act(async () => {
      window.dispatchEvent(new Event("online"));
    });
    const reconnecting = await screen.findByTestId(
      "chat-health-reconnecting",
    );
    expect(reconnecting.textContent).toBe(t("chat.stream.offline"));
    promptAndSend("hello again");
    const flushed = await screen.findAllByText("back");
    expect(flushed.length).toBe(2);
    await waitFor(() => {
      expect(screen.queryByTestId("chat-health-reconnecting")).toBeNull();
    });
  });
});
