/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import {
  DEFAULT_CONTRACT_BINDING,
  DEFAULT_CONTRACT_VERSION,
  confirmAgentContractDefaults,
  confirmStoredProfile,
} from "../contractDefaults";
import { ContractDefaultsBar } from "../ContractDefaultsBar";

function jsonBody(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function stubRoleGet(profile: unknown, status = 200): void {
  vi.stubGlobal(
    "fetch",
    async (url: unknown, init?: { method?: string }) => {
      const path = String(url);
      const method = init?.method ?? "GET";
      if (
        path === "/api/v1/routing/role?project_id=p-9&role=manager" &&
        method === "GET"
      ) {
        if (status === 200) {
          return jsonBody({ profile });
        }
        return new Response("missing", { status });
      }
      throw new Error(`unexpected fetch ${method} ${path}`);
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("ARCH-720 contract defaults confirmation", () => {
  it("rejects an unknown mode with no defaults", () => {
    const result = confirmAgentContractDefaults({});
    expect(result.confirmed).toBe(false);
    expect(result.missing).toContain("mode");
    expect(result.defaults).toBeNull();
  });

  it("confirms AUTO with the shipped binding and version defaults", () => {
    const result = confirmAgentContractDefaults({ mode: "AUTO" });
    expect(result.confirmed).toBe(true);
    expect(result.missing).toEqual([]);
    expect(result.defaults).toMatchObject({
      mode: "AUTO",
      binding: DEFAULT_CONTRACT_BINDING,
      version: DEFAULT_CONTRACT_VERSION,
    });
    expect(DEFAULT_CONTRACT_BINDING).toBe("DEFAULT");
    expect(DEFAULT_CONTRACT_VERSION).toBe(1);
  });

  it("requires provider and model for PINNED", () => {
    const result = confirmAgentContractDefaults({ mode: "PINNED" });
    expect(result.confirmed).toBe(false);
    expect(result.missing).toEqual(
      expect.arrayContaining(["provider", "model"]),
    );
    expect(result.defaults).toBeNull();
  });

  it("keeps explicit binding and version instead of the defaults", () => {
    const result = confirmAgentContractDefaults({
      mode: "PINNED",
      provider: "acme",
      model: "m-1",
      binding: "CUSTOM",
      version: 3,
    });
    expect(result.confirmed).toBe(true);
    expect(result.defaults).toMatchObject({
      mode: "PINNED",
      provider: "acme",
      model: "m-1",
      binding: "CUSTOM",
      version: 3,
    });
  });

  it("falls back to the defaults for a bad version", () => {
    const result = confirmAgentContractDefaults({
      mode: "pool",
      version: 0,
    });
    expect(result.confirmed).toBe(true);
    expect(result.defaults?.version).toBe(DEFAULT_CONTRACT_VERSION);
  });

  it("confirms an undefined stored profile as missing", () => {
    const result = confirmStoredProfile(undefined);
    expect(result.confirmed).toBe(false);
    expect(result.missing).toContain("mode");
  });
});

describe("ContractDefaultsBar", () => {
  it("shows the confirmed effective defaults from the server profile", async () => {
    stubRoleGet({
      role: "manager",
      project_id: "p-9",
      mode: "PINNED",
      provider: "acme",
      model: "m-1",
      binding: "CUSTOM",
      version: 3,
    });
    render(<ContractDefaultsBar projectId="p-9" role="manager" />);
    const confirmed = await screen.findByTestId(
      "contract-defaults-confirmed",
    );
    expect(confirmed.textContent).toContain(
      t("settings.roleProfile.modes.pinned"),
    );
    const bar = await screen.findByTestId("contract-defaults-bar");
    expect(bar.textContent).toContain(
      t("settings.roleProfile.providerLabel"),
    );
    expect(bar.textContent).toContain("acme");
    expect(bar.textContent).toContain("m-1");
  });

  it("shows the missing shape when no stored profile exists", async () => {
    stubRoleGet(null, 404);
    render(<ContractDefaultsBar projectId="p-9" role="manager" />);
    const missing = await screen.findByTestId("contract-defaults-missing");
    expect(missing.textContent).toContain(t("errors.generic"));
    const bar = await screen.findByTestId("contract-defaults-bar");
    expect(bar.textContent).toContain("mode");
  });
});
