/** @vitest-environment jsdom */
// FXDESIGN6 (b): the verdict card shows only for a plain answer with a
// proposal. A typed done event carrying executed:true marks a finished
// engine run: its answer renders (newlines kept) with NO accept/edit/
// reject card. A plain done keeps the card. Structure/behaviour only:
// no CSS literals, no screenshot assertions.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import { ChatArea } from "../index";

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
});

function stubSse(events: string[]): void {
  // String body (not a manual ReadableStream): the client's text path,
  // the same stub shape the green wire tests use.
  const text = events.join("");
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response(text, {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
  );
}

function promptAndSend(text: string): void {
  fireEvent.change(screen.getByTestId("chat-prompt"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByTestId("chat-send"));
}

describe("fxdesign6 engine verdict gate", () => {
  it("keeps the card for a plain answer", async () => {
    stubSse([
      'data: {"type":"start","stream_id":"s-1","run_id":"r-1"}\n\n',
      'data: {"type":"delta","stream_id":"s-1","run_id":"r-1","text":"Hello"}\n\n',
      'data: {"type":"done","stream_id":"s-1","run_id":"r-1"}\n\n',
    ]);
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hi");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    const proposal = await screen.findByTestId("approval-text");
    expect(proposal.textContent).toBe("Hello");
  });

  it("renders engine lines with no card under an executed run", async () => {
    stubSse([
      'data: {"type":"start","stream_id":"s-9","run_id":"r-9"}\n\n',
      'data: {"type":"delta","stream_id":"s-9","run_id":"r-9","text":"line one\\nline two"}\n\n',
      'data: {"type":"done","stream_id":"s-9","run_id":"r-9","executed":true}\n\n',
    ]);
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("run it");
    const assistant = await screen.findByTestId("chat-assistant-message");
    const text = assistant.querySelector("p")?.textContent ?? "";
    expect(text).toContain("line one");
    expect(text).toContain("line two");
    expect(text.indexOf("\n")).toBeGreaterThanOrEqual(0);
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(screen.queryByTestId("approval-accept")).toBeNull();
    expect(screen.queryByTestId("approval-edit")).toBeNull();
    expect(screen.queryByTestId("approval-reject")).toBeNull();
  });
});
