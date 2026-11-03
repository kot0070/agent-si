/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { apiErrorLocaleKey } from "../../api/errors";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { ChatArea } from "../index";
import { ProvidersPage } from "../../settings/ProvidersPage/ProvidersPage";

function errorSse(code: string, providerId: string): Response {
  const body =
    `data: ${JSON.stringify({ type: "error", stream_id: "s-1", run_id: "r-1", code, provider_id: providerId, message: "engine text must not show" })}\n\n`;
  return new Response(body, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

function stubChatError(code: string, providerId: string): void {
  vi.stubGlobal("fetch", async (url: unknown) => {
    const target = String(url);
    if (target.includes("/api/v1/chat/stream")) {
      return errorSse(code, providerId);
    }
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
}

function stubEmptyProviders(): void {
  vi.stubGlobal("fetch", async (url: unknown) => {
    const target = String(url);
    if (target === "/api/v1/providers") {
      return new Response(JSON.stringify({ providers: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    if (target === "/api/v1/local/models") {
      return new Response(JSON.stringify({ models: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
}

function promptAndSend(text: string): void {
  fireEvent.change(screen.getByTestId("chat-prompt"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByTestId("chat-send"));
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

describe("fxstore missing key line", () => {
  it("maps the missing-key code to the chat line key", () => {
    expect(apiErrorLocaleKey("SECRET_VALUE_MISSING")).toBe(
      "chat.error.keyMissing",
    );
    expect(apiErrorLocaleKey("CREDENTIAL_STORE_UNREADABLE")).toBe(
      "chat.error.storeUnreadable",
    );
  });

  it("names the key and links Settings in English", async () => {
    setLocale("en");
    stubChatError("SECRET_VALUE_MISSING", "meta");
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello again");
    const line = await screen.findByTestId("chat-error-line");
    expect(line.textContent).toContain(
      "The key for Meta is not available. Connect it again.",
    );
    expect(line.textContent).not.toContain("engine text must not show");
    expect(line.textContent).not.toContain("AdapterConfigError");
    const connect = screen.getByTestId("kit-error-connect");
    expect(connect.getAttribute("href")).toBe("/settings/models");
    expect(screen.queryByTestId("chat-toast")).toBeNull();
  });

  it("names the key and links Settings in Ukrainian", async () => {
    setLocale("uk");
    stubChatError("SECRET_VALUE_MISSING", "meta");
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("привіт ще раз");
    const line = await screen.findByTestId("chat-error-line");
    expect(line.textContent).toContain(
      "Ключ для Meta недоступний. Під'єднайте його знову.",
    );
    expect(line.textContent).not.toContain("engine text must not show");
    const connect = screen.getByTestId("kit-error-connect");
    expect(connect.getAttribute("href")).toBe("/settings/models");
  });

  it("says the store cannot be read, never a missing key", async () => {
    setLocale("en");
    stubChatError("CREDENTIAL_STORE_UNREADABLE", "meta");
    const client = new HttpApiClient();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello store");
    const line = await screen.findByTestId("chat-error-line");
    expect(line.textContent).toContain(
      t("chat.error.storeUnreadable"),
    );
    expect(line.textContent).not.toContain("not available");
  });
});

describe("fxstore provider card with a gone value", () => {
  it("shows Connect, not Disconnect, when the served list drops the provider", async () => {
    setLocale("en");
    stubEmptyProviders();
    render(<ProvidersPage project_id="local" />);
    expect(await screen.findByLabelText("Connect Meta")).toBeTruthy();
    expect(screen.queryByLabelText("Disconnect Meta")).toBeNull();
  });
});
