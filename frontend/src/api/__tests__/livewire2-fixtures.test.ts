/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "../client";
import {
  ApiError,
  apiErrorLocaleKey,
  isErrorCode,
  parseErrorBody,
} from "../errors";
import {
  BudgetResponseSchema,
  PackageReportSchema,
} from "../projectsApi";
import { streamChat } from "../../chat/chatApi";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import budgetFixture from "../wire/budget-state.json";
import openFixture from "../wire/chat-open-request.json";
import eventsFixture from "../wire/chat-stream-events.json?raw";
import errorFixture from "../wire/error-body.json";
import reportFixture from "../wire/report-body.json";

afterEach(() => {
  vi.unstubAllGlobals();
  resetLocaleForTests();
});

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function asSseText(fixture: unknown): string {
  if (typeof fixture === "string") {
    return fixture;
  }
  if (Array.isArray(fixture)) {
    return fixture.map((frame) => String(frame)).join("");
  }
  const record = asRecord(fixture);
  if (record !== null) {
    for (const key of ["sse", "bytes", "body", "text"]) {
      if (typeof record[key] === "string") {
        return record[key] as string;
      }
    }
    for (const key of ["frames", "events", "lines", "data"]) {
      if (Array.isArray(record[key])) {
        return (record[key] as unknown[]).map((frame) => String(frame)).join("");
      }
    }
  }
  throw new Error("unrecognized chat-stream-events fixture shape");
}

function asOpenBody(fixture: unknown): Record<string, unknown> {
  const record = asRecord(fixture);
  if (record === null) {
    throw new Error("unrecognized chat-open-request fixture shape");
  }
  const nested = asRecord(record["body"]);
  const body = nested ?? record;
  if (typeof body["project"] !== "string" || typeof body["message"] !== "string") {
    throw new Error("chat-open-request fixture needs {project, message}");
  }
  return body;
}

function asErrorSamples(
  fixture: unknown,
): Array<{ name: string; status: number; body: unknown }> {
  const record = asRecord(fixture);
  let entries: Array<[string, unknown]>;
  if (Array.isArray(fixture)) {
    entries = fixture.map((item, index) => [String(index), item]);
  } else if (record !== null && Array.isArray(record["samples"])) {
    entries = (record["samples"] as unknown[]).map((item, index) => [
      String(index),
      item,
    ]);
  } else if (record !== null && Array.isArray(record["cases"])) {
    entries = (record["cases"] as unknown[]).map((item, index) => [
      String(index),
      item,
    ]);
  } else if (record !== null) {
    entries = Object.entries(record);
  } else {
    throw new Error("unrecognized error-body fixture shape");
  }
  const out: Array<{ name: string; status: number; body: unknown }> = [];
  for (const [name, sample] of entries) {
    if (typeof sample === "number" || typeof sample === "string") {
      continue;
    }
    const sampleRecord = asRecord(sample);
    if (sampleRecord === null) {
      continue;
    }
    const direct = sampleRecord["status"];
    const suffix = /_(\d{3})$/.exec(name)?.[1];
    out.push({
      name,
      status:
        typeof direct === "number"
          ? direct
          : suffix !== undefined
            ? Number.parseInt(suffix, 10)
            : 0,
      body: "body" in sampleRecord ? sampleRecord["body"] : sample,
    });
  }
  if (out.length === 0) {
    throw new Error("error-body fixture holds no samples");
  }
  return out;
}

function sampleCode(body: unknown): string | null {
  const record = asRecord(body);
  if (record === null) {
    return null;
  }
  if (typeof record["code"] === "string" && record["code"].length > 0) {
    return record["code"];
  }
  const detail = asRecord(record["detail"]);
  if (
    detail !== null &&
    typeof detail["code"] === "string" &&
    detail["code"].length > 0
  ) {
    return detail["code"];
  }
  return null;
}

function deltaOracle(text: string): string {
  const parts: string[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) {
      continue;
    }
    const payload = trimmed.slice("data:".length).trim();
    if (payload === "" || payload === "[DONE]") {
      continue;
    }
    let event: unknown;
    try {
      event = JSON.parse(payload) as unknown;
    } catch {
      continue;
    }
    const record = asRecord(event);
    if (record !== null && record["type"] === "delta" && typeof record["text"] === "string") {
      parts.push(record["text"]);
    }
  }
  return parts.join("");
}

function startStreamId(text: string): string | null {
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) {
      continue;
    }
    let event: unknown;
    try {
      event = JSON.parse(trimmed.slice("data:".length).trim()) as unknown;
    } catch {
      continue;
    }
    const record = asRecord(event);
    if (
      record !== null &&
      record["type"] === "start" &&
      typeof record["stream_id"] === "string"
    ) {
      return record["stream_id"];
    }
  }
  return null;
}

describe("wire fixtures with the real client schemas", () => {
  it("parses budget-state.json with BudgetResponseSchema", () => {
    const body = BudgetResponseSchema.parse(budgetFixture);
    expect(typeof body.budget.hard_limit).toBe("number");
    expect(typeof body.budget.spent).toBe("number");
    expect(typeof body.budget.reserved).toBe("number");
    expect(body.project_id.length).toBeGreaterThan(0);
  });

  it("parses report-body.json with PackageReportSchema", () => {
    const report = PackageReportSchema.parse(reportFixture);
    expect(typeof report.row.package_id).toBe("string");
    expect(typeof report.row.wall_time_s).toBe("number");
    expect(report.auto_push).toBe(false);
  });

  it("parses every error-body.json sample to a localizable code", () => {
    const samples = asErrorSamples(errorFixture);
    expect(samples.length).toBeGreaterThan(0);
    for (const sample of samples) {
      try {
        const error = parseErrorBody(sample.body, sample.status);
        expect(error).toBeInstanceOf(ApiError);
        const code = sampleCode(sample.body);
        if (code !== null && isErrorCode(code)) {
          expect(error.code).toBe(code);
        } else if (code !== null) {
          expect(apiErrorLocaleKey(error.code as string)).toBe(
            "errors.generic",
          );
        } else {
          expect([
            "api.error.context_missing",
            "api.error.context_wrong_contract_version",
          ]).toContain(apiErrorLocaleKey(error.code as string));
        }
        const key = apiErrorLocaleKey(error.code as string);
        setLocale("en");
        expect(t(key).length).toBeGreaterThan(0);
        setLocale("uk");
        expect(t(key).length).toBeGreaterThan(0);
      } catch (cause) {
        throw new Error(
          `fixture sample ${sample.name}: ${(cause as Error).message}`,
        );
      }
    }
    resetLocaleForTests();
  });

  it("streams the fixture no-provider error event through the chat reader", async () => {
    const record = asRecord(
      (errorFixture as Record<string, unknown>)["no_provider_error_event"],
    );
    expect(record?.["type"]).toBe("error");
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(`data: ${JSON.stringify(record)}\n\n`, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );
    const client = new HttpApiClient();
    const runner = streamChat(
      client,
      { project_id: "p-1", prompt_ref: "wire probe", stream_id: "wire-1" },
      {
        onChunkText: () => undefined,
        isCancelled: () => false,
      },
    );
    await expect(runner.done).rejects.toMatchObject({
      code: "NO_PROVIDER_BOUND",
    });
  });

  it("sends exactly the chat-open-request.json body shape", async () => {
    const openBody = asOpenBody(openFixture);
    const seen: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      async (_url: unknown, init?: RequestInit) => {
        const raw = init?.body;
        seen.push(
          typeof raw === "string" && raw.length > 0
            ? (JSON.parse(raw) as unknown)
            : undefined,
        );
        return new Response(
          'data: {"type":"start","stream_id":"srv-wire","run_id":"r-wire"}\n\ndata: {"type":"done","stream_id":"srv-wire","run_id":"r-wire"}\n\n',
          {
            status: 200,
            headers: { "content-type": "text/event-stream" },
          },
        );
      },
    );
    const client = new HttpApiClient();
    const texts: string[] = [];
    const runner = streamChat(
      client,
      {
        project_id: openBody["project"] as string,
        prompt_ref: openBody["message"] as string,
        stream_id: "wire-probe-1",
      },
      {
        onChunkText: (text) => {
          texts.push(text);
        },
        isCancelled: () => false,
      },
    );
    await runner.done;
    expect(seen).toHaveLength(1);
    expect(seen[0]).toEqual({
      project: openBody["project"],
      message: openBody["message"],
    });
  });

  it("streams chat-stream-events.json through the real chat reader", async () => {
    const text = asSseText(eventsFixture);
    const expected = deltaOracle(text);
    const serverId = startStreamId(text);
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(text, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );
    const client = new HttpApiClient();
    const stream = client.openChatStream({
      project_id: "p-1",
      prompt_ref: "wire probe",
      stream_id: "wire-probe-1",
    });
    const chunks = [];
    for await (const chunk of stream.chunks) {
      chunks.push(chunk);
    }
    expect(chunks.filter((chunk) => chunk.done)).toHaveLength(1);
    expect(chunks.map((chunk) => chunk.delta).join("")).toBe(expected);
    if (serverId !== null) {
      for (const chunk of chunks) {
        expect(chunk.stream_id).toBe(serverId);
      }
    }
    const texts: string[] = [];
    const second = new HttpApiClient();
    const runner = streamChat(
      second,
      {
        project_id: "p-1",
        prompt_ref: "wire probe",
        stream_id: "wire-probe-2",
      },
      {
        onChunkText: (entry) => {
          texts.push(entry);
        },
        isCancelled: () => false,
      },
    );
    await runner.done;
    expect(texts.join("")).toBe(expected);
  });
});
