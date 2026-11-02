// J11: keyboard path first — a skip link to the composer, the centre
// column before either rail in tab order, a visible focus ring on every
// control, and no positive tabindex to trap the order.
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
const shellCss = readFileSync(join(here, '../../ui/shell.css'), 'utf-8');

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function stubEmpty(): void {
  vi.stubGlobal(
    'fetch',
    async (input: unknown) => {
      const url = String(input);
      if (url === '/api/v1/projects') {
        return jsonBody({ projects: [] });
      }
      if (url === '/api/v1/agents/live') {
        return jsonBody({ agents: [] });
      }
      return jsonBody({ code: 'J11_UNEXPECTED_API' }, 404);
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

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: '*', element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new HttpApiClient()}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe('J11 keyboard path', () => {
  it('skip link names the composer and lands on a real target', async () => {
    stubEmpty();
    renderAppAt('/');
    const skip = await screen.findByTestId('skip-to-composer');
    expect(skip.getAttribute('href')).toBe('#chat-prompt');
    expect(skip.textContent).toBe('Skip to composer');
    const prompt = await screen.findByTestId('chat-prompt');
    expect(prompt.getAttribute('id')).toBe('chat-prompt');
  });

  it('tab order reads the centre before either rail', async () => {
    stubEmpty();
    renderAppAt('/');
    const shell = await screen.findByTestId('app-shell');
    const main = shell.querySelector('[data-testid="app-main"]') as Element;
    const sidebar = shell.querySelector('[data-testid="sidebar"]') as Element;
    const inspector = shell.querySelector('[data-testid="inspector"]') as Element;
    expect(main).toBeTruthy();
    // No positive tabindex anywhere: DOM order is the tab order.
    for (const el of shell.querySelectorAll('[tabindex]')) {
      expect(Number((el as HTMLElement).getAttribute('tabindex'))).toBeLessThanOrEqual(0);
    }
    const FOLLOWING = 4;
    expect(Boolean(main.compareDocumentPosition(sidebar) & FOLLOWING)).toBe(true);
    expect(Boolean(main.compareDocumentPosition(inspector) & FOLLOWING)).toBe(true);
  });

  it('every control keeps a visible focus ring, including the skip link', () => {
    expect(shellCss).toContain('div[data-testid="app-shell"] :focus-visible');
    expect(shellCss).toContain('skip-to-composer');
    expect(shellCss).toMatch(/skip-to-composer[^{]*\{[^}]*position:\s*absolute/);
    expect(shellCss).toMatch(/skip-to-composer.*:focus-visible/);
  });
});
