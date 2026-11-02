/** @vitest-environment jsdom */
// FXCHATV RED-first: chat reply a juror can read (laptop RC5-B photos).
// V1 one reply (verdict + Details, never twice); V2 card gating per state;
// V3 live permission ask within 1s incl. slice-key change; V4 live step
// line while working; V5 plain layer without raw words; (a) no raw code or
// generic line; (b) single Connect CTA; (c) status blocked, never Ready
// with no provider; (d) check lines name the program only.
// FAKE seam only at fetch (SSE bytes + JSON), the page is real.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { HttpApiClient } from "../../api/client";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { resetChatStore } from "../chatStore";
import { ChatArea } from "../index";

const HOLD_TOOL = "install:PV-a:python";
const HOLD_PROJECT = "PV-a";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function sse(lines: string[]): Response {
  return new Response(lines.join("\n"), {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

let historyTurns: unknown[];
let streamReplies: (() => Response)[];
let boundModels: unknown[] | null;
let connectedProviders: string[];

const seenPosts: { url: string; body: unknown }[] = [];

function stubBoundary(): void {
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.startsWith("/api/v1/chat/history")) {
      if (method === "POST") {
        return jsonBody({ ok: true });
      }
      return jsonBody({ turns: historyTurns });
    }
    if (url.includes("/api/v1/chat/stream") && method === "POST") {
      const reply = streamReplies.shift();
      if (reply === undefined) {
        throw new Error("no stubbed stream reply left");
      }
      return reply();
    }
    if (url.startsWith("/api/v1/chat/models")) {
      return jsonBody({ project_id: "x", models: boundModels ?? [] });
    }
    if (url === "/api/v1/providers") {
      return jsonBody({
        providers: connectedProviders.map((provider_id) => ({ provider_id })),
      });
    }
    if (url.startsWith("/api/v1/routing/role")) {
      return jsonBody({ error: "missing" }, 404);
    }
    if (url.startsWith("/api/v1/permissions/install-request")) {
      return jsonBody({ error: "missing" }, 404);
    }
    if (url === "/api/v1/permissions/check" && method === "POST") {
      return jsonBody({ allowed: true, asked_once: false });
    }
    if (url === "/api/v1/permissions/decide" && method === "POST") {
      let body: unknown = null;
      try {
        body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
      } catch {
        body = null;
      }
      seenPosts.push({ url, body });
      return jsonBody({ ok: true });
    }
    if (url === "/api/v1/chat/decision" && method === "POST") {
      return jsonBody({ ok: true });
    }
    if (url.includes("/api/v1/chat/cancel")) {
      return jsonBody({ ok: true });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
  resetChatStore();
  historyTurns = [];
  streamReplies = [];
  boundModels = [];
  connectedProviders = [];
  seenPosts.length = 0;
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

function renderChat(
  projectId: string,
  opts?: { initialSend?: string; client?: HttpApiClient },
): void {
  render(
    <ApiClientProvider client={opts?.client ?? new HttpApiClient()}>
      <ChatArea
        projectId={projectId}
        initialSend={opts?.initialSend}
      />
    </ApiClientProvider>,
  );
}

function send(text: string): void {
  fireEvent.change(screen.getByTestId("chat-prompt"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByTestId("chat-send"));
}

const PHOTO_LOG = [
  "Working folder: D:\\Test2\\app\\data\\workspaces\\abc123",
  "Team: director, manager, worker, auditor on meta/muse-spark-1.3-contributor (Auto: cheapest known price among connected providers)",
  "Director: plan of 1 parts",
  "Part p1: Create file hello.txt with the text hello [files: hello.txt]",
  "Part p1: attempt 1",
  "Check p1 $ C:\\Windows\\system32\\findstr.EXE hello hello.txt -> exit 0",
  "Auditor for p1: PASS (hello.txt created with content 'hello')",
  "Part p1: PASS (checks green, auditor PASS)",
  "Total: 931 input + 3595 output = 4526 tokens; cost: UNKNOWN",
  "Run dir: C:\\Users\\Owner\\work",
  "run success: all 1 parts PASS",
].join("\n");

function approvalStream(): Response {
  return sse([
    `data: {"type":"start","stream_id":"srv-ask","run_id":"r-ask"}`,
    `data: {"type":"approval","stream_id":"srv-ask","run_id":"r-ask","tool_id":"${HOLD_TOOL}","reason":"run held: install permission needed"}`,
    "",
  ]);
}

describe("V1 one reply: verdict plus Details, never twice", () => {
  it("run-log done without an executed flag renders verdict plus Details, no card", async () => {
    streamReplies.push(() =>
      sse([
        `data: {"type":"start","stream_id":"srv-1","run_id":"r-1"}`,
        `data: {"type":"delta","stream_id":"srv-1","run_id":"r-1","text":${JSON.stringify(PHOTO_LOG)}}`,
        `data: {"type":"done","stream_id":"srv-1","run_id":"r-1","text":${JSON.stringify(PHOTO_LOG)},"output_ref":"artifact:run/r-1/output"}`,
        "",
      ]),
    );
    renderChat("PV-log");
    send("create hello");
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).toContain("Done");
    expect(verdict.textContent).toContain("1 part");
    const toggle = await screen.findByTestId("run-steps-toggle");
    expect(toggle.textContent).toBe("Details");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByTestId("run-steps").hasAttribute("hidden")).toBe(true);
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(screen.queryByTestId("approval-accept")).toBeNull();
    // The log lives once, inside the disclosure; the verdict stays plain.
    const steps = screen.getByTestId("run-steps").textContent ?? "";
    expect(steps).toContain("findstr");
    expect(steps).toContain("Working folder:");
    expect(verdict.textContent).not.toContain("Working folder:");
    expect(verdict.textContent).not.toContain("run success:");
  });

  it("history run-log without an executed flag renders verdict, never the card", async () => {
    historyTurns = [
      {
        project_id: "PV-hist",
        user_text: "create hello",
        assistant_text: PHOTO_LOG,
        time: "2026-01-01T00:00:00Z",
        id: "t-photo",
        status: "ok",
        run_id: "run-t-photo",
        error_code: "",
        executed: false,
        run_end_reason: "",
      },
    ];
    renderChat("PV-hist");
    expect(await screen.findByTestId("run-verdict")).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
  });
});

describe("V2 card gating per state", () => {
  it("interrupted turn shows resend and never the card", async () => {
    historyTurns = [
      {
        project_id: "PV-int",
        user_text: "count words",
        assistant_text: "half counted",
        time: "2026-01-01T00:00:00Z",
        id: "t-run",
        status: "running",
        run_id: "run-t-run",
        error_code: "",
        executed: false,
        run_end_reason: "",
      },
    ];
    renderChat("PV-int");
    expect(await screen.findByTestId("chat-resend")).toBeTruthy();
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(screen.queryByTestId("approval-accept")).toBeNull();
  });

  it("failed and stopped turns never show the card", async () => {
    historyTurns = [
      {
        project_id: "PV-fs",
        user_text: "dig",
        assistant_text: "half a ditch",
        time: "2026-01-01T00:00:00Z",
        id: "t-f",
        status: "failed",
        run_id: "run-t-f",
        error_code: "BUDGET_CAPPED",
        executed: false,
        run_end_reason: "",
      },
      {
        project_id: "PV-fs",
        user_text: "raise",
        assistant_text: "half a barn",
        time: "2026-01-01T00:00:00Z",
        id: "t-s",
        status: "stopped",
        run_id: "run-t-s",
        error_code: "STOPPED",
        executed: false,
        run_end_reason: "",
      },
    ];
    renderChat("PV-fs");
    await screen.findByTestId("chat-error-line");
    expect(screen.queryByTestId("approval-card")).toBeNull();
    expect(screen.queryByTestId("approval-accept")).toBeNull();
  });

  it("decided plain answer hides the card", async () => {
    streamReplies.push(() =>
      sse([
        `data: {"type":"start","stream_id":"srv-d","run_id":"r-d"}`,
        `data: {"type":"delta","stream_id":"srv-d","run_id":"r-d","text":"plain answer"}`,
        `data: {"type":"done","stream_id":"srv-d","run_id":"r-d","text":"plain answer","output_ref":"artifact:run/r-d/output"}`,
        "",
      ]),
    );
    renderChat("PV-dec");
    send("tell me");
    await screen.findByTestId("approval-accept");
    fireEvent.click(screen.getByTestId("approval-accept"));
    await waitFor(() => {
      expect(screen.queryByTestId("approval-card")).toBeNull();
    });
  });
});

describe("V3 live permission ask", () => {
  it("(a) send in an existing project shows the card within 1s", async () => {
    streamReplies.push(approvalStream);
    renderChat(HOLD_PROJECT);
    send("install the helper");
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
    expect(screen.getByTestId("permission-tool").textContent).toBe(
      "python",
    );
  });

  it("(b) first chat through initialSend shows the card within 1s", async () => {
    streamReplies.push(approvalStream);
    renderChat("PV-b", { initialSend: "install the helper" });
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
  });

  it("(c) ask parked while away shows on return without resending", async () => {
    streamReplies.push(approvalStream);
    const client = new HttpApiClient();
    const first = render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="PV-c" />
      </ApiClientProvider>,
    );
    send("install the helper");
    first.unmount();
    await waitFor(() => {
      expect(streamReplies).toHaveLength(0);
    });
    render(
      <ApiClientProvider client={client}>
        <ChatArea projectId="PV-c" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
  });

  it("(d) ask after Resend shows the card within 1s", async () => {
    historyTurns = [
      {
        project_id: "PV-d",
        user_text: "install the helper",
        assistant_text: "half installed",
        time: "2026-01-01T00:00:00Z",
        id: "t-r",
        status: "running",
        run_id: "run-t-r",
        error_code: "",
        executed: false,
        run_end_reason: "",
      },
    ];
    streamReplies.push(approvalStream);
    renderChat("PV-d");
    fireEvent.click(await screen.findByTestId("chat-resend"));
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
  });

  it("(e) slice key change mid-run still shows the card without remount", async () => {
    streamReplies.push(approvalStream);
    const clientA = new HttpApiClient();
    const clientB = new HttpApiClient();
    const view = render(
      <ApiClientProvider client={clientA}>
        <ChatArea projectId="PV-e" />
      </ApiClientProvider>,
    );
    send("install the helper");
    view.rerender(
      <ApiClientProvider client={clientB}>
        <ChatArea projectId="PV-e" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("permission-dialog")).toBeTruthy();
  });
});

describe("V4 live step line while working", () => {
  it("shows part, step, plain words and elapsed seconds under the composer", async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(entry) {
        controller = entry;
      },
    });
    streamReplies.push(
      () =>
        new Response(body, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );
    renderChat("PV-step");
    send("run it");
    await act(async () => {
      controller.enqueue(
        encoder.encode(
          'data: {"type":"start","stream_id":"srv-s","run_id":"r-s"}\n',
        ),
      );
      controller.enqueue(
        encoder.encode(
          `data: {"type":"delta","stream_id":"srv-s","run_id":"r-s","text":${JSON.stringify("Part p1: attempt 1\nCheck p1 $ C:\\tool\\python.EXE -m pytest -> exit 0\n")}}\n`,
        ),
      );
    });
    const line = await screen.findByTestId("chat-live-step");
    expect(line.textContent).toMatch(/Worker p1, step 1/);
    expect(line.textContent).toMatch(/,\s*\d+ s/);
    expect(line.textContent).not.toContain("C:\\");
    await act(async () => {
      controller.enqueue(
        encoder.encode(
          `data: {"type":"done","stream_id":"srv-s","run_id":"r-s","text":"Part p1: PASS","executed":true}\n`,
        ),
      );
      controller.close();
    });
    expect(await screen.findByTestId("run-verdict")).toBeTruthy();
  });
});

describe("V5 plain layer without raw words", () => {
  it("engine reply hides cost UNKNOWN and run-success lines outside Details", async () => {
    streamReplies.push(() =>
      sse([
        `data: {"type":"start","stream_id":"srv-5","run_id":"r-5"}`,
        `data: {"type":"delta","stream_id":"srv-5","run_id":"r-5","text":${JSON.stringify(PHOTO_LOG)}}`,
        `data: {"type":"done","stream_id":"srv-5","run_id":"r-5","text":${JSON.stringify(PHOTO_LOG)},"output_ref":"artifact:run/r-5/output"}`,
        "",
      ]),
    );
    renderChat("PV-plain");
    send("create hello");
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).toContain("Done");
    expect(verdict.textContent).toContain("cost not known");
    expect(verdict.textContent).not.toContain("cost: UNKNOWN");
    expect(verdict.textContent).not.toContain("run success:");
    const steps = screen.getByTestId("run-steps").textContent ?? "";
    expect(steps).toContain("run success: all 1 parts PASS");
  });
});

describe("LAPTOP_B photo lines", () => {
  it("(a) no raw code and no generic line around NO_PROVIDER_BOUND", async () => {
    streamReplies.push(() =>
      sse([
        `data: {"type":"start","stream_id":"srv-n","run_id":"r-n"}`,
        `data: {"type":"error","stream_id":"srv-n","run_id":"r-n","code":"NO_PROVIDER_BOUND","message":"wire"}`,
        "",
      ]),
    );
    renderChat("PV-np");
    send("do the thing");
    const line = await screen.findByTestId("chat-error-line");
    expect(line.textContent).toContain("Connect a provider first");
    expect(line.hasAttribute("title")).toBe(false);
    expect(line.textContent).not.toContain("NO_PROVIDER_BOUND");
    expect(document.body.textContent ?? "").not.toContain("Something went wrong");
    expect(document.body.textContent ?? "").not.toContain("NO_PROVIDER_BOUND");
    expect(screen.queryByTestId("kit-error-code")).toBeNull();
  });

  it("(a2) retrying run shows no stale generic line while working", async () => {
    streamReplies.push(() =>
      sse([
        `data: {"type":"start","stream_id":"srv-n","run_id":"r-n"}`,
        `data: {"type":"error","stream_id":"srv-n","run_id":"r-n","code":"NO_PROVIDER_BOUND","message":"wire"}`,
        "",
      ]),
    );
    let hang!: ReadableStreamDefaultController<Uint8Array>;
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(entry) {
        hang = entry;
      },
    });
    streamReplies.push(
      () =>
        new Response(body, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );
    renderChat("PV-np2");
    send("do the thing");
    await screen.findByTestId("chat-error-line");
    fireEvent.click(screen.getByTestId("kit-error-retry"));
    await act(async () => {
      hang.enqueue(
        encoder.encode(
          'data: {"type":"start","stream_id":"srv-r","run_id":"r-r"}\n',
        ),
      );
    });
    await screen.findByTestId("chat-spinner");
    expect(document.body.textContent ?? "").not.toContain("Something went wrong");
    await act(async () => {
      hang.close();
    });
  });

  it("(b) expanded empty hierarchy plus empty models offer exactly one Connect CTA", async () => {
    window.localStorage.setItem("agentsi.hierarchy.collapsed.PV-cta", "expanded");
    renderChat("PV-cta");
    await screen.findByTestId("hierarchy-connect-link");
    const ctas = screen
      .getAllByText("Connect a provider")
      .filter((node) => node.tagName === "A");
    expect(ctas).toHaveLength(1);
  });

  it("(c) status shows blocked, never Ready, with no provider", async () => {
    streamReplies.push(() =>
      sse([
        `data: {"type":"start","stream_id":"srv-c","run_id":"r-c"}`,
        `data: {"type":"error","stream_id":"srv-c","run_id":"r-c","code":"NO_PROVIDER_BOUND","message":"wire"}`,
        "",
      ]),
    );
    renderChat("PV-block");
    send("do the thing");
    await screen.findByTestId("chat-error-line");
    const status = await screen.findByTestId("chat-statusline");
    expect(status.textContent).not.toContain("Ready");
    expect(status.textContent).toContain("Blocked");
    expect(status.querySelectorAll(":scope > span")).toHaveLength(3);
  });

  it("(d) check lines name the program only, working folder stays in Details", async () => {
    historyTurns = [
      {
        project_id: "PV-prog",
        user_text: "run checks",
        assistant_text: PHOTO_LOG,
        time: "2026-01-01T00:00:00Z",
        id: "t-prog",
        status: "ok",
        run_id: "run-t-prog",
        error_code: "",
        executed: true,
        run_end_reason: "",
      },
    ];
    renderChat("PV-prog");
    const verdict = await screen.findByTestId("run-verdict");
    expect(verdict.textContent).not.toContain("C:\\");
    expect(verdict.textContent).not.toContain("findstr");
    const steps = screen.getByTestId("run-steps").textContent ?? "";
    expect(steps).toContain("findstr");
    expect(steps).not.toContain("C:\\Windows");
    expect(steps).not.toContain("C:\\Users");
    expect(steps).toContain("work");
    expect(steps).toContain("Working folder:");
  });
});

describe("FXOPEN O4 photo lines: paths, plan change, one entry", () => {
  const PHOTO_PATH_LOG = [
    "Working folder: D:\\Test2\\app\\data\\workspaces\\abc123",
    "Team: director, manager, worker, auditor on meta/x (Auto)",
    "Director: plan of 1 parts",
    "Part p1: Create file hello.txt with the text hello [files: hello.txt]",
    "Check p1 $ C:\\Windows\\system32\\findstr.EXE hello hello.txt -> exit 0",
    "Run dir: C:\\Users\\kot00\\work",
    "run success: all 1 parts PASS",
  ].join("\n");

  function historyOk(id: string, text: string): unknown {
    return {
      project_id: "PV-open",
      user_text: "create hello",
      assistant_text: text,
      time: "2026-01-01T00:00:00Z",
      id,
      status: "ok",
      run_id: `run-${id}`,
      error_code: "",
      executed: true,
      run_end_reason: "",
    };
  }

  it("chat shows file names, never host absolute paths or the user name", async () => {
    historyTurns = [historyOk("t-paths", PHOTO_PATH_LOG)];
    renderChat("PV-open");
    await screen.findByTestId("run-verdict");
    const steps = screen.getByTestId("run-steps").textContent ?? "";
    expect(steps).not.toMatch(/[A-Za-z]:[\\/]/);
    expect(steps).not.toContain("kot00");
    expect(steps).not.toContain("Test2");
    expect(steps).toContain("findstr");
    expect(steps).toContain("hello.txt");
    expect(steps).toContain("Working folder:");
  });

  it("a second plan announcement renders one plain Plan changed line", async () => {
    historyTurns = [
      historyOk(
        "t-plan",
        [
          "Director: plan of 2 parts",
          "Part p1: first [files: a.txt]",
          "Director: plan of 3 parts",
          "Part p1: Install pytest dependency [files: b.txt]",
          "run success: all 1 parts PASS",
        ].join("\n"),
      ),
    ];
    renderChat("PV-open");
    const changed = await screen.findByTestId("plan-changed");
    expect(changed.textContent).toContain("Plan changed:");
    expect(changed.textContent).toContain("was 2 parts");
    expect(changed.textContent).toContain("now 3 parts");
  });

  it("a single plan announcement renders no Plan changed line", async () => {
    historyTurns = [historyOk("t-one", PHOTO_PATH_LOG)];
    renderChat("PV-open");
    await screen.findByTestId("run-verdict");
    expect(screen.queryByTestId("plan-changed")).toBeNull();
  });

  function historyRunning(
    id: string,
    userText: string,
    time: string,
  ): unknown {
    return {
      project_id: "PV-open",
      user_text: userText,
      assistant_text: "half done",
      time,
      id,
      status: "running",
      run_id: `run-${id}`,
      error_code: "",
      executed: false,
      run_end_reason: "",
    };
  }

  it("one entry per interrupted task after restart", async () => {
    historyTurns = [
      historyRunning("t-1011", "count words", "2026-01-01T10:11:00Z"),
      historyRunning("t-1014", "count words", "2026-01-01T10:14:00Z"),
    ];
    renderChat("PV-open");
    await screen.findByTestId("chat-resend");
    expect(screen.getAllByTestId("chat-resend")).toHaveLength(1);
  });

  it("different interrupted tasks keep their own entries", async () => {
    historyTurns = [
      historyRunning("t-a", "count words", "2026-01-01T10:11:00Z"),
      historyRunning("t-b", "weigh stones", "2026-01-01T10:14:00Z"),
    ];
    renderChat("PV-open");
    const resends = await screen.findAllByTestId("chat-resend");
    expect(resends).toHaveLength(2);
  });
});

describe("FXOPEN O6 J6: the composer grows with the draft", () => {
  it("a long draft grows toward six rows, a short draft stays one", async () => {
    renderChat("PV-grow");
    const prompt = (await screen.findByTestId(
      "chat-prompt",
    )) as HTMLTextAreaElement;
    expect(prompt.rows).toBe(1);
    fireEvent.change(prompt, {
      target: { value: "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8" },
    });
    expect(prompt.rows).toBe(6);
    fireEvent.change(prompt, { target: { value: "short" } });
    expect(prompt.rows).toBe(1);
  });
});
