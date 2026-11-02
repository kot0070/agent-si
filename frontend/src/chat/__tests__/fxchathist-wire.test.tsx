/** @vitest-environment jsdom */
// FXCHATHIST Part 2 wiring: H1 survival, H2 history load, H3 entry
// points, H4 verdict plus quiet dot, S5 single card plus transient toast.
// FakeApiClient fakes only the provider/stream boundary; history flows
// through stubbed fetch shaped like the served route.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import {
  ApiClientProvider,
} from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { HttpApiClient } from "../../api/client";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea, hasChatUnseen } from "../index";
import { Sidebar } from "../../shell/Sidebar";
import { ProjectsPage } from "../../projects/ProjectsPage";
import { ProjectView } from "../../projects/ProjectView";
import { App } from "../../app/App";

const ONLINE = Object.getOwnPropertyDescriptor(window.navigator, "onLine");

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  resetChatStore();
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

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function historyTurns() {
  return {
    turns: [
      {
        project_id: "p-1",
        user_text: "older question",
        assistant_text: "older answer",
        time: "2026-01-01T00:00:00Z",
      },
    ],
  };
}

function stubHistoryFetch(): void {
  vi.stubGlobal("fetch", async (url: unknown) => {
    const target = String(url);
    if (target.startsWith("/api/v1/chat/history")) {
      if (target.includes("project_id=")) {
        return jsonBody(historyTurns());
      }
      return jsonBody({ turns: [] });
    }
    if (target.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: "p-1", models: [] });
    }
    if (target === "/api/v1/providers") {
      return jsonBody({ providers: [] });
    }
    throw new Error(`unexpected fetch to ${target}`);
  });
}

function renderAppAt(route: string, client?: FakeApiClient): void {
  const api = client ?? new FakeApiClient({});
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={api}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe("H1 messages plus the live runner survive page changes", () => {
  it("keeps a completed run across unmount without cancelling", async () => {
    const client = new FakeApiClient({ chatDeltas: ["Hel", "lo"] });
    const cancelled = vi.spyOn(client, "cancelChatStream");
    const first = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    expect(await screen.findByText("hello")).toBeTruthy();
    first.unmount();
    expect(cancelled).not.toHaveBeenCalled();
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText("hello")).toBeTruthy();
    const assistants = await screen.findAllByTestId("chat-assistant-message");
    expect(assistants).toHaveLength(1);
    expect(assistants[0]?.textContent).toContain("Hello");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    expect(cancelled).not.toHaveBeenCalled();
  });

  it("does not abort a live stream on unmount and shows it on return", async () => {
    const cancelled: string[] = [];
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(entry) {
        controller = entry;
      },
    });
    vi.stubGlobal("fetch", async (url: unknown) => {
      const target = String(url);
      if (target.includes("/api/v1/chat/cancel")) {
        cancelled.push(target);
        return jsonBody({ ok: true });
      }
      if (target.includes("/api/v1/chat/stream")) {
        return new Response(body, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        });
      }
      if (target.startsWith("/api/v1/chat/history")) {
        return jsonBody({ turns: [] });
      }
      if (target.startsWith("/api/v1/chat/models")) {
        return jsonBody({ project_id: "p-1", models: [] });
      }
      if (target === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      throw new Error(`unexpected fetch to ${target}`);
    });
    const encoder = new TextEncoder();
    function sseLine(event: string): Uint8Array {
      return encoder.encode(`${event}\n`);
    }
    const client = new HttpApiClient();
    const first = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    await act(async () => {
      controller.enqueue(
        sseLine(
          'data: {"type":"start","stream_id":"srv-1","run_id":"r-1"}',
        ),
      );
      controller.enqueue(
        sseLine(
          'data: {"type":"delta","stream_id":"srv-1","run_id":"r-1","text":"Hel"}',
        ),
      );
    });
    expect(await screen.findByText("Hel")).toBeTruthy();
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    first.unmount();
    // H1: unmount never aborts the live run.
    expect(cancelled).toHaveLength(0);
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    // Coming back shows everything so far, still streaming.
    expect(await screen.findByText("Hel")).toBeTruthy();
    expect(await screen.findByText("hello")).toBeTruthy();
    expect(await screen.findByTestId("chat-spinner")).toBeTruthy();
    expect(cancelled).toHaveLength(0);
    await act(async () => {
      controller.enqueue(
        sseLine(
          'data: {"type":"delta","stream_id":"srv-1","run_id":"r-1","text":"lo"}',
        ),
      );
      controller.enqueue(
        sseLine('data: {"type":"done","stream_id":"srv-1","run_id":"r-1"}'),
      );
      controller.close();
    });
    // The live pump kept driving the store across the unmount: the full
    // answer plus the verdict card land on the remounted chat (the text
    // repeats in the message and its card).
    const hellos = await screen.findAllByText("Hello");
    expect(hellos.length).toBeGreaterThanOrEqual(2);
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    expect(cancelled).toHaveLength(0);
  });
});

describe("H2 history loads from the served route on project open", () => {
  it("renders served turns on open", async () => {
    stubHistoryFetch();
    render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText("older question")).toBeTruthy();
    // History never marks a proposal: the served answer renders once,
    // with no verdict card.
    const answers = await screen.findAllByText("older answer");
    expect(answers).toHaveLength(1);
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });

  it("restores history for a fresh session (restart persistence)", async () => {
    stubHistoryFetch();
    const first = render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText("older question")).toBeTruthy();
    first.unmount();
    // A restart wipes the module store and starts a fresh client slice;
    // the served route is the durability behind the remount.
    resetChatStore();
    render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText("older question")).toBeTruthy();
    const answers = await screen.findAllByText("older answer");
    expect(answers).toHaveLength(1);
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });
});

describe("H4 verdict stored with chat, quiet dot until opened", () => {
  function stubFailingStream(): {
    releaseError: () => Promise<void>;
    cancelled: string[];
  } {
    let release!: (response: Response) => void;
    const gate = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const cancelled: string[] = [];
    vi.stubGlobal("fetch", async (url: unknown) => {
      const target = String(url);
      if (target.includes("/api/v1/chat/cancel")) {
        cancelled.push(target);
        return jsonBody({ ok: true });
      }
      if (target.includes("/api/v1/chat/stream")) {
        return gate;
      }
      if (target.startsWith("/api/v1/chat/history")) {
        return jsonBody({ turns: [] });
      }
      if (target.startsWith("/api/v1/chat/models")) {
        return jsonBody({ project_id: "p-1", models: [] });
      }
      if (target === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (target === "/api/v1/projects") {
        return jsonBody({
          projects: [{ project_id: "p-1", name: "n-1", created_at: "t-0" }],
        });
      }
      throw new Error(`unexpected fetch to ${target}`);
    });
    return {
      cancelled,
      releaseError: async () => {
        await act(async () => {
          release(
            new Response(
              'data: {"type":"start","stream_id":"srv-e","run_id":"r-e"}\n\n' +
                'data: {"type":"error","stream_id":"srv-e","run_id":"r-e","code":"BUDGET_CAPPED","message":"wire"}\n\n',
              {
                status: 200,
                headers: { "content-type": "text/event-stream" },
              },
            ),
          );
        });
      },
    };
  }

  it("stores the verdict and dots the project row until the chat opens", async () => {
    const client = new HttpApiClient();
    const stream = stubFailingStream();
    const first = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    // Leave while live: the verdict lands while nobody shows the chat.
    first.unmount();
    await stream.releaseError();
    // The verdict line is stored with the chat (single error card waits).
    expect(hasChatUnseen(client, "p-1")).toBe(true);
    const rowsRouter = createMemoryRouter(
      [
        {
          path: "/",
          element: (
            <>
              <Sidebar projectId="p-1" />
              <ProjectsPage />
            </>
          ),
        },
      ],
      { initialEntries: ["/"] },
    );
    render(
      <ApiClientProvider client={client}>
        <RouterProvider router={rowsRouter} />
      </ApiClientProvider>,
    );
    // Sidebar plus ProjectsPage rows each carry the quiet dot.
    const dots = await screen.findAllByTestId("project-chat-dot-p-1");
    expect(dots).toHaveLength(2);
    // Opening the chat clears the dot; the single error line shows.
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    const lines = await screen.findAllByTestId("chat-error-line");
    expect(lines).toHaveLength(1);
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    expect(screen.queryByTestId("chat-health-degraded")).toBeNull();
    expect(document.body.textContent).not.toContain("UNKNOWN");
    await waitFor(() => {
      expect(screen.queryByTestId("project-chat-dot-p-1")).toBeNull();
    });
    expect(stream.cancelled).toHaveLength(0);
  });

  it("sets no dot when the run finishes in front of the user", async () => {
    const client = new FakeApiClient({ chatDeltas: ["ok"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("hello");
    expect(await screen.findByTestId("approval-accept")).toBeTruthy();
    expect(hasChatUnseen(client, "p-1")).toBe(false);
  });
});

describe("H3 every entry point opens that project's chat", () => {
  it("opens the chat tab from the Sidebar project row", async () => {
    renderAppAt("/projects");
    fireEvent.click(await screen.findByTestId("project-open-p-1"));
    expect(await screen.findByTestId("chat-area")).toBeTruthy();
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    expect(
      (screen.getByTestId("topbar-project") as HTMLSelectElement).value,
    ).toBe("p-1");
  });

  it("opens the selected project's chat from the TopBar switch", async () => {
    renderAppAt(
      "/",
      new FakeApiClient({
        projects: [
          { project_id: "p-1", name: "n-1", created_at: "t-0" },
          { project_id: "p-2", name: "n-2", created_at: "t-0" },
        ],
      }),
    );
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
    // Let the auto-select settle on p-1 first: the mount-time project
    // list resolves after the first paint and would otherwise overwrite
    // the manual switch below (stale select wins the race).
    await waitFor(() => {
      expect(
        (screen.getByTestId("topbar-project") as HTMLSelectElement).value,
      ).toBe("p-1");
    });
    fireEvent.change(screen.getByTestId("topbar-project"), {
      target: { value: "p-2" },
    });
    expect(await screen.findByTestId("chat-area")).toBeTruthy();
    expect(
      (screen.getByTestId("topbar-project") as HTMLSelectElement).value,
    ).toBe("p-2");
  });

  it("renders Chat as the first project tab and navigates to the chat", async () => {
    renderAppAt("/projects/p-1/overview");
    const tabs = await screen.findByRole("navigation", {
      name: t("projectView.tabsLabel"),
    });
    const buttons = within(tabs).getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    expect(buttons[0]?.getAttribute("data-testid")).toBe("project-chat-tab");
    fireEvent.click(screen.getByTestId("project-chat-tab"));
    expect(await screen.findByTestId("chat-area")).toBeTruthy();
    expect(await screen.findByTestId("chat-prompt")).toBeTruthy();
  });

  it("keeps the chat tab operable without a select callback", async () => {
    render(
      <ApiClientProvider client={new FakeApiClient({})}>
        <ProjectView projectId="p-1" view="overview" />
      </ApiClientProvider>,
    );
    const tab = await screen.findByTestId("project-chat-tab");
    expect(tab.textContent).toBe(t("shell.sidebar.chat"));
    fireEvent.click(tab);
    expect(screen.getByTestId("project-chat-tab")).toBeTruthy();
  });
});

describe("S5 single card, quiet no-provider line, transient toast", () => {
  it("shows one error card, one quiet line with a Connect action", async () => {
    stubHistoryFetch();
    const client = new FakeApiClient({});
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    const hint = await screen.findByTestId("chat-no-model-hint");
    expect(hint.textContent).toBe(t("chat.composer.noModel"));
    const connect = await screen.findByTestId("chat-no-model-connect");
    expect(connect.textContent).toBe(t("chat.hierarchy.connect"));
    expect(connect.getAttribute("href")).toBe("/settings/models");
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    const statusline = await screen.findByTestId("chat-statusline");
    // S5 bound single label: exactly the three locale value spans.
    expect(statusline.querySelectorAll(":scope > span")).toHaveLength(3);
  });

  it("toasts offline queues transiently", async () => {
    Object.defineProperty(window.navigator, "onLine", {
      value: false,
      configurable: true,
    });
    const client = new FakeApiClient({ chatDeltas: ["back"] });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("chat-offline-dot")).toBeTruthy();
    promptAndSend("queued hello");
    expect(await screen.findByTestId("chat-toast")).toBeTruthy();
    // Transient: the toast clears by itself without another send.
    await waitFor(
      () => {
        expect(screen.queryByTestId("chat-toast")).toBeNull();
      },
      { timeout: 7000 },
    );
  }, 15000);
});

describe("engine run verdict: log lines once, no card, time-only stamp", () => {
  function stubDevrunFetch(): void {
    vi.stubGlobal("fetch", async (url: unknown) => {
      const target = String(url);
      if (target.startsWith("/api/v1/chat/history")) {
        return jsonBody({ turns: [] });
      }
      if (target.startsWith("/api/v1/chat/models")) {
        return jsonBody({ project_id: "p-1", models: [] });
      }
      if (target === "/api/v1/providers") {
        return jsonBody({ providers: [] });
      }
      if (target.includes("/api/v1/chat/stream")) {
        return new Response(
          [
            'data: {"type":"start","stream_id":"srv-d","run_id":"r-d"}',
            'data: {"type":"delta","stream_id":"srv-d","run_id":"r-d","text":"Director: plan of 2 parts\\n"}',
            'data: {"type":"delta","stream_id":"srv-d","run_id":"r-d","text":"Total: 10 input + 5 output = 15 tokens\\n"}',
            'data: {"type":"delta","stream_id":"srv-d","run_id":"r-d","text":"run success: all 2 parts PASS"}',
            'data: {"type":"done","stream_id":"srv-d","run_id":"r-d","text":"run success: all 2 parts PASS"}',
            "",
          ].join("\n"),
          {
            status: 200,
            headers: { "content-type": "text/event-stream" },
          },
        );
      }
      throw new Error(`unexpected fetch to ${target}`);
    });
  }

  it("renders the engine verdict first with the log behind a toggle", async () => {
    stubDevrunFetch();
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <ChatArea projectId="p-1" />
      </ApiClientProvider>,
    );
    promptAndSend("run it");
    // The verdict line comes first...
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).toContain("Done");
    // ...the log lines stay in the DOM behind the toggle, unchanged.
    const toggle = await screen.findByTestId("run-steps-toggle");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByText(/Director: plan of 2 parts/)).toBeTruthy();
    expect(screen.getByText(/Total: 10 input/)).toBeTruthy();
    expect(screen.getByText(/run success: all 2 parts PASS/)).toBeTruthy();
    expect(screen.getByTestId("run-steps").hasAttribute("hidden")).toBe(true);
    // No verdict card for the engine run: no accept/edit/reject.
    await waitFor(() => {
      expect(screen.queryByTestId("chat-spinner")).toBeNull();
    });
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(screen.queryByTestId("approval-accept")).toBeNull();
    expect(screen.queryByTestId("approval-edit")).toBeNull();
    expect(screen.queryByTestId("approval-reject")).toBeNull();
    expect(screen.queryByTestId("kit-error-panel")).toBeNull();
    // Bubbles carry time only, never the date.
    const stamps = await screen.findAllByTestId("chat-timestamp");
    expect(stamps.length).toBeGreaterThan(0);
    for (const stamp of stamps) {
      const label = stamp.textContent ?? "";
      expect(label).toMatch(/\d{1,2}:\d{2}/);
      expect(label).not.toMatch(/2026|2025|\//);
    }
  });
});
