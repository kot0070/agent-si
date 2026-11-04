/** @vitest-environment jsdom */
// PLANB X6a (DEFECT-33): the Team now model name is not cut at a fixed
// 16ch; it takes the free room of the row and ellipsises only when full.
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { readFileSync } from "node:fs";
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { dirname, join } from "node:path";
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { shortModelName } from "../Inspector";

const rawCss: string = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../ui/shell.css"),
  "utf-8",
);
const css = rawCss.replace(/\/\*[\s\S]*?\*\//g, "");

function rulesFor(selector: string): string[] {
  const out: string[] = [];
  const pattern = /([^{}]+)\{([^{}]*)\}/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(css)) !== null) {
    const names = (match[1] ?? "").split(",").map((name) => name.trim());
    if (names.includes(selector)) {
      out.push(match[2] ?? "");
    }
  }
  return out;
}

describe("PLANB X6a team model name room", () => {
  it("the team line model span has no fixed character cut", () => {
    const rules = rulesFor(".fx-team-line .fx-truncate");
    expect(rules.length).toBeGreaterThan(0);
    expect(rules.join(";")).not.toMatch(/max-width:\s*\d+ch/);
    expect(rules.join(";")).toMatch(/max-width:\s*none/);
    expect(rules.join(";")).toMatch(/flex:\s*0 1 auto/);
    expect(rulesFor(".fx-team-line > span").join(";")).toMatch(/flex:\s*0 0 auto/);
  });

  it("the short name keeps the whole local model tag", () => {
    expect(shortModelName("ollama/muse-glimmer:30b")).toBe("muse-glimmer:30b");
  });
});
