/** @vitest-environment jsdom */
// FXB1 focused behaviour proofs: R05 history text, A2 Connect link,
// B1 capability labels, B2 diagnostics masking, D4 resolved strings.
// Each case fails on the pre-fix tree (RED first, then GREEN).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import en from "../../locale/en.json";
import { resetChatStore } from "../chatStore";
import { ChatArea, EngineTurnView } from "../index";
import { humanFieldName } from "../../k07next2/KbRefreshProposal";
import { maskLogDir } from "../../settings/DiagnosticsSection";
import { HOW_IT_WORKS_KEYS, HowItWorks } from "../../app/HowItWorks";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

let historyTurns: unknown[];

function stubBoundary(): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.startsWith("/api/v1/chat/history") && method === "GET") {
      return jsonBody({ turns: historyTurns });
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: "p-fxb1", models: [] });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({ providers: [] });
    }
    return jsonBody({ code: "FXB1_UNEXPECTED_API" }, 404);
  });
}

function failedTurn(errorCode: string): unknown {
  return {
    project_id: "p-fxb1",
    user_text: "do the thing",
    assistant_text: "partial",
    time: "2026-01-01T00:00:00Z",
    id: `t-${errorCode}`,
    status: "failed",
    run_id: `run-${errorCode}`,
    error_code: errorCode,
    executed: false,
    run_end_reason: "",
  };
}

function renderChat(): void {
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <ChatArea projectId="p-fxb1" />
    </ApiClientProvider>,
  );
}

function normalizedText(content: string | null): string {
  return (content ?? "").replace(/\s+/g, " ").trim();
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
  historyTurns = [];
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("FXB1 R05 history text", () => {
  it("plain output opens on the assistant text, never a bare verdict", async () => {
    render(
      <EngineTurnView text={"log line 1\nlog line 2"} status="ok" />,
    );
    const toggle = await screen.findByTestId("run-steps-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("run-steps").hasAttribute("hidden")).toBe(false);
    expect(normalizedText(await screen.findByTestId("run-verdict").then(
      (el) => el.textContent,
    ))).toContain("Nothing was built");
  });

  it("engine logs stay collapsed behind Details", async () => {
    render(
      <EngineTurnView
        text={"Part p1: PASS\nrun success: all 1 parts PASS"}
        status="ok"
      />,
    );
    const toggle = await screen.findByTestId("run-steps-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByTestId("run-steps").hasAttribute("hidden")).toBe(true);
  });

  it("rendered text and textContent agree for plain output", async () => {
    const { container } = render(
      <EngineTurnView text={"log line 1\nlog line 2"} status="ok" />,
    );
    expect(normalizedText(container.textContent)).toBe(
      "Nothing was built — the plan had no parts. Say what you want built, for example: “Add a contact page with a test.”. " +
        "Details log line 1 log line 2",
    );
  });
});

describe("FXB1 A2 Connect link", () => {
  it("no-provider notice carries Connect next to Retry", async () => {
    historyTurns = [failedTurn("NO_PROVIDER_BOUND")];
    renderChat();
    const connect = await screen.findByTestId("kit-error-connect");
    expect(connect.getAttribute("href")).toBe("/settings/models");
    expect(connect.textContent).toBe(en.chat.hierarchy.connect);
    expect(await screen.findByTestId("kit-error-retry")).toBeTruthy();
  });

  it("other errors carry no Connect link", async () => {
    historyTurns = [failedTurn("BUDGET_CAPPED")];
    renderChat();
    expect(await screen.findByTestId("kit-error-retry")).toBeTruthy();
    expect(screen.queryByTestId("kit-error-connect")).toBeNull();
  });
});

describe("FXB1 B1 capability labels", () => {
  it("served snake_case facts map to human labels", () => {
    expect(humanFieldName("total_changes")).toBe("Total changes");
    expect(humanFieldName("last_source")).toBe("Last source");
    expect(humanFieldName("models")).toBe("Models");
    expect(humanFieldName("last_change_at")).toBe("Last change");
    expect(humanFieldName("overall")).toBe("overall");
    expect(humanFieldName("kb_version")).toBe("Version");
    expect(humanFieldName("updated_at")).toBe("Updated");
    expect(humanFieldName("per_provider")).toBe("Per provider");
  });
});

describe("FXB1 B2 diagnostics masking", () => {
  it("masks the user profile segment and keeps the rest", () => {
    expect(maskLogDir("C:\\Users\\PC IA\\AppData\\logs")).toBe(
      "C:\\Users\\…\\AppData\\logs",
    );
    expect(maskLogDir("D:\\agent\\data\\logs")).toBe("D:\\agent\\data\\logs");
  });
});

describe("FXB1 D4 resolved strings", () => {
  it("concepts show resolved strings, never raw keys", () => {
    const { container } = render(<HowItWorks />);
    expect(container.textContent).toContain(en.howItWorks.runs.title);
    expect(container.textContent).toContain(en.howItWorks.runs.body);
    expect(container.textContent).toContain(en.howItWorks.codeTests.body);
    expect(container.textContent).toContain(en.howItWorks.localTests.body);
    for (const key of Object.values(HOW_IT_WORKS_KEYS)) {
      expect(container.textContent).not.toContain(key);
    }
  });
});
