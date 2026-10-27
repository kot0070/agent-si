/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/client";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { compactPrompt } from "../chatApi";
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

async function awaitCompletions(count: number): Promise<void> {
  await waitFor(() => {
    expect(screen.getAllByTestId("approval-accept")).toHaveLength(count);
  });
}

describe("flooding warning and compact re-issue", () => {
  it("warns after rapid prompts and re-issues a compacted prompt", async () => {
    const client = new FakeApiClient({ chatDeltas: ["ok"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(screen.queryByTestId("chat-flood-warning")).toBeNull();
    promptAndSend("alpha one");
    await awaitCompletions(1);
    expect(screen.queryByTestId("chat-flood-warning")).toBeNull();
    promptAndSend("beta two");
    await awaitCompletions(2);
    promptAndSend("gamma three");
    await awaitCompletions(3);
    const longPrompt = `delta ${"extra padding ".repeat(12)}end`;
    promptAndSend(longPrompt);
    await awaitCompletions(4);
    const warning = await screen.findByTestId("chat-flood-warning");
    expect(warning.textContent).toContain(t("api.error.delta_over_bound"));
    const resend = await screen.findByTestId("chat-compact-resend");
    expect(resend.textContent).toBe(t("ui.error.retry"));
    const compacted = compactPrompt(longPrompt);
    expect(compacted.length).toBeLessThan(longPrompt.length);
    fireEvent.click(resend);
    expect(await screen.findByText(compacted)).toBeTruthy();
    await awaitCompletions(5);
    await waitFor(() => {
      expect(screen.queryByTestId("chat-flood-warning")).toBeNull();
    });
  });

  it("compacts whitespace runs through the shared helper", () => {
    expect(compactPrompt("  a   b\nc  ")).toBe("a b c");
    expect(compactPrompt("x")).toBe("x");
  });
});
