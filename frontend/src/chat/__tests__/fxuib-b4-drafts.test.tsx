/** @vitest-environment jsdom */
// FXUIB-B4: the chat draft survives page change/remount on the same
// client (kept in the chat store per slice, cleared on send).
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("FXUIB-B4 chat draft kept per slice", () => {
  it("type, remount, text is there; send clears it", async () => {
    const client = new FakeApiClient({ chatDeltas: ["hi"] });
    const ui = (
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>
    );
    const first = render(ui);
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "draft text" },
    });
    expect(
      (screen.getByTestId("chat-prompt") as HTMLInputElement).value,
    ).toBe("draft text");
    first.unmount();
    render(ui);
    expect(
      (screen.getByTestId("chat-prompt") as HTMLInputElement).value,
    ).toBe("draft text");
    fireEvent.click(screen.getByTestId("chat-send"));
    expect(
      await screen.findByText("draft text"),
    ).toBeTruthy();
    expect(
      (screen.getByTestId("chat-prompt") as HTMLInputElement).value,
    ).toBe("");
  });
});
