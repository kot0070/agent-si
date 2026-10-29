// CODER-2 Sable: LIVE0-05 new lane test (REAL FirstRunFlow + REAL /firstrun route).
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { FirstRunFlow } from '../FirstRunFlow';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import en from '../../../locale/en.json';
import { ApiClientProvider } from '../../ApiClientProvider';
import { HttpApiClient } from '../../../api/client';
import { App } from '../../App';

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

function orderedSteps(): string[] {
  return [
    en.firstrun.steps.connectProvider,
    en.firstrun.steps.oneClickTeam,
    en.firstrun.steps.projectFolder,
    en.firstrun.steps.firstTask,
  ];
}

describe('LIVE0-05 sable wizard setup steps from firstrun keys', () => {
  it('renders every required setup step in order with the first current', () => {
    const { container } = render(<FirstRunFlow onComplete={() => undefined} />);
    expect(screen.getByText(en.firstrun.title)).toBeTruthy();
    for (const title of orderedSteps()) {
      expect(screen.getByText(title)).toBeTruthy();
    }
    const items = container.querySelectorAll('ol > li');
    expect(items.length).toBe(4);
    const ordered = orderedSteps();
    expect(items[0]?.textContent).toBe(ordered[0]);
    expect(items[1]?.textContent).toBe(ordered[1]);
    expect(items[2]?.textContent).toBe(ordered[2]);
    expect(items[3]?.textContent).toBe(ordered[3]);
    const current = container.querySelectorAll('li[aria-current="step"]');
    expect(current.length).toBe(1);
    expect(current[0]?.textContent).toBe(en.firstrun.steps.connectProvider);
  });

  it('walks Next through each setup step to the first-task form, then completes', () => {
    let done = false;
    const { container } = render(
      <FirstRunFlow onComplete={() => { done = true; }} />,
    );
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    const current = container.querySelectorAll('li[aria-current="step"]');
    expect(current.length).toBe(1);
    expect(current[0]?.textContent).toBe(en.firstrun.steps.firstTask);
    expect(done).toBe(false);
    expect(screen.getByRole('heading', { name: en.tasks.creator.title })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect(done).toBe(true);
  });

  it('serves the wizard at the /firstrun route path', async () => {
    vi.stubGlobal(
      'fetch',
      async () =>
        new Response(JSON.stringify({ projects: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    );
    const router = createMemoryRouter([{ path: '*', element: <App /> }], {
      initialEntries: ['/firstrun'],
    });
    render(
      <ApiClientProvider client={new HttpApiClient()}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    expect(await screen.findByText(en.firstrun.title)).toBeTruthy();
    for (const title of orderedSteps()) {
      expect(await screen.findByText(title)).toBeTruthy();
    }
  });
});
