/** @vitest-environment jsdom */
// B7: an animated circle beside "Working" in the status line and on
// Stop while a run streams, also when returning to chat mid-run;
// respects reduced motion; CSS only. FAKE seam only at the fetch
// boundary.
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { readFileSync } from "node:fs";
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { dirname, join } from "node:path";
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea } from "../index";

const shellCss = readFileSync(
  join(
    dirname(fileURLToPath(import.meta.url)),
    "../../ui/shell.css",
  ),
  "utf-8",
);

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubHangingStream(): {
  enqueue: (text: string) => void;
} {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const live = new ReadableStream<Uint8Array>({
    start(entry) {
      controller = entry;
    },
  });
  vi.stubGlobal("fetch", async (input: unknown) => {
    const url = String(input);
    if (url.startsWith("/api/v1/chat/history")) {
      return jsonBody({ turns: [] });
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: "p-spin", models: [] });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [] });
    }
    if (url.includes("/api/v1/chat/stream")) {
      return new Response(live, {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      });
    }
    if (url.includes("/api/v1/chat/cancel")) {
      return jsonBody({ ok: true });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  return {
    enqueue: (text: string) => {
      controller.enqueue(encoder.encode(text));
    },
  };
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("B7 working circle", () => {
  it("spins beside Working and on Stop while streaming, also mid-run return", async () => {
    const stream = stubHangingStream();
    const client = new HttpApiClient();
    const first = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-spin" />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "spin me" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    stream.enqueue(
      'data: {"type":"start","stream_id":"srv-s","run_id":"r-s"}\n\n',
    );
    stream.enqueue(
      'data: {"type":"delta","stream_id":"srv-s","run_id":"r-s","text":"spinning"}\n\n',
    );
    expect(await screen.findByText("spinning")).toBeTruthy();
    // Circle beside Working in the status line.
    const statusline = await screen.findByTestId("chat-statusline");
    expect(statusline.textContent).toContain(t("chat.composer.statusWorking"));
    const circles = statusline.querySelectorAll(".fx-spin");
    expect(circles.length).toBeGreaterThanOrEqual(1);
    // Circle on the Stop button too.
    const abort = await screen.findByTestId("chat-abort");
    expect(abort.querySelectorAll(".fx-spin")).toHaveLength(1);
    expect(abort.textContent).toContain(t("chat.abort.cancel"));
    // Leaving and returning mid-run keeps both circles.
    first.unmount();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-spin" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    const returned = await screen.findByTestId("chat-statusline");
    expect(returned.querySelectorAll(".fx-spin").length).toBeGreaterThanOrEqual(
      1,
    );
    expect(
      (await screen.findByTestId("chat-abort")).querySelectorAll(".fx-spin"),
    ).toHaveLength(1);
  });

  it("is CSS only and still under reduced motion", () => {
    expect(shellCss).toContain(".fx-spin");
    expect(shellCss).toContain("@keyframes fx-spin");
    expect(shellCss).toContain("prefers-reduced-motion");
  });
});
