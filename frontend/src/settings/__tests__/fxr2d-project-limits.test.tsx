// U4: settings step buttons say Save, fields name their limit + unit
// with one hint line; the budget line is spaced, not glued.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ProjectLimitsSection } from '../projectLimits';
import { resetLocaleForTests, setLocale } from '../../locale/index';

const PROJECT_ID = 'p-u4';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function installFetch(): void {
  vi.stubGlobal(
    'fetch',
    async (url: unknown, init?: { method?: string; body?: string }) => {
      const target = String(url);
      if (target.includes('/api/v1/roles/parallel')) {
        return jsonResponse({ project_id: PROJECT_ID, max_parallel_parts: 1 });
      }
      if (target.includes('/api/v1/budget')) {
        return jsonResponse({
          project_id: PROJECT_ID,
          budget: {
            hard_limit: '5.00',
            spent: '0',
            reserved: '0',
            currency: 'USD',
            provider_spend_caps: {},
            provider_spending: {},
          },
        });
      }
      return jsonResponse({
        project_id: PROJECT_ID,
        task_max_steps: 40,
        chat_max_steps: 15,
      });
    },
  );
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  installFetch();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('U4 project limits read as limits', () => {
  it('save buttons say Save and fields name limit + unit with one hint', async () => {
    render(<ProjectLimitsSection projectId={PROJECT_ID} />);
    await screen.findByTestId('project-limits-section');
    const saves = [
      await screen.findByTestId('project-limits-save'),
      await screen.findByTestId('project-limits-parallel-save'),
      await screen.findByTestId('project-limits-caps-save'),
    ];
    for (const button of saves) {
      expect(button.textContent).toBe('Save');
    }
    const taskLabel = document.querySelector('label[for="project-limits-task"]');
    const chatLabel = document.querySelector('label[for="project-limits-chat"]');
    expect(taskLabel?.textContent).toContain('steps');
    expect(chatLabel?.textContent).toContain('steps');
    expect(await screen.findByTestId('project-limits-steps-hint')).toBeTruthy();
  });

  it('budget line is spaced and caps carry their own label', async () => {
    render(<ProjectLimitsSection projectId={PROJECT_ID} />);
    const budget = await screen.findByTestId('project-limits-budget');
    expect(budget.textContent).toContain('0 / 5.00 USD');
    expect(budget.textContent).not.toMatch(/Cost0|Вартість0/);
    const capsLabel = document.querySelector('label[for="project-limits-caps"]');
    expect(capsLabel?.textContent).not.toContain('Cost');
  });
});
