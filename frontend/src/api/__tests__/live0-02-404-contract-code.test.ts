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

describe("LIVE0-02 explicit contract-version code on 404 still reads not-found", () => {
  it("a 404 carrying the contract-version code reports CONTEXT_MISSING, never the contract-version error", async () => {
    resetLocaleForTests();
    setLocale("en");
    stubStatus(404, { code: "CONTEXT_WRONG_CONTRACT_VERSION" });
    const failure = await new HttpApiClient().listProjects().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: "CONTEXT_MISSING", status: 404 });
    expect(apiErrorLocaleKey((failure as ApiError).code)).toBe("api.error.context_missing");
    expect(t(apiErrorLocaleKey((failure as ApiError).code) as "api.error.context_missing")).not.toContain(
      "contract version",
    );
  });

  it("a 404 carrying the contract-version code in detail reports CONTEXT_MISSING", async () => {
    resetLocaleForTests();
    setLocale("en");
    stubStatus(404, { detail: { code: "CONTEXT_WRONG_CONTRACT_VERSION" } });
    const failure = await new HttpApiClient().listProjects().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: "CONTEXT_MISSING", status: 404 });
    expect(apiErrorLocaleKey((failure as ApiError).code)).toBe("api.error.context_missing");
  });

  it("a 404 chat stream carrying the contract-version code still reports the connect-provider message", async () => {
    resetLocaleForTests();
    setLocale("en");
    stubStatus(404, { code: "CONTEXT_WRONG_CONTRACT_VERSION" });
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
    expect(apiErrorLocaleKey((failure as ApiError).code)).toBe("firstrun.steps.connectProvider");
  });

  it("a 404 carrying a real server code keeps that code (no overcorrection)", async () => {
    stubStatus(404, { code: "NO_PROVIDER_BOUND" });
    const failure = await new HttpApiClient().listProjects().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: "NO_PROVIDER_BOUND", status: 404 });
  });

  it("a codeless 500 still reports the generic error, never contract-version (FXANSWER S1)", async () => {
    stubStatus(500, { surprise: true });
    const failure = await new HttpApiClient().listProjects().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: "GENERIC_ERROR", status: 500 });
    expect(apiErrorLocaleKey((failure as ApiError).code)).toBe("errors.generic");
  });
});
