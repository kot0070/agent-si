// J12: placeholder text meets 4.5:1 in both themes; every context
// legend dot carries the slice name as its text label; spinners freeze
// under prefers-reduced-motion.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { readFileSync } from 'node:fs';
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { dirname, join } from 'node:path';
// @ts-expect-error node types are unavailable in the frontend tsconfig
import { fileURLToPath } from 'node:url';
import { ApiClientProvider } from '../../app/ApiClientProvider';
import { HttpApiClient } from '../../api/client';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import { App } from '../../app/App';

const here = dirname(fileURLToPath(import.meta.url));
const tokensCss = readFileSync(join(here, '../../ui/tokens.css'), 'utf-8');
const baseCss = readFileSync(join(here, '../../ui/base.css'), 'utf-8');
const shellCss = readFileSync(join(here, '../../ui/shell.css'), 'utf-8');

function luminance(hex: string): number {
  const c = hex.replace('#', '');
  const [r, g, b] = [c.slice(0, 2), c.slice(2, 4), c.slice(4, 6)].map((v) => {
    const s = parseInt(v, 16) / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function tokenValue(css: string, block: string, name: string): string | null {
  const m = new RegExp(block + '\\s*\\{([\\s\\S]*?)\\}', 'm').exec(css);
  const body = (m?.[1] ?? '').replace(/\/\*[\s\S]*?\*\//g, '');
  const line = body.split(';').find((l) => l.includes(name));
  return line?.split(':')[1]?.trim() ?? null;
}

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function stubServed(): void {
  vi.stubGlobal(
    'fetch',
    async (input: unknown) => {
      const url = String(input);
      if (url === '/api/v1/projects') {
        return jsonBody({
          projects: [{ project_id: 'p-1', name: 'n-1', created_at: 't-0' }],
        });
      }
      if (url === '/api/v1/agents/live') {
        return jsonBody({
          agents: [
            {
              agent: 'agent-1',
              scope: 's-1',
              deliverable: 'part-1',
              status: 'RUNNING',
              role: 'manager',
              model: 'm-1',
              tokens: { input: 400, output: 600 },
            },
          ],
        });
      }
      if (url.startsWith('/api/v1/tasks')) {
        return jsonBody({ tasks: [] });
      }
      if (url.startsWith('/api/v1/runs/ledger')) {
        return jsonBody({ rows: [] });
      }
      if (url.startsWith('/api/v1/budget')) {
        return jsonBody({ project_id: 'p-1', budget: null });
      }
      if (url.startsWith('/api/v1/chat/history')) {
        return jsonBody({ turns: [] });
      }
      if (url.startsWith('/api/v1/chat/models')) {
        return jsonBody({ project_id: 'p-1', models: [] });
      }
      if (url === '/api/v1/providers') {
        return jsonBody({ providers: [] });
      }
      return jsonBody({ code: 'J12_UNEXPECTED_API' }, 404);
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem('agentsi.firstrun.done', 'true');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('J12 contrast, dot labels, reduced motion', () => {
  it('placeholder color clears 4.5:1 on the input surface in both themes', () => {
    expect(baseCss).toMatch(/::placeholder/);
    expect(baseCss).toMatch(/opacity:\s*1/);
    const darkPh = tokenValue(tokensCss, '\\[data-theme="dark"\\]', '--fx-placeholder');
    const darkBg = tokenValue(tokensCss, '\\[data-theme="dark"\\]', '--fx-input-bg');
    const lightPh = tokenValue(tokensCss, '\\[data-theme="light"\\]', '--fx-placeholder');
    const lightBg = tokenValue(tokensCss, '\\[data-theme="light"\\]', '--fx-input-bg');
    expect(darkPh).toBeTruthy();
    expect(lightPh).toBeTruthy();
    expect(contrast(darkPh as string, darkBg as string)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(lightPh as string, lightBg as string)).toBeGreaterThanOrEqual(4.5);
  });

  it('every context legend dot names its slice', async () => {
    stubServed();
    const router = createMemoryRouter([{ path: '*', element: <App /> }], {
      initialEntries: ['/'],
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    const legend = await screen.findByTestId('ctx-legend');
    const dots = legend.querySelectorAll('.fx-legend-dot');
    expect(dots.length).toBeGreaterThan(0);
    for (const dot of dots) {
      expect(dot.getAttribute('aria-label')).toBeTruthy();
    }
  });

  it('spinners freeze under prefers-reduced-motion', () => {
    const block = /prefers-reduced-motion[\s\S]*?\{([\s\S]*?)\}\s*\}/.exec(shellCss)?.[0] ?? '';
    expect(block).toContain('.fx-spin');
    expect(block).toContain('animation: none');
  });
});
