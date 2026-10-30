/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import { TaskComposer } from "../TaskComposer";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe("L0C-02 composer idle never reuses the tasks list empty text", () => {
  it("idle shows no tasks.list.empty and no result", async () => {
    const client = new FakeApiClient({});
    render(
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-1" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("task-composer")).toBeTruthy();
    expect(screen.queryByTestId("composer-result")).toBeNull();
    expect(screen.queryByText(t("tasks.list.empty"))).toBeNull();
  });

  it("create still reaches the entry and shows the typed title", async () => {
    const client = new FakeApiClient({});
    render(
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-1" />
      </ApiClientProvider>,
    );
    fireEvent.change(screen.getByTestId("composer-title"), {
      target: { value: "live task" },
    });
    fireEvent.click(screen.getByTestId("composer-create"));
    const result = await screen.findByTestId("composer-result");
    expect(result.textContent).toContain("live task");
    expect(screen.queryByText(t("tasks.list.empty"))).toBeNull();
  });
});
