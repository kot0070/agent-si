/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "../client";
import {
  ApiError,
  API_ERROR_CODES,
  apiErrorLocaleKey,
  parseErrorBody,
} from "../errors";
import type { ApiErrorCode, ChatOpen } from "../iface";
import {
  BudgetResponseSchema,
  BudgetStateSchema,
  ChatStreamEventSchema,
  PackageReportSchema,
  readBudgetState,
  readPackageReport,
} from "../projectsApi";
import { streamChat } from "../../chat/chatApi";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";

afterEach(() => {
  vi.unstubAllGlobals();
  resetLocaleForTests();
});

const SERVED_BUDGET_BODY = {
  project_id: "p-1",
  budget: {
    project_id: "p-1",
    currency: "u-1",
    budget_limit: "5.00",
    soft_limit: "4.00",
    hard_limit: "5.00",
    spent: "1.25",
    reserved: "0.50",
    updated_at: "t-0",
    provider_spend_caps: {},
    remaining_derived: "3.25",
  },
};

const SERVED_REPORT_BODY = {
  package_id: "pkg-1",
  load: { package_id: "pkg-1", agents: 2, peak_concurrency: 2, wall_time_s: 60 },
  nudge: "review package pkg-1 load before starting the next package",
  auto_push: false,
};

function sseResponse(
  text: string,
  headers: Record<string, string> = {},
): Response {
  return new Response(text, {
    status: 200,
    headers: { "content-type": "text/event-stream", ...headers },
  });
}

function stubFetch(
  respond: (url: string, init?: RequestInit) => Response | Promise<Response>,
): { seen: Array<{ url: string; body: unknown }> } {
  const seen: Array<{ url: string; body: unknown }> = [];
  vi.stubGlobal("fetch", async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const rawBody = init?.body;
    seen.push({
      url,
      body:
        typeof rawBody === "string" && rawBody.length > 0
          ? (JSON.parse(rawBody) as unknown)
          : undefined,
    });
    return respond(url, init);
  });
  return { seen };
}

function drain(
  body: ChatOpen,
): { client: HttpApiClient; texts: string[]; done: Promise<{ aborted: boolean }> } {
  const client = new HttpApiClient();
  const texts: string[] = [];
  const runner = streamChat(
    client,
    body,
    {
      onChunkText: (text) => {
        texts.push(text);
      },
      isCancelled: () => false,
    },
  );
  return { client, texts, done: runner.done };
}

describe("L0B-08 served budget shape", () => {
  it("accepts the served budget payload with string amounts", () => {
    const state = BudgetStateSchema.parse(SERVED_BUDGET_BODY.budget);
    expect(state).toEqual({
      project_id: "p-1",
      hard_limit: 5,
      spent: 1.25,
      reserved: 0.5,
      currency: "u-1",
    });
  });

  it("still accepts numeric amounts", () => {
    const state = BudgetStateSchema.parse({
      project_id: "p-1",
      hard_limit: 5,
      spent: 1,
      reserved: 0,
      currency: "u-1",
    });
    expect(state.spent).toBe(1);
  });

  it("unwraps budget, not state, through the real budget call", async () => {
    stubFetch((url) => {
      expect(url).toContain("/api/v1/budget");
      return new Response(JSON.stringify(SERVED_BUDGET_BODY), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const state = await readBudgetState("p-1");
    expect(state).toEqual({
      project_id: "p-1",
      hard_limit: 5,
      spent: 1.25,
      reserved: 0.5,
      currency: "u-1",
    });
  });

  it("rejects the legacy state envelope", async () => {
    stubFetch(
      () =>
        new Response(
          JSON.stringify({
            state: {
              project_id: "p-1",
              hard_limit: 5,
              spent: 1,
              reserved: 0,
              currency: "u-1",
            },
          }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          },
        ),
    );
    await expect(readBudgetState("p-1")).rejects.toMatchObject({
      code: "GENERIC_ERROR",
    });
  });

  it("validates the response envelope project id", () => {
    expect(() =>
      BudgetResponseSchema.parse({ project_id: "", budget: {} }),
    ).toThrow();
  });
});

describe("L0B-09 chat open shape", () => {
  it("sends {project, message} with no client-side ids", async () => {
    const { seen } = stubFetch(() =>
      sseResponse(
        'data: {"type":"start","stream_id":"srv-1","run_id":"r-1"}\n\ndata: {"type":"done","stream_id":"srv-1","run_id":"r-1"}\n\n',
        { "x-stream-id": "srv-1" },
      ),
    );
    const { done } = drain({
      project_id: "p-1",
      prompt_ref: "hello",
      stream_id: "c-1",
    });
    await expect(done).resolves.toEqual({ aborted: false });
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toContain("/api/v1/chat/stream");
    expect(seen[0]?.body).toEqual({ project: "p-1", message: "hello" });
  });

  it("adopts the server stream id from the header and start event", async () => {
    stubFetch(() =>
      sseResponse(
        'data: {"type":"start","stream_id":"srv-7","run_id":"r-7"}\n\ndata: {"type":"delta","stream_id":"srv-7","run_id":"r-7","text":"hi"}\n\ndata: {"type":"done","stream_id":"srv-7","run_id":"r-7"}\n\n',
        { "x-stream-id": "srv-7" },
      ),
    );
    const client = new HttpApiClient();
    const stream = client.openChatStream({
      project_id: "p-1",
      prompt_ref: "hello",
      stream_id: "c-9",
    });
    expect(stream.stream_id).toBe("c-9");
    const chunks = [];
    for await (const chunk of stream.chunks) {
      chunks.push(chunk);
    }
    expect(stream.stream_id).toBe("srv-7");
    expect(chunks.map((chunk) => chunk.stream_id)).toEqual(["srv-7", "srv-7"]);
    expect(chunks.map((chunk) => chunk.delta)).toEqual(["hi", ""]);
    expect(chunks[chunks.length - 1]?.done).toBe(true);
  });
});

describe("L0B-10 chat stream vocabulary", () => {
  const ANSWER_SSE = [
    'data: {"type":"start","stream_id":"srv-1","run_id":"r-1"}',
    'data: {"type":"delta","stream_id":"srv-1","run_id":"r-1","text":"Hel"}',
    'data: {"type":"delta","stream_id":"srv-1","run_id":"r-1","text":"lo"}',
    'data: {"type":"done","stream_id":"srv-1","run_id":"r-1","text":"Hello","output_ref":"artifact:run/r-1/output"}',
    'data: {"type":"done","stream_id":"srv-1","run_id":"r-1"}',
    "",
  ].join("\n");

  it("accumulates delta text once and finishes on done", async () => {
    stubFetch(() => sseResponse(ANSWER_SSE, { "x-stream-id": "srv-1" }));
    const { texts, done } = drain({
      project_id: "p-1",
      prompt_ref: "hello",
      stream_id: "c-1",
    });
    await expect(done).resolves.toEqual({ aborted: false });
    expect(texts).toEqual(["Hel", "lo"]);
    expect(texts.join("")).toBe("Hello");
  });

  it("never appends done text and stops at the first terminal", async () => {
    stubFetch(() => sseResponse(ANSWER_SSE));
    const client = new HttpApiClient();
    const stream = client.openChatStream({
      project_id: "p-1",
      prompt_ref: "hello",
      stream_id: "c-1",
    });
    const chunks = [];
    for await (const chunk of stream.chunks) {
      chunks.push(chunk);
    }
    expect(chunks.filter((chunk) => chunk.done)).toHaveLength(1);
    expect(chunks.map((chunk) => chunk.delta).join("")).toBe("Hello");
  });

  it("tolerates tool_call and other future event kinds", () => {
    const frame = ChatStreamEventSchema.parse({
      type: "tool_call",
      stream_id: "srv-1",
      run_id: "r-1",
      text: "should never surface",
    });
    expect(frame.type).toBe("tool_call");
  });

  it("surfaces error events as ApiError, never silently", async () => {
    stubFetch(() =>
      sseResponse(
        'data: {"type":"start","stream_id":"srv-2","run_id":"r-2"}\n\ndata: {"type":"error","stream_id":"srv-2","run_id":"r-2","code":"BUDGET_CAPPED","message":"capped"}\n\n',
      ),
    );
    const { texts, done } = drain({
      project_id: "p-1",
      prompt_ref: "hello",
      stream_id: "c-2",
    });
    await expect(done).rejects.toMatchObject({ code: "BUDGET_CAPPED" });
    await expect(done).rejects.toBeInstanceOf(ApiError);
    expect(texts).toEqual([]);
  });

  it("surfaces approval events as errors, never silently", async () => {
    stubFetch(() =>
      sseResponse(
        'data: {"type":"start","stream_id":"srv-3","run_id":"r-3"}\n\ndata: {"type":"approval","stream_id":"srv-3","run_id":"r-3","reason":"need ok"}\n\n',
      ),
    );
    const { done } = drain({
      project_id: "p-1",
      prompt_ref: "hello",
      stream_id: "c-3",
    });
    await expect(done).rejects.toMatchObject({ code: "APPROVAL_REQUIRED" });
  });

  it("maps unknown stream error codes to the localized generic", async () => {
    stubFetch(() =>
      sseResponse(
        'data: {"type":"error","stream_id":"srv-4","run_id":"r-4","code":"WIBBLE_X9","message":"future"}\n\n',
      ),
    );
    const { done } = drain({
      project_id: "p-1",
      prompt_ref: "hello",
      stream_id: "c-4",
    });
    const error = await done.then(
      () => null,
      (cause: unknown) => cause,
    );
    expect(error).toBeInstanceOf(ApiError);
    const code = (error as ApiError).code as string;
    expect(API_ERROR_CODES).not.toContain(code);
    expect(apiErrorLocaleKey(code)).toBe("errors.generic");
  });

  it("keeps the request id for legacy frames without a type", async () => {
    stubFetch(() =>
      sseResponse(
        'data: {"stream_id":"other","delta":"hello ","done":false}\n' +
          'data: {"stream_id":"other","delta":"world","done":true}\n',
      ),
    );
    const { texts, done } = drain({
      project_id: "p-1",
      prompt_ref: "hello",
      stream_id: "c-9",
    });
    await expect(done).resolves.toEqual({ aborted: false });
    expect(texts.join("")).toBe("hello world");
  });
});

describe("L0B-11 error codes and locale messages", () => {
  it("maps every ApiError code to its own en and uk message", () => {
    for (const code of API_ERROR_CODES) {
      const key = apiErrorLocaleKey(code as ApiErrorCode);
      // FXANSWER S1: GENERIC_ERROR is the generic by design.
      if (code === "GENERIC_ERROR") {
        expect(key).toBe("errors.generic");
        continue;
      }
      expect(key).not.toBe("errors.generic");
      setLocale("en");
      const english = t(key);
      expect(english.length).toBeGreaterThan(0);
      setLocale("uk");
      const ukrainian = t(key);
      expect(ukrainian.length).toBeGreaterThan(0);
    }
    resetLocaleForTests();
  });

  it("gives NO_PROVIDER_BOUND a connect-a-provider message", () => {
    expect(apiErrorLocaleKey("NO_PROVIDER_BOUND")).toBe(
      "firstrun.steps.connectProvider",
    );
    setLocale("en");
    const english = t("firstrun.steps.connectProvider");
    expect(english).toContain("Connect a provider");
    setLocale("uk");
    const ukrainian = t("firstrun.steps.connectProvider");
    expect(ukrainian.length).toBeGreaterThan(0);
    expect(ukrainian).not.toBe(english);
    resetLocaleForTests();
  });

  it("maps an unknown code to the localized generic", () => {
    expect(apiErrorLocaleKey("WIBBLE_X9")).toBe("errors.generic");
    setLocale("en");
    expect(t(apiErrorLocaleKey("WIBBLE_X9")).length).toBeGreaterThan(0);
    setLocale("uk");
    expect(t(apiErrorLocaleKey("WIBBLE_X9")).length).toBeGreaterThan(0);
    resetLocaleForTests();
  });

  it("parses machine-code error bodies and preserves unknown codes", () => {
    expect(parseErrorBody({ code: "NO_PROVIDER_BOUND", message: "x" }, 404))
      .toMatchObject({ code: "NO_PROVIDER_BOUND", status: 404 });
    const unknown = parseErrorBody({ code: "WIBBLE_X9", message: "?" }, 500);
    expect(unknown.code as string).toBe("WIBBLE_X9");
    expect(apiErrorLocaleKey(unknown.code as string)).toBe("errors.generic");
  });

  it("keeps the legacy plain-string fallbacks", () => {
    expect(
      parseErrorBody({ error: "no budget state on file 'p-9'" }, 404),
    ).toMatchObject({ code: "CONTEXT_MISSING" });
    expect(parseErrorBody({ detail: "boom" }, 500)).toMatchObject({
      code: "GENERIC_ERROR",
    });
  });
});

describe("report body shape", () => {
  it("reads the served load shape", () => {
    expect(PackageReportSchema.parse(SERVED_REPORT_BODY)).toEqual({
      row: SERVED_REPORT_BODY.load,
      nudge: SERVED_REPORT_BODY.nudge,
      auto_push: false,
    });
  });

  it("reads the served report through the real report call", async () => {
    stubFetch((url) => {
      expect(url).toContain("/api/v1/reports/next-package-nudge");
      return new Response(JSON.stringify(SERVED_REPORT_BODY), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    const report = await readPackageReport("pkg-1");
    expect(report.row.package_id).toBe("pkg-1");
    expect(report.auto_push).toBe(false);
  });
});
