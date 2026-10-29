/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {
  Link,
  RouterProvider,
  createMemoryRouter,
  useLocation,
} from 'react-router-dom';
import type { ReactElement } from 'react';
import { ApiClientProvider } from '../../app/ApiClientProvider';
import { FakeApiClient } from '../../api/__tests__/fakeApiClient';
import { resetLocaleForTests, setLocale, t } from '../../locale/index';
import { App } from '../../app/App';
import { ClosingGuard } from '../ClosingGuard';

function stubScheme(dark: boolean): void {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: 375,
  });
  const matchMedia = (query: string) => ({
    matches: query === '(prefers-color-scheme: dark)' && dark,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: matchMedia,
  });
}

function renderAppAt(path: string): void {
  const router = createMemoryRouter([{ path: '*', element: <App /> }], {
    initialEntries: [path],
  });
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

function LocationProbe(): ReactElement {
  const location = useLocation();
  return <span data-testid="guard-location">{location.pathname}</span>;
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale('en');
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe.each([false, true])('k07r2a shell rows (dark=%s)', (dark) => {
  it('D2 exactly one topbar; pairing-strip lives inside it with real pairing status', async () => {
    stubScheme(dark);
    renderAppAt('/');
    const topbar = await screen.findByTestId('topbar');
    expect(topbar.tagName.toLowerCase()).toBe('header');
    expect(document.querySelectorAll('[data-testid="topbar"]').length).toBe(1);
    const strip = await screen.findByTestId('pairing-strip');
    expect(topbar.contains(strip)).toBe(true);
    expect(strip.textContent).toContain(t('shell.topbar.watcher'));
    const badge = strip.textContent ?? '';
    expect(
      badge.includes(t('agents.badge.local')) ||
        badge.includes(t('agents.badge.cloud')),
    ).toBe(true);
  });

  it('D3 settings layout keeps exactly one H2 plus explainer and the Why chip', async () => {
    stubScheme(dark);
    renderAppAt('/settings/general');
    const chip = await screen.findByTestId('settings-why-chip');
    expect(chip.textContent).toBe(t('projects.why_this_model.title'));
    const section = chip.closest('section');
    expect(section).not.toBeNull();
    expect(section?.querySelectorAll('h2').length).toBe(1);
    expect(section?.querySelectorAll('p').length).toBeGreaterThanOrEqual(1);
  });

  it('D4 Stay/Leave confirm on the confirmKey prop, Leave primary, undo restores', async () => {
    stubScheme(dark);
    const router = createMemoryRouter(
      [
        {
          path: '*',
          element: (
            <>
              <ClosingGuard armed confirmKey="shell.closing.confirm">
                <span data-testid="guard-body">guarded</span>
              </ClosingGuard>
              <Link data-testid="guard-go" to="/guard-b">
                go
              </Link>
              <LocationProbe />
            </>
          ),
        },
      ],
      { initialEntries: ['/guard-a', '/guard-b'], initialIndex: 0 },
    );
    render(<RouterProvider router={router} />);
    expect(await screen.findByTestId('guard-body')).toBeTruthy();
    fireEvent.click(screen.getByTestId('guard-go'));
    const confirm = await screen.findByTestId('closing-confirm');
    expect(confirm.textContent).toContain(t('shell.closing.confirm'));
    expect(confirm.getAttribute('aria-label')).toBe(t('shell.closing.confirm'));
    expect(screen.getByTestId('closing-stay').textContent).toBe(
      t('shell.closing.stay'),
    );
    const leave = screen.getByTestId('closing-leave');
    expect(leave.textContent).toBe(t('shell.closing.leave'));
    expect(document.activeElement).toBe(leave);
    fireEvent.click(leave);
    await waitFor(() => {
      expect(screen.getByTestId('guard-location').textContent).toBe('/guard-b');
    });
    expect(screen.queryByTestId('closing-confirm')).toBeNull();
    const undo = await screen.findByTestId('closing-undo');
    expect(undo.textContent).toBe(t('ui.error.retry'));
    fireEvent.click(undo);
    await waitFor(() => {
      expect(screen.getByTestId('guard-location').textContent).toBe('/guard-a');
    });
    expect(screen.queryByTestId('closing-undo')).toBeNull();
    fireEvent.click(screen.getByTestId('guard-go'));
    expect(await screen.findByTestId('closing-confirm')).toBeTruthy();
  });
});
