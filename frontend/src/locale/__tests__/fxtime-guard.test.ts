/** @vitest-environment node */
// FXTIME guard: no direct locale time formatting outside the one helper.
// Any toLocaleString/toLocaleTimeString/toLocaleDateString/Intl.DateTimeFormat
// in non-test frontend/src FAILS: every screen time routes through
// formatScreenTime in frontend/src/locale/index.ts.
import { describe, expect, it } from "vitest";
// @ts-ignore: node types unavailable offline
import { readdirSync, readFileSync, statSync } from "node:fs";
// @ts-ignore: node types unavailable offline
// @ts-ignore: node types unavailable offline
import { join, relative } from "node:path";
// @ts-ignore: node types unavailable offline
import { fileURLToPath } from "node:url";

const FRONTEND = fileURLToPath(new URL("../../..", import.meta.url));
const SRC = join(FRONTEND, "src");

const BANNED =
  /toLocaleString|toLocaleTimeString|toLocaleDateString|Intl\.DateTimeFormat/;

function walk(dir: string, out: string[]): void {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    // @ts-ignore: node types unavailable offline
    if (statSync(full).isDirectory()) {
      if (name === "__tests__") {
        continue;
      }
      walk(full, out);
      continue;
    }
    if (!/\.tsx?$/.test(name) || /\.test\.tsx?$/.test(name)) {
      continue;
    }
    const text = readFileSync(full, "utf8");
    const lines = text.split("\n");
    lines.forEach((line: string, index: number) => {
      if (BANNED.test(line)) {
        out.push(`${relative(SRC, full)}:${index + 1}: ${line.trim()}`);
      }
    });
  }
}

describe("fxtime guard: one screen-time helper", () => {
  it("has zero direct locale time calls in non-test sources", () => {
    const hits: string[] = [];
    walk(SRC, hits);
    expect(hits).toEqual([]);
  });

  it("exposes formatScreenTime from the locale module", () => {
    const text = readFileSync(join(SRC, "locale", "index.ts"), "utf8");
    expect(text).toContain("export function formatScreenTime");
  });

  it("wires chat and run moments through the helper", () => {
    const chat = readFileSync(join(SRC, "chat", "index.tsx"), "utf8");
    expect(chat).toContain("formatScreenTime");
    const views = readFileSync(join(SRC, "projects", "viewsApi.ts"), "utf8");
    expect(views).toContain("formatScreenTime");
  });
});
