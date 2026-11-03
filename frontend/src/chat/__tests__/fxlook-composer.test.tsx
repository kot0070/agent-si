/** @vitest-environment jsdom */
// FXLOOK D2 RED: the chat route is a bounded column — head on top, the
// stream lane takes the free space and is the ONLY scroller, composer
// pinned last. Hierarchy folds into the composer tray (one line); the
// empty sentence + 2 suggestions sit right above the composer.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea } from "../index";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubBoundary(): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.startsWith("/api/v1/chat/history") && method === "GET") {
      return jsonBody({ turns: [] });
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: "p-d2", models: [] });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [] });
    }
    if (url.startsWith("/api/v1/routing/role")) {
      return jsonBody({ code: "ROLE_MISSING" }, 404);
    }
    if (url.startsWith("/api/v1/roles/chat-model")) {
      return jsonBody({ project_id: "p-d2", model_id: null });
    }
    return jsonBody({ code: "D2_UNEXPECTED" }, 404);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
});

describe("FXLOOK D2 composer-always-on-screen column", () => {
  it("stream takes free space, composer is last in the layout lane", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-d2" />
      </ApiClientProvider>,
    );
    const layout = await screen.findByTestId("chat-layout");
    const messages = within(layout).getByTestId("chat-messages");
    const composer = within(layout).getByTestId("chat-composer");
    // Composer is the last lane child: pinned to the column bottom.
    expect(
      messages.compareDocumentPosition(composer) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(layout.lastElementChild?.getAttribute("data-testid")).toBe(
      "chat-composer",
    );
    // The message lane is the scroller (CSS guard).
    // @ts-ignore: node fs available offline in this repo's tests
    const { readFileSync } = require("node:fs");
    const css: string = readFileSync("src/ui/shell.css", "utf8");
    const laneBlocks =
      css.match(/div\[data-testid="chat-messages"\]\s*\{[^}]*\}/g) ?? [];
    expect(
      laneBlocks.some((block) => /overflow-y:\s*auto/.test(block)),
    ).toBe(true);
    // The route column bounds the whole route (CSS guard).
    expect(css).toMatch(
      /\.fx-chat-route\s*\{[^}]*height:\s*calc\(100vh - 190px\)/,
    );
  });

  it("hierarchy folds into the composer tray, single line", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-d2" />
      </ApiClientProvider>,
    );
    const composer = await screen.findByTestId("chat-composer");
    const tray = within(composer).getByTestId("chat-tray");
    expect(
      within(tray).getByTestId("hierarchy-collapsed"),
    ).toBeTruthy();
    // @ts-ignore: node fs available offline in this repo's tests
    const { readFileSync } = require("node:fs");
    const css: string = readFileSync("src/ui/shell.css", "utf8");
    const trayBlock =
      /\.fx-composer-tray button\[data-testid="hierarchy-collapsed"\]\s*\{([^}]*)\}/
        .exec(css)?.[1] ?? "";
    expect(trayBlock).toMatch(/white-space:\s*nowrap/);
    expect(trayBlock).toMatch(/text-overflow:\s*ellipsis/);
  });

  it("empty sentence + 2 suggestions sit right above the composer", async () => {
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-d2" />
      </ApiClientProvider>,
    );
    const layout = await screen.findByTestId("chat-layout");
    const empty = within(layout).getByTestId("chat-empty-state");
    const composer = within(layout).getByTestId("chat-composer");
    expect(
      empty.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      within(empty).getByTestId("chat-sample-1"),
    ).toBeTruthy();
    expect(
      within(empty).getByTestId("chat-sample-2"),
    ).toBeTruthy();
    // Nothing between the empty block and the composer but quiet meta.
    let node: Element | null = empty.nextElementSibling;
    while (node !== null && node !== composer) {
      expect(node.getAttribute("data-testid")).not.toBe("chat-layout");
      node = node.nextElementSibling;
    }
    expect(node).toBe(composer);
  });
});
