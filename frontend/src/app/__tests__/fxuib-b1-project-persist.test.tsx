/** @vitest-environment jsdom */
// FXUIB-B1: the saved project pick survives remount; a stored id that is
// no longer served falls back to the first row. Real provider, no mocks
// except the ApiClient instance.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ApiClientProvider, useCurrentProject } from "../ApiClientProvider";
import { resolveFirstProject } from "../App";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";

function Probe(): React.JSX.Element {
  const current = useCurrentProject();
  return (
    <div>
      <span data-testid="picked">{current.projectId ?? "none"}</span>
      <button type="button" onClick={() => current.select("proj-b")}>
        pick-b
      </button>
    </div>
  );
}

function renderProbe(): void {
  render(
    <ApiClientProvider client={new FakeApiClient()}>
      <Probe />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

describe("FXUIB-B1 persisted project pick", () => {
  it("select B, remount, B", () => {
    renderProbe();
    expect(screen.getByTestId("picked").textContent).toBe("none");
    fireEvent.click(screen.getByText("pick-b"));
    expect(screen.getByTestId("picked").textContent).toBe("proj-b");
    cleanup();
    renderProbe();
    expect(screen.getByTestId("picked").textContent).toBe("proj-b");
  });

  it("resolveFirstProject keeps a served pick, falls back otherwise", () => {
    const rows = [{ project_id: "a" }, { project_id: "b" }].map((row) => ({
      ...row,
      name: row.project_id,
      created_at: "t-0",
    }));
    expect(resolveFirstProject(rows, "b")).toBeNull();
    expect(resolveFirstProject(rows, "gone")).toBe("a");
    expect(resolveFirstProject(rows, null)).toBe("a");
    expect(resolveFirstProject([], null)).toBeNull();
  });
});
