// U2: Cloud/Local AI tabs read as labelled plain rows — never chopped
// mid-word, repeats folded, one shared reason, cost named when unknown.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import { ApiClientProvider } from '../../app/ApiClientProvider';
import { FakeApiClient } from '../../api/__tests__/fakeApiClient';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import { ProjectView } from '../ProjectView';
import type { PartRow } from '../../api/iface';

function liveRow(partial: Record<string, unknown>): PartRow {
  return {
    agent: 'agent-1',
    scope: 's-1',
    deliverable: 'part-1',
    status: 'RUNNING',
    ...partial,
  } as PartRow;
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('U2 labelled live rows', () => {
  it('labels every cell, folds the repeat, names unknown cost once', async () => {
    const client = new FakeApiClient({
      projects: [{ project_id: 'p-9', name: 'n-9', created_at: '2026-01-01T00:00:00Z' }],
      tasksByProject: { 'p-9': [] },
      ledgerByProject: { 'p-9': [] },
      budgetByProject: {},
      liveRows: [
        liveRow({
          agent: 'worker-verylongagentnamewithoutbreaks-part-1',
          status: 'RUNNING',
          placement: 'CLOUD',
          role: 'worker',
          model: 'mod-c',
          tokens: { input: 5, output: 5 },
        }),
        liveRow({
          agent: 'c-stuck-1',
          status: 'BLOCKED',
          placement: 'CLOUD',
          role: 'manager',
          model: 'mod-m',
        }),
        liveRow({
          agent: 'c-stuck-2',
          status: 'BLOCKED',
          placement: 'CLOUD',
          role: 'manager',
          model: 'mod-m',
        }),
      ],
    });
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="cloud-ai" />
      </ApiClientProvider>,
    );
    const row = await screen.findByTestId('place-row-worker-verylongagentnamewithoutbreaks-part-1');
    for (const label of ['Role', 'Model', 'Tokens', 'Cost']) {
      expect(within(row).getByText(label)).toBeTruthy();
    }
    // Unknown cost is named, never a bare UNKNOWN beside numbers.
    expect(row.textContent).toContain('cost not known (no price)');
    expect(row.textContent).not.toContain('UNKNOWN');
    // One shared reason for every blocked row, not one per row.
    const notes = await screen.findAllByTestId('live-blocked-note');
    expect(notes).toHaveLength(1);
    expect(document.querySelectorAll('[data-testid="live-blocked-note"]').length).toBe(1);
  });
});
