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
// @ts-ignore: node types unavailable offline
import { readFileSync } from "node:fs";
// @ts-ignore: node types unavailable offline
import { fileURLToPath } from "node:url";

// S2 stylesheet source: jsdom never applies shell.css, so the meaning
// (composer in flow, messages own the scroll) is read from the file text.
function readShellCss(): string {
  try {
    return readFileSync(
      fileURLToPath(new URL("../../ui/shell.css", import.meta.url)),
      "utf8",
    );
  } catch {
    // Transformed import.meta.url is not file: here; tests run from frontend/.
    // @ts-ignore: node types unavailable offline
    return readFileSync("src/ui/shell.css", "utf8");
  }
}
const shellCss = readShellCss();

/** All stylesheet bodies for a selector (incl. prefixed child rules). */
function ruleBodies(css: string, selector: string): string[] {
  const bodies: string[] = [];
  let from = 0;
  for (;;) {
    const at = css.indexOf(selector, from);
    if (at === -1) {
      return bodies;
    }
    const open = css.indexOf("{", at);
    const close = open === -1 ? -1 : css.indexOf("}", open);
    if (open === -1 || close === -1) {
      return bodies;
    }
    bodies.push(css.slice(open + 1, close));
    from = close + 1;
  }
}

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
  it("keeps the composer in flow under the scrolling message list, never over it", async () => {
    const client = new FakeApiClient({ chatDeltas: ["x"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    const layout = await screen.findByTestId("chat-layout");
    const messages = screen.getByTestId("chat-messages");
    const composer = screen.getByTestId("chat-composer");
    // Composer follows the messages in DOM order (in flow, under them).
    expect(
      (messages.compareDocumentPosition(composer) &
        Node.DOCUMENT_POSITION_FOLLOWING) !==
        0,
    ).toBe(true);
    // No inline overlay override on the composer.
    expect(composer.style.position).not.toMatch(/sticky|fixed|absolute/);
    // Stylesheet meaning: no chat-composer rule parks it sticky/fixed/absolute.
    const composerBodies = ruleBodies(
      shellCss,
      'div[data-testid="chat-composer"]',
    );
    expect(composerBodies.length).toBeGreaterThan(0);
    for (const body of composerBodies) {
      expect(body).not.toMatch(/position\s*:\s*(sticky|fixed|absolute)/);
    }
    // Stylesheet meaning: the messages area owns the scroll; the layout
    // constrains the height so the composer stays below, never over text.
    const messageBodies = ruleBodies(
      shellCss,
      'div[data-testid="chat-messages"]',
    );
    expect(
      messageBodies.some((body) =>
        /overflow-y\s*:\s*(auto|scroll)/.test(body),
      ),
    ).toBe(true);
    // FXLOOK D2: the height cap moved from inline style to the
    // stylesheet (route column + lane cap), so the composer stays below
    // the scrolling lane instead of overlaying text.
    const layoutBodies = ruleBodies(shellCss, 'div[data-testid="chat-layout"]');
    expect(
      layoutBodies.some((body) =>
        /max-height\s*:\s*calc\(100vh - 200px\)/.test(body),
      ),
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
