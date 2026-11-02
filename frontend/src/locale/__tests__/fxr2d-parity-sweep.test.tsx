// U6 parity sweep lock: the committed allowlist stays valid JSON with no
// duplicates, and no entry goes stale (every listed key must still be
// genuinely drifted, so exceptions never outlive the drift).
/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { readFileSync } from 'node:fs';
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { dirname, join } from 'node:path';
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { fileURLToPath } from 'node:url';
import en from '../en.json';
import uk from '../uk.json';

const here = dirname(fileURLToPath(import.meta.url));

function leaves(node: unknown, prefix = ''): Set<string> {
  const out = new Set<string>();
  if (node !== null && typeof node === 'object' && !Array.isArray(node)) {
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      for (const leaf of leaves(value, prefix === '' ? key : `${prefix}.${key}`)) {
        out.add(leaf);
      }
    }
  } else {
    out.add(prefix);
  }
  return out;
}

describe('U6 parity allowlist hygiene', () => {
  it('allowlist is valid, duplicate-free, and never stale', () => {
    const raw = readFileSync(join(here, '../parity-allowlist.json'), 'utf-8');
    const allowlist = JSON.parse(raw) as unknown;
    expect(Array.isArray(allowlist)).toBe(true);
    const entries = allowlist as string[];
    expect(new Set(entries).size).toBe(entries.length);
    const dts = readFileSync(join(here, '../../settings/k07b-iface.d.ts'), 'utf-8');
    const block = /export type LocaleKey =([\s\S]*?);/.exec(dts)?.[1] ?? '';
    const union = new Set(
      [...block.matchAll(/'([^']+)'/g)].map((m) => m[1]),
    );
    const enKeys = leaves(en as unknown);
    const ukKeys = leaves(uk as unknown);
    for (const key of entries) {
      const langDrift = enKeys.has(key) !== ukKeys.has(key);
      const unionDrift = union.has(key) !== (enKeys.has(key) || ukKeys.has(key));
      expect(langDrift || unionDrift).toBe(true);
    }
  });
});
