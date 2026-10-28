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
import { FakeApiClient, HttpApiClient } from "../../api/client";
import { ENDPOINTS } from "../../api/endpoints";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { ChatArea } from "../index";

const ONLINE = Object.getOwnPropertyDescriptor(window.navigator, "onLine");

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale("en");
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

describe("channel locale policy and tags", () => {
  it("shows the channel locale policy and tags served in assistant deltas", async () => {
    const client = new FakeApiClient({
      chatDeltas: ["deploy ready #urgent #backend done"],
    });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(screen.queryByTestId("chat-channel-meta")).toBeNull();
    promptAndSend("hello");
    expect(await screen.findByTestId("chat-channel-meta")).toBeTruthy();
    expect(screen.getByTestId("chat-policy").textContent).toBe("en");
    expect(screen.getByTestId("chat-tags")).toBeTruthy();
    expect(screen.getByTestId("chat-tag-0").textContent).toBe("#urgent");
    expect(screen.getByTestId("chat-tag-1").textContent).toBe("#backend");
  });

  it("serves tags over the real stream route at the network boundary", async () => {
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      seen.push(String(url));
      return new Response(
        'data: {"stream_id":"s-pol","delta":"wire #live check","done":true}\n',
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
    expect(await screen.findByTestId("chat-tag-0")).toBeTruthy();
    expect(screen.getByTestId("chat-tag-0").textContent).toBe("#live");
    expect(seen).toContain(ENDPOINTS.chatStream);
  });

  it("follows the uk channel locale policy", async () => {
    setLocale("uk");
    const client = new FakeApiClient({
      chatDeltas: ["готово #терміново робота"],
    });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("привіт");
    expect(await screen.findByTestId("chat-channel-meta")).toBeTruthy();
    expect(screen.getByTestId("chat-policy").textContent).toBe("uk");
    expect(screen.getByTestId("chat-tag-0").textContent).toBe("#терміново");
  });

  it("hides channel meta when the served stream carries no tags", async () => {
    const client = new FakeApiClient({ chatDeltas: ["plain reply"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    await screen.findByTestId("approval-accept");
    await waitFor(() => {
      expect(screen.queryByTestId("chat-channel-meta")).toBeNull();
    });
    expect(t("chat.composer.send")).toBeTruthy();
  });
});
