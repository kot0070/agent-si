/** @vitest-environment jsdom */
// FXUIB-B3/B6: saved picks show after mount (network GET only); an empty
// pool shows a hint and never fires a save.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { PROVIDER_CATALOG } from "./catalog";
import { ChatModelSelector } from "./ChatModelSelector";
import { RolePoolPicker } from "./RolePoolPicker";
import type { PoolOption } from "./RolePoolPicker";
import { resetLocaleForTests, setLocale } from "../../locale/index";

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const OPTIONS: PoolOption[] = [
  { key: "k1", label: "L1", providerId: "pa", modelId: "pa/a-1" },
  { key: "k2", label: "L2", providerId: "pb", modelId: "pb/b-1" },
];

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("FXUIB-B3 saved picks show after mount", () => {
  it("chat selector shows the saved model after mount", async () => {
    vi.stubGlobal(
      "fetch",
      async (url: unknown) =>
        String(url).startsWith("/api/v1/roles/chat-model")
          ? jsonBody({ project_id: "local", model_id: "openai/gpt-4o-mini" })
          : jsonBody({}, 404),
    );
    render(
      <ChatModelSelector
        project_id="local"
        states={{
          openai: {
            presetId: "openai",
            connected: true,
            enabledModels: ["openai/gpt-4o-mini", "openai/gpt-4o"],
          },
        }}
        catalog={PROVIDER_CATALOG}
      />,
    );
    const select = await screen.findByLabelText("Chat model");
    await waitFor(() => {
      expect((select as HTMLSelectElement).value).toBe("openai/gpt-4o-mini");
    });
  });

  it("role pool picker shows the saved pinned pick after mount and never saves on mount", async () => {
    const onChange = vi.fn();
    vi.stubGlobal(
      "fetch",
      async (url: unknown) =>
        String(url).startsWith("/api/v1/routing/role")
          ? jsonBody({
              profile: {
                role: "worker",
                project_id: "local",
                mode: "PINNED",
                provider: "pa",
                model: "pa/a-1",
              },
              binding: { strategy: "AUTO", members: [] },
            })
          : jsonBody({}, 404),
    );
    render(
      <RolePoolPicker role="worker" project_id="local" options={OPTIONS} onChange={onChange} />,
    );
    const picker = await screen.findByTestId("role-pool-picker");
    await waitFor(() => {
      expect(
        (within(picker).getByRole("combobox") as HTMLSelectElement).value,
      ).toBe("k1");
    });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("role pool picker shows the saved pool members after mount", async () => {
    vi.stubGlobal(
      "fetch",
      async (url: unknown) =>
        String(url).startsWith("/api/v1/routing/role")
          ? jsonBody({
              profile: {
                role: "worker",
                project_id: "local",
                mode: "pool",
              },
              binding: {
                strategy: "FALLBACK_ORDER",
                members: [{ provider: "pa", model: "pa/a-1" }],
              },
            })
          : jsonBody({}, 404),
    );
    render(<RolePoolPicker role="worker" project_id="local" options={OPTIONS} />);
    const picker = await screen.findByTestId("role-pool-picker");
    await waitFor(() => {
      expect(
        (within(picker).getByLabelText("L1") as HTMLInputElement).checked,
      ).toBe(true);
    });
    expect(
      (within(picker).getByLabelText("L2") as HTMLInputElement).checked,
    ).toBe(false);
  });
});

describe("FXUIB-B6 empty pool hint, no doomed save", () => {
  it("pool mode with nothing picked shows the hint and fires no save", async () => {
    const onChange = vi.fn();
    vi.stubGlobal("fetch", async () => jsonBody({}, 404));
    render(
      <RolePoolPicker role="worker" project_id="local" options={OPTIONS} onChange={onChange} />,
    );
    await screen.findByTestId("role-pool-picker");
    fireEvent.click(screen.getByLabelText("Model pool"));
    expect(await screen.findByTestId("pool-empty-hint")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText("L1"));
    expect(screen.queryByTestId("pool-empty-hint")).toBeNull();
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toMatchObject({
      mode: "pool",
      poolKeys: ["k1"],
    });
  });
});
