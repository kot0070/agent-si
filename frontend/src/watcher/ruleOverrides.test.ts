// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_SIGNAL,
  DEFAULT_WATCHER_POWER,
  SIGNAL_TARGETS,
  WATCHER_POWERS,
  cardPower,
  cardSignal,
  isCardEnabled,
  isStrongPower,
  isWatcherEnabled,
  setCardEnabled,
  setCardPower,
  setCardSignal,
  setWatcherEnabled,
} from "./ruleOverrides";

beforeEach(() => {
  window.localStorage.clear();
});

describe("ruleOverrides (RED: module missing)", () => {
  it("leaves a fresh project watcher and every card on", () => {
    expect(isWatcherEnabled("proj-new")).toBe(true);
    expect(isCardEnabled("card-guard", "proj-new")).toBe(true);
  });

  it("turns one card off and survives a reload", () => {
    setCardEnabled("card-guard", false, "proj-a");
    expect(isCardEnabled("card-guard", "proj-a")).toBe(false);
    expect(isCardEnabled("card-hang", "proj-a")).toBe(true);
  });

  it("defaults power to observe and director, flags strong powers", () => {
    expect(DEFAULT_WATCHER_POWER).toBe("observe");
    expect(DEFAULT_SIGNAL).toBe("director");
    expect([...WATCHER_POWERS]).toEqual([
      "observe",
      "restart-once",
      "pause",
      "stop",
    ]);
    expect([...SIGNAL_TARGETS]).toEqual(["manager", "director", "user"]);
    expect(isStrongPower("observe")).toBe(false);
    expect(isStrongPower("restart-once")).toBe(true);
    expect(isStrongPower("pause")).toBe(true);
    expect(isStrongPower("stop")).toBe(true);
  });

  it("stores power and signal per card and project", () => {
    setCardPower("card-tamper", "stop", "proj-a");
    setCardSignal("card-tamper", "user", "proj-a");
    expect(cardPower("card-tamper", "proj-a")).toBe("stop");
    expect(cardSignal("card-tamper", "proj-a")).toBe("user");
    expect(cardPower("card-tamper", "proj-b")).toBe("observe");
  });

  it("turns the project watcher off without touching cards", () => {
    setWatcherEnabled(false, "proj-a");
    expect(isWatcherEnabled("proj-a")).toBe(false);
    expect(isCardEnabled("card-guard", "proj-a")).toBe(true);
  });
});
