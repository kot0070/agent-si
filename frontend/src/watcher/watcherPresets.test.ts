// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import {
  DEFAULT_WATCHER_PRESET,
  PRESET_TABLE,
  WATCHER_PRESETS,
  loadWatcherPreset,
  saveWatcherPreset,
} from "./watcherPresets";

beforeEach(() => {
  window.localStorage.clear();
});

describe("watcherPresets (RED: module missing)", () => {
  it("defaults a fresh project to the standard preset", () => {
    expect(loadWatcherPreset("proj-new")).toBe(DEFAULT_WATCHER_PRESET);
    expect(DEFAULT_WATCHER_PRESET).toBe("standard");
  });

  it("lists cautious, standard and strict with their installed cards", () => {
    expect([...WATCHER_PRESETS]).toEqual(["cautious", "standard", "strict"]);
    expect([...(PRESET_TABLE["cautious"] ?? [])]).toEqual(["card-hang"]);
    expect([...(PRESET_TABLE["standard"] ?? [])]).toEqual([
      "card-hang",
      "card-guard",
    ]);
    expect([...(PRESET_TABLE["strict"] ?? [])]).toEqual([
      "card-hang",
      "card-guard",
      "card-tamper",
    ]);
  });

  it("marks strict and survives a reload", () => {
    saveWatcherPreset("strict", "proj-a");
    expect(loadWatcherPreset("proj-a")).toBe("strict");
  });

  it("keeps presets separate per project", () => {
    saveWatcherPreset("cautious", "proj-a");
    expect(loadWatcherPreset("proj-b")).toBe("standard");
  });
});
