/** @vitest-environment jsdom */
// FXRC1FIX P1+P3: assistant text keeps its line breaks (pre-wrap) and the
// message list scrolls inside the chat card with the composer below it,
// auto-scrolling to the newest message unless the user scrolled up.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
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

function promptAndSend(text: string): void {
  fireEvent.change(screen.getByTestId("chat-prompt"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByTestId("chat-send"));
}

describe("fxrc1fix P1 assistant text keeps line breaks", () => {
  it("renders status lines on their own lines via pre-wrap", async () => {
    const client = new FakeApiClient({
      chatDeltas: ["line1\n", "line2\nline3"],
    });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    const blocks = await screen.findAllByTestId("chat-assistant-message");
    expect(blocks).toHaveLength(1);
    const paragraph = blocks[0]?.querySelector("p");
    expect(paragraph?.textContent).toBe("line1\nline2\nline3");
    expect(paragraph?.style.whiteSpace).toBe("pre-wrap");
  });
});

describe("fxrc1fix P3 messages scroll inside the card", () => {
  it("keeps the composer below the scrolling message list", async () => {
    const client = new FakeApiClient({ chatDeltas: ["x"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    const layout = await screen.findByTestId("chat-layout");
    const messages = screen.getByTestId("chat-messages");
    const composer = screen.getByTestId("chat-composer");
    expect(layout.style.maxHeight).not.toBe("");
    expect(composer.style.position).toBe("static");
    expect(
      (messages.compareDocumentPosition(composer) &
        Node.DOCUMENT_POSITION_FOLLOWING) !==
        0,
    ).toBe(true);
  });

  it("auto-scrolls to newest unless the user scrolled up", async () => {
    const client = new FakeApiClient({ chatDeltas: ["new text"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    const messages = (await screen.findByTestId(
      "chat-messages",
    )) as HTMLElement;
    Object.defineProperty(messages, "scrollHeight", {
      value: 1000,
      configurable: true,
    });
    Object.defineProperty(messages, "clientHeight", {
      value: 200,
      configurable: true,
    });
    promptAndSend("first");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    expect(messages.scrollTop).toBe(1000);
    messages.scrollTop = 100;
    fireEvent.scroll(messages);
    promptAndSend("second");
    await screen.findAllByTestId("chat-assistant-message");
    expect(messages.scrollTop).toBe(100);
  });
});
