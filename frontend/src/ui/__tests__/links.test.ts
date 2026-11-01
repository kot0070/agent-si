/** @vitest-environment node */
// FXLINK: links must stay readable on both themes. base.css carries no
// hard-coded link palette: a, a:visited and a:focus-visible all resolve
// through the existing --agent-si-accent token, which tokens.css defines
// per theme (dark default plus light override).
import { describe, expect, it } from "vitest";

// @ts-ignore: node types unavailable offline
import { readFileSync } from "node:fs";
// @ts-ignore: node types unavailable offline
import { fileURLToPath } from "node:url";

const UI = fileURLToPath(new URL("..", import.meta.url));
const BASE = `${UI}/base.css`;
const TOKENS = `${UI}/tokens.css`;

describe("fxlink themed link colors", () => {
  it("styles a, a:visited and a:focus-visible via --agent-si-accent", () => {
    const css = readFileSync(BASE, "utf8");
    expect(css).toMatch(/a\s*\{[^}]*color:\s*var\(--agent-si-accent\)/);
    expect(css).toMatch(/a:visited\s*\{[^}]*color:\s*var\(--agent-si-accent\)/);
    expect(css).toMatch(/a:focus-visible\s*\{[^}]*var\(--agent-si-accent\)/);
    expect(css).not.toMatch(/#0000ee/i);
    expect(css).not.toMatch(/rgb\(\s*0\s*,\s*0\s*,\s*238\s*\)/);
  });

  it("defines --agent-si-accent for both dark and light themes", () => {
    const tokens = readFileSync(TOKENS, "utf8");
    const dark = tokens.match(
      /:root\s*,?\s*\[data-theme="dark"\]\s*\{([^}]*)\}/,
    );
    const light = tokens.match(/\[data-theme="light"\]\s*\{([^}]*)\}/);
    expect(dark?.[1]).toMatch(/--agent-si-accent:\s*#[0-9a-f]{6}/i);
    expect(light?.[1]).toMatch(/--agent-si-accent:\s*#[0-9a-f]{6}/i);
    const darkAccent = dark?.[1].match(/--agent-si-accent:\s*(#[0-9a-f]{6})/i)?.[1].toLowerCase();
    const lightAccent = light?.[1].match(/--agent-si-accent:\s*(#[0-9a-f]{6})/i)?.[1].toLowerCase();
    expect(darkAccent).toBeTruthy();
    expect(lightAccent).toBeTruthy();
    expect(darkAccent).not.toBe(lightAccent);
  });
});
