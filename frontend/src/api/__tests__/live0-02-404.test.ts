/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "../client";
import { apiErrorLocaleKey, ApiError } from "../errors";
import { setLocale, resetLocaleForTests, t } from "../../locale/index";

afterEach(() => {
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function stubStatus(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
  );
}

describe("LIVE0-02 honest 404 wording", () => {
  it("a 404 project fetch reports CONTEXT_MISSING, never the contract-version error", async () => {
    resetLocaleForTests();
    setLocale("en");
    stubStatus(404, { surprise: true });
    const failure = await new HttpApiClient().listProjects().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: "CONTEXT_MISSING", status: 404 });
    expect((failure as ApiError).code).not.toBe("CONTEXT_WRONG_CONTRACT_VERSION");
    expect(apiErrorLocaleKey((failure as ApiError).code)).toBe("api.error.context_missing");
    expect(t(apiErrorLocaleKey((failure as ApiError).code) as "api.error.context_missing")).not.toContain(
      "contract version",
    );
  });

  it("a 404 chat stream reports the connect-provider message, never the contract-version error", async () => {
    resetLocaleForTests();
    setLocale("en");
    stubStatus(404, { detail: "no live chat engine" });
    const client = new HttpApiClient();
    const stream = client.openChatStream({
      project_id: "p-1",
      prompt_ref: "r-1",
      stream_id: "s-1",
    });
    const failure = await (async (): Promise<unknown> => {
      try {
        for await (const chunk of stream.chunks) {
          void chunk;
        }
        return null;
      } catch (error) {
        return error;
      }
    })();
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: "NO_PROVIDER_BOUND", status: 404 });
    expect((failure as ApiError).code).not.toBe("CONTEXT_WRONG_CONTRACT_VERSION");
    expect(apiErrorLocaleKey((failure as ApiError).code)).toBe("firstrun.steps.connectProvider");
  });

  it("an offline failure reports server-down wording, never the contract-version error", async () => {
    resetLocaleForTests();
    setLocale("en");
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("offline");
    });
    const failure = await new HttpApiClient().listProjects().catch((error: unknown) => error);
    expect(failure).toMatchObject({ code: "CONTEXT_MISSING", status: 0 });
    expect((failure as ApiError).code).not.toBe("CONTEXT_WRONG_CONTRACT_VERSION");
    expect(apiErrorLocaleKey((failure as ApiError).code)).toBe("api.error.context_missing");
  });
});
