/** @vitest-environment node */
// L0B-05: the built app has a page title plus applied styles, verified on
// the BUILT output only: vite build runs, dist/index.html carries a title
// element, links a css asset, and that asset is non-empty. dist is removed
// afterwards so the tree stays clean.
import { describe, expect, it } from "vitest";

// No @types/node in the offline tree and installs are forbidden, so each
// node import below carries a targeted suppression; vitest supplies the
// runtime and the used surface is tiny (execFileSync, fs helpers, join,
// fileURLToPath, process.execPath).
// @ts-ignore: node types unavailable offline
import { execFileSync } from "node:child_process";
// @ts-ignore: node types unavailable offline
import { existsSync, readFileSync, rmSync, statSync } from "node:fs";
// @ts-ignore: node types unavailable offline
import { join } from "node:path";
// @ts-ignore: node types unavailable offline
import { fileURLToPath } from "node:url";
declare const process: { execPath: string };

const FRONTEND = fileURLToPath(new URL("../../..", import.meta.url));
const DIST = join(FRONTEND, "dist");

describe("l0b05 built title plus styles", () => {
  it("builds dist with a title element and a non-empty css asset", () => {
    rmSync(DIST, { recursive: true, force: true });
    try {
      execFileSync(
        process.execPath,
        [join("node_modules", "vite", "bin", "vite.js"), "build"],
        { cwd: FRONTEND, stdio: "pipe", timeout: 120000 },
      );
      const html = readFileSync(join(DIST, "index.html"), "utf8");
      expect(html).toMatch(/<title>[^<]+<\/title>/);
      const hrefs = [...html.matchAll(/<link[^>]+href="([^"]+\.css)"/g)].map(
        (match) => match[1] as string,
      );
      expect(hrefs.length).toBeGreaterThanOrEqual(1);
      for (const href of hrefs) {
        const asset = join(DIST, href.replace(/^\//, ""));
        expect(existsSync(asset)).toBe(true);
        expect(statSync(asset).size).toBeGreaterThan(0);
      }
    } finally {
      rmSync(DIST, { recursive: true, force: true });
    }
  }, 180000);
});
