/** @vitest-environment jsdom */
// FXUIB-B5: the closing guard arms while a chat stream runs. Real App,
// fetch mocked at the network only; the stream POST hangs, then
// beforeunload must be prevented (the existing window-closed wording
// names the reason).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { HttpApiClient } from "../../api/client";
import { ApiClientProvider } from "../ApiClientProvider";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { resetChatStore } from "../../chat/chatStore";
import { App } from "../App";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(): void {
  vi.stubGlobal(
    "fetch",
    async (input: unknown, init?: RequestInit): Promise<Response> => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "GET" && url === "/api/v1/projects") {
        return jsonBody({
          projects: [{ project_id: "p1", name: "P1", created_at: "t-0" }],
        });
      }
      if (method === "GET" && url === "/api/v1/projects/p1") {
        return jsonBody({ project: { project_id: "p1", name: "P1" } });
      }
      if (method === "GET" && url.startsWith("/api/v1/chat/models")) {
        return jsonBody({
          project_id: "p1",
          models: [{ provider_id: "openai", model: "openai/gpt-4o-mini" }],
        });
      }
      if (method === "POST" && url === "/api/v1/chat/stream") {
        return new Promise<Response>(() => undefined);
      }
      return jsonBody({ code: "FXUIB5_UNEXPECTED_API" }, 404);
    },
  );
}

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function fireBeforeUnload(): boolean {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  resetChatStore();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem("agentsi.firstrun.done", "true");
  stubFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("FXUIB-B5 closing guard arms during a stream", () => {
  it("beforeunload passes idle, is prevented while streaming", async () => {
    renderAppAt("/");
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    // The project list loads async and the StartBox reuses the prompt
    // testids: wait for the real ChatArea textarea, not the StartBox
    // input, before typing.
    await waitFor(() => {
      expect(
        document.querySelector("textarea[data-testid='chat-prompt']"),
      ).not.toBeNull();
    });
    expect(fireBeforeUnload()).toBe(false);
    fireEvent.change(screen.getByTestId("chat-prompt"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByTestId("chat-send"));
    await waitFor(() => {
      expect(fireBeforeUnload()).toBe(true);
    });
  });
});
