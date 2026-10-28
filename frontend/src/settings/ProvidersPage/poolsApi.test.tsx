/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { clearUiToken, setUiToken } from "../../api/errors";
import { buildRolePoolBody, saveRolePool } from "./poolsApi";
import type { PoolOption } from "./RolePoolPicker";

const OPTIONS: PoolOption[] = [
  {
    key: "pool-opt-1",
    label: "OpenAI — Standard",
    providerId: "openai",
    modelId: "openai/model-1",
  },
];

afterEach(() => {
  vi.unstubAllGlobals();
  clearUiToken();
});

function stubFetch() {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init: init ?? {} });
    return { ok: true, status: 200, json: async () => ({}) };
  });
  vi.stubGlobal("fetch", mock);
  return { mock, calls };
}

describe("saveRolePool header token", () => {
  it("PUTs the bare pools URL with the UI token in the header", async () => {
    setUiToken("hdr-pools-1");
    const { mock, calls } = stubFetch();
    await saveRolePool(
      "local",
      "worker",
      { mode: "AUTO", pinnedKey: "", poolKeys: [], strategy: "AUTO" },
      OPTIONS,
    );
    expect(mock).toHaveBeenCalledTimes(1);
    const { url, init } = calls[0];
    expect(url).toBe("/api/v1/roles/pools");
    expect(url).not.toContain("session_token");
    expect(init.method).toBe("PUT");
    const headers = init.headers as Record<string, string>;
    expect(headers["x-ui-session-token"]).toBe("hdr-pools-1");
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body).toMatchObject({
      project_id: "local",
      role: "worker",
      mode: "AUTO",
    });
    expect(JSON.stringify(body)).not.toContain("session_token");
    expect(JSON.stringify(body)).not.toContain("hdr-pools-1");
  });

  it("sends a pinned pool body without any token in the URL", async () => {
    setUiToken("hdr-pools-2");
    const { calls } = stubFetch();
    await saveRolePool(
      "local",
      "worker",
      { mode: "PINNED", pinnedKey: "pool-opt-1", poolKeys: [], strategy: "AUTO" },
      OPTIONS,
    );
    const { url, init } = calls[0];
    expect(url).not.toContain("session_token");
    expect(url).not.toContain("?");
    const headers = init.headers as Record<string, string>;
    expect(headers["x-ui-session-token"]).toBe("hdr-pools-2");
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body).toMatchObject({
      project_id: "local",
      role: "worker",
      mode: "PINNED",
      provider: "openai",
      model: "openai/model-1",
    });
    expect(body["pool"]).toEqual([]);
    expect(JSON.stringify(body)).not.toContain("session_token");
  });

  it("buildRolePoolBody keeps tokens out of the JSON body", () => {
    const body = buildRolePoolBody(
      "local",
      "worker",
      { mode: "AUTO", pinnedKey: "", poolKeys: [], strategy: "AUTO" },
      OPTIONS,
    );
    expect(JSON.stringify(body)).not.toContain("session_token");
  });
});
