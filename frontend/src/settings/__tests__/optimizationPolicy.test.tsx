/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { OptimizationPolicySection } from "../optimizationPolicy";

const POLICY_URL = "/api/v1/routing/optimization-policy";

// FAKE-OF: GET /api/v1/routing/optimization-policy (ARCH-528 served row).
function policyPayload() {
  return {
    policy_id: "ctx-default",
    version: 1,
    required_quality: 0.8,
    max_risk: "HIGH",
    weights: {
      weight_quality: 1.0,
      weight_cost: 1.0,
      weight_latency: 1.0,
      weight_cloud_tokens: 1.0,
    },
    local_preference: false,
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  vi.unstubAllGlobals();
});

describe("OptimizationPolicySection", () => {
  it("presents required quality, the risk ceiling and the weights", async () => {
    vi.stubGlobal(
      "fetch",
      async (url: unknown) => {
        expect(String(url)).toBe(POLICY_URL);
        return jsonResponse(policyPayload());
      },
    );
    render(<OptimizationPolicySection />);
    expect(await screen.findByTestId("optimization-policy-quality"))
      .toBeTruthy();
    expect(screen.getByTestId("optimization-policy-quality").textContent)
      .toBe("0.8");
    expect(screen.getByTestId("optimization-policy-risk").textContent)
      .toBe("HIGH");
    const weights = screen.getByTestId("optimization-policy-weights")
      .textContent;
    expect(weights).toContain("1");
    expect(screen.queryByTestId("optimization-policy-error")).toBeNull();
  });

  it("shows the error leg when the policy read fails", async () => {
    vi.stubGlobal(
      "fetch",
      async () => jsonResponse({ detail: "down" }, 500),
    );
    render(<OptimizationPolicySection />);
    expect(await screen.findByTestId("optimization-policy-error"))
      .toBeTruthy();
  });
});
