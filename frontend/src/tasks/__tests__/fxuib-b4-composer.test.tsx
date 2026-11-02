/** @vitest-environment jsdom */
// FXUIB-B4: the task composer draft survives remount (sessionStorage
// per project).
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
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

describe("FXUIB-B4 composer draft kept per project", () => {
  it("type, remount, text is there; other projects are separate", () => {
    const client = new FakeApiClient();
    const ui = (
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-1" />
      </ApiClientProvider>
    );
    const first = render(ui);
    fireEvent.change(screen.getByTestId("composer-title"), {
      target: { value: "my draft title" },
    });
    fireEvent.change(screen.getByTestId("composer-scope"), {
      target: { value: "a, b" },
    });
    first.unmount();
    render(ui);
    expect(
      (screen.getByTestId("composer-title") as HTMLInputElement).value,
    ).toBe("my draft title");
    expect(
      (screen.getByTestId("composer-scope") as HTMLInputElement).value,
    ).toBe("a, b");
    cleanup();
    render(
      <ApiClientProvider client={client}>
        <TaskComposer projectId="p-2" />
      </ApiClientProvider>,
    );
    expect(
      (screen.getByTestId("composer-title") as HTMLInputElement).value,
    ).toBe("");
  });
});
