// J8: one project-name source; no-project topbar reads "No project yet";
// the empty projects view keeps the create form in view.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { ApiClientProvider } from '../../app/ApiClientProvider';
import { FakeApiClient } from '../../api/__tests__/fakeApiClient';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import { TopBar } from '../TopBar';
import { ProjectsPage } from '../../projects/ProjectsPage';
import { ProjectListProvider } from '../../projects/projectList';

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderTopbar(client: FakeApiClient): void {
  const router = createMemoryRouter(
    [{ path: '/', element: <TopBar projectId={null} /> }],
    { initialEntries: ['/'] },
  );
  render(
    <ApiClientProvider client={client}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe('J8 no-project topbar and create form', () => {
  it('topbar names the empty state "No project yet"', async () => {
    renderTopbar(new FakeApiClient({ projects: [] }));
    const select = (await screen.findByTestId('topbar-project')) as HTMLSelectElement;
    expect(select.textContent).toContain('No project yet');
    expect(select.textContent).not.toContain('Select a project');
  });

  it('empty projects view keeps the create form in view', async () => {
    const router = createMemoryRouter(
      [
        {
          path: '/projects',
          element: (
            <ProjectListProvider>
              <ProjectsPage />
            </ProjectListProvider>
          ),
        },
      ],
      { initialEntries: ['/projects'] },
    );
    render(
      <ApiClientProvider client={new FakeApiClient({ projects: [] })}>
        <RouterProvider router={router} />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId('project-add-form')).toBeTruthy();
    expect(await screen.findByTestId('project-add-name')).toBeTruthy();
    expect(await screen.findByTestId('project-add-submit')).toBeTruthy();
  });
});
