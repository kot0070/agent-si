/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FirstRunFlow } from "../FirstRunFlow";
import { resetLocaleForTests, setLocale } from "../../../locale/index";
import en from "../../../locale/en.json";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("K07L0D3 LIVE0-05 wizard setup steps", () => {
  it("renders every required setup step in order with the first current", () => {
    const { container } = render(<FirstRunFlow onComplete={() => undefined} />);
    expect(screen.getByText(en.firstrun.title)).toBeTruthy();
    const ordered = [
      en.firstrun.steps.connectProvider,
      en.firstrun.steps.oneClickTeam,
      en.firstrun.steps.projectFolder,
      en.firstrun.steps.firstTask,
    ];
    for (const title of ordered) {
      expect(screen.getByText(title)).toBeTruthy();
    }
    const items = container.querySelectorAll("ol > li");
    expect(items.length).toBe(4);
    expect(items[0]?.textContent).toBe(ordered[0]);
    expect(items[3]?.textContent).toBe(ordered[3]);
    expect(container.querySelectorAll('li[aria-current="step"]').length).toBe(1);
  });

  it("walks Next to the first-task form then completes", () => {
    let done = false;
    render(<FirstRunFlow onComplete={() => { done = true; }} />);
    fireEvent.click(screen.getByRole("button", { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole("button", { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole("button", { name: en.firstrun.next }));
    expect(screen.getByRole("heading", { name: en.tasks.creator.title })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.tasks.creator.create }));
    expect(done).toBe(true);
  });
});
