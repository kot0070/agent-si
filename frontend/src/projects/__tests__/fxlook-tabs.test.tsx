/** @vitest-environment jsdom */
// FXLOOK D1+D7 RED: one shared single-row tab strip. Real component
// render (fetch never touched: pure component), layout faked by
// redefining the lane's scroll metrics (jsdom has no layout).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import {
  ProjectTabsNav,
  TABS_SCROLL_STEP,
} from "../ProjectTabsNav";

function mockLane(scroller: HTMLElement, scrollLeftValue: number): void {
  let left = scrollLeftValue;
  Object.defineProperty(scroller, "scrollWidth", {
    configurable: true,
    get: () => 2000,
  });
  Object.defineProperty(scroller, "clientWidth", {
    configurable: true,
    get: () => 400,
  });
  Object.defineProperty(scroller, "scrollLeft", {
    configurable: true,
    get: () => left,
    set: (value: number) => {
      left = value;
    },
  });
}

function lane(): HTMLElement {
  const wrap = screen.getByTestId("project-tabs");
  const scroller = wrap.querySelector(".fxpv-tabs-scroll");
  if (scroller === null) {
    throw new Error("missing .fxpv-tabs-scroll lane");
  }
  return scroller as HTMLElement;
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  const proto = window.HTMLElement.prototype as unknown as Record<
    string,
    unknown
  >;
  if (typeof proto["scrollIntoView"] !== "function") {
    proto["scrollIntoView"] = vi.fn();
  } else {
    vi.spyOn(window.HTMLElement.prototype, "scrollIntoView").mockImplementation(
      () => undefined,
    );
  }
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("FXLOOK D1 single-row tab strip", () => {
  it("renders chat + 15 data tabs in one nowrap lane", () => {
    render(<ProjectTabsNav selected="overview" onSelect={() => undefined} />);
    expect(screen.getByTestId("project-chat-tab")).toBeTruthy();
    expect(
      document.querySelectorAll('[data-testid^="project-menu-"]').length,
    ).toBe(15);
    const nav = document.querySelector("nav.fxpv-tabs");
    expect(nav).toBeTruthy();
  });

  it("shows no arrows without overflow, next arrow with right overflow", () => {
    render(<ProjectTabsNav selected="overview" onSelect={() => undefined} />);
    expect(screen.queryByTestId("project-tabs-next")).toBeNull();
    expect(screen.queryByTestId("project-tabs-prev")).toBeNull();
    mockLane(lane(), 0);
    fireEvent.scroll(lane());
    expect(screen.getByTestId("project-tabs-next")).toBeTruthy();
    expect(screen.queryByTestId("project-tabs-prev")).toBeNull();
  });

  it("shows the prev arrow once scrolled right", () => {
    render(<ProjectTabsNav selected="overview" onSelect={() => undefined} />);
    mockLane(lane(), 320);
    fireEvent.scroll(lane());
    expect(screen.getByTestId("project-tabs-prev")).toBeTruthy();
  });

  it("each arrow click scrolls exactly 160px", () => {
    render(<ProjectTabsNav selected="overview" onSelect={() => undefined} />);
    mockLane(lane(), 0);
    fireEvent.scroll(lane());
    const scroller = lane();
    scroller.scrollBy = vi.fn();
    fireEvent.click(screen.getByTestId("project-tabs-next"));
    expect(scroller.scrollBy).toHaveBeenCalledWith({
      left: TABS_SCROLL_STEP,
    });
    expect(TABS_SCROLL_STEP).toBe(160);
  });

  it("ArrowRight/Home/End move focus across tabs", () => {
    render(<ProjectTabsNav selected="overview" onSelect={() => undefined} />);
    const chat = screen.getByTestId("project-chat-tab");
    const overview = screen.getByTestId("project-menu-overview");
    chat.focus();
    fireEvent.keyDown(chat, { key: "ArrowRight" });
    expect(document.activeElement).toBe(overview);
    fireEvent.keyDown(overview, { key: "End" });
    const tabs = Array.from(
      document.querySelectorAll("button.fxpv-tab"),
    );
    expect(document.activeElement).toBe(tabs[tabs.length - 1]);
    fireEvent.keyDown(document.activeElement as Element, { key: "Home" });
    expect(document.activeElement).toBe(chat);
  });

  it("scrolls the selected tab into view (nearest/nearest)", () => {
    render(<ProjectTabsNav selected="tasks" onSelect={() => undefined} />);
    const selected = screen.getByTestId("project-menu-tasks");
    expect(selected.className).toContain("fxpv-tab-selected");
    expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalledWith({
      block: "nearest",
      inline: "nearest",
    });
  });
});

describe("FXLOOK D7 chat tab reads as a tab", () => {
  it("chat tab carries the same tab class, selected gets aria-current", () => {
    const { rerender } = render(
      <ProjectTabsNav selected="overview" onSelect={() => undefined} />,
    );
    const chat = screen.getByTestId("project-chat-tab");
    expect(chat.className).toContain("fxpv-tab");
    expect(chat.className).not.toContain("fxpv-tab-selected");
    expect(chat.getAttribute("aria-current")).toBeNull();
    rerender(<ProjectTabsNav selected="chat" onSelect={() => undefined} />);
    const chatSelected = screen.getByTestId("project-chat-tab");
    expect(chatSelected.className).toContain("fxpv-tab-selected");
    expect(chatSelected.getAttribute("aria-current")).toBe("true");
  });

  it("shell.css gives the chat tab the same border + fill as the others", () => {
    // FXLOOK D7: same read pattern as fxr2d-tabs.test.tsx (node fs,
    // repo-relative path, ts-ignored like the existing CSS tests).
    // @ts-ignore: node fs available offline in this repo's tests
    const { readFileSync } = require("node:fs");
    const css: string = readFileSync("src/ui/shell.css", "utf8");
    const restRule = css.match(
      /nav\s+button\[data-testid="project-chat-tab"\][^{]*\{[^}]*\}/,
    );
    expect(restRule).toBeTruthy();
    expect(restRule?.[0]).toMatch(/border:\s*1px solid/);
    expect(restRule?.[0]).toMatch(/background-color:/);
  });
});
