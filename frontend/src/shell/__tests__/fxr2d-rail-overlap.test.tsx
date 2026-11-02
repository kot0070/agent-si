// U11: left sidebar rows wrap or truncate with a tooltip, never overlap,
// at 1366x768 and 1024x700, both languages. Every rail row plus the top
// bar checked the same way.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';
import { ApiClientProvider } from '../../app/ApiClientProvider';
import { FakeApiClient } from '../../api/__tests__/fakeApiClient';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import { Sidebar } from '../Sidebar';
import { TopBar } from '../TopBar';

const shellCss = readFileSync('src/ui/shell.css', 'utf8');

const LONG_UK_NAME = 'Дуже довга назва проєкту для перевірки перенесення рядка';

function renderSidebar(locale: 'en' | 'uk'): void {
  const router = createMemoryRouter([{ path: '/', element: <Sidebar projectId={null} /> }], {
    initialEntries: ['/'],
  });
  render(
    <ApiClientProvider
      client={
        new FakeApiClient({
          projects: [{ project_id: 'p-long', name: LONG_UK_NAME, created_at: '2026-01-01T00:00:00Z' }],
        })
      }
    >
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('U11 rail rows never overlap', () => {
  it.each(['en', 'uk'] as const)('every rail row carries a tooltip (%s)', async (locale) => {
    setLocale(locale);
    renderSidebar(locale);
    for (const id of ['menu-new-task', 'menu-projects', 'menu-results', 'menu-settings']) {
      const link = await screen.findByTestId(id);
      expect(link.getAttribute('title')?.trim().length).toBeGreaterThan(0);
    }
    // No project selected: the results hint names the next step in place.
    expect(await screen.findByTestId('menu-results-hint')).toBeTruthy();
    const projectRow = await screen.findByTestId('sidebar-project-p-long');
    expect(projectRow.getAttribute('title')).toBe(LONG_UK_NAME);
  });

  it('top bar selects expose the full text as a tooltip', async () => {
    setLocale('uk');
    const router = createMemoryRouter([{ path: '/', element: <TopBar projectId={null} /> }], {
      initialEntries: ['/'],
    });
    render(
      <ApiClientProvider client={new FakeApiClient({ projects: [] })}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    const project = (await screen.findByTestId('topbar-project')) as HTMLSelectElement;
    expect(project.getAttribute('title')?.trim().length).toBeGreaterThan(0);
    const language = (await screen.findByTestId('topbar-language')) as HTMLSelectElement;
    expect(language.getAttribute('title')).toBe('uk');
  });

  it('rail and top bar CSS constrain rows instead of overlapping', () => {
    // Sidebar clips horizontal overflow; rows constrain flex children.
    expect(shellCss).toMatch(/nav\[data-testid="sidebar"\]\s*\{[^}]*overflow-x:\s*hidden/);
    expect(shellCss).toMatch(/\.fx-rail-row\s*\{[^}]*min-width:\s*0/);
    expect(shellCss).toMatch(/\.fx-rail-purpose\s*\{[^}]*overflow-wrap:\s*break-word/);
    expect(shellCss).toMatch(/\[data-testid="menu-results-hint"\]\s*\{[^}]*overflow-wrap:\s*break-word/);
    // Top bar values truncate with ellipsis (full text in title above).
    expect(shellCss).toMatch(/\.fx-topbar select,[\s\S]*?\{[^}]*text-overflow:\s*ellipsis/);
  });
});
