// Y2 connect step 2: pre-ticked recommended text model, Done warns on
// empty, no duplicated label/id, quoted key prefixes.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import { ConnectDialog } from '../ConnectDialog';
import { PROVIDER_CATALOG, getPreset } from '../catalog';
import { createMemorySecretStore } from '../secretStore';

function stubModels(): void {
  vi.stubGlobal(
    'fetch',
    async (input: unknown, init?: { method?: string }) => {
      const url = String(input);
      const method = (init?.method ?? 'GET').toUpperCase();
      if (url === '/api/v1/providers/openai/models' && method === 'GET') {
        return new Response(
          JSON.stringify({
            models: [
              { model: 'openai/gpt-4o-mini', kb_known: true, price: 0.15 },
              { model: 'openai/gpt-4o', kb_known: true, price: 1 },
              { model: 'openai/whisper-1', kb_known: false },
            ],
            enabled: null,
            source: 'catalog',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        );
      }
      return new Response(JSON.stringify({ code: 'CONTEXT_MISSING' }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      });
    },
  );
}

function renderManage(initialTicked?: string[]): { onModelsDone: ReturnType<typeof vi.fn> } {
  const preset = getPreset(PROVIDER_CATALOG, 'openai');
  expect(preset).toBeDefined();
  const onModelsDone = vi.fn();
  const store = createMemorySecretStore('sess');
  void store.save({
    secret_id: 'openai',
    provider_id: 'openai',
    type: 'api-key',
    scope: 'providers',
    source: 'providers-page',
    created_at: 't',
    last_rotated_at: null,
  });
  render(
    <ConnectDialog
      preset_id="openai"
      preset={preset ?? null}
      open
      store={store}
      initialStep={2}
      initialTicked={initialTicked}
      onClose={() => {}}
      onConnected={() => {}}
      onModelsDone={onModelsDone}
    />,
  );
  return { onModelsDone };
}

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

describe('Y2 connect step 2 model list', () => {
  it('pre-ticks the recommended text model when opened with nothing ticked', async () => {
    stubModels();
    renderManage([]);
    const rows = await screen.findAllByTestId('connect-model-row');
    expect(rows.length).toBe(3);
    const checked = rows
      .map((row) => within(row).getByRole('checkbox') as HTMLInputElement)
      .filter((box) => box.checked);
    expect(checked).toHaveLength(1);
    expect(checked[0].getAttribute('aria-label')).toBe('openai/gpt-4o-mini');
  });

  it('Done with nothing ticked warns and stays open', async () => {
    stubModels();
    const { onModelsDone } = renderManage([]);
    const rows = await screen.findAllByTestId('connect-model-row');
    for (const row of rows) {
      const box = within(row).getByRole('checkbox') as HTMLInputElement;
      if (box.checked) {
        fireEvent.click(box);
      }
    }
    fireEvent.click(screen.getByText('Done'));
    expect(await screen.findByTestId('connect-done-note')).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(onModelsDone).not.toHaveBeenCalled();
  });

  it('never renders a duplicated label/id or a glued sentence', async () => {
    stubModels();
    renderManage(['openai/gpt-4o']);
    const rows = await screen.findAllByTestId('connect-model-row');
    for (const row of rows) {
      const idCell = row.querySelector('[data-testid^="connect-model-id-"]');
      const id = idCell?.getAttribute('data-testid')?.replace('connect-model-id-', '');
      const text = row.textContent ?? '';
      if (id) {
        expect(text).not.toContain(`${id} ${id}`);
      }
      expect(text).not.toContain('not known not in capability base');
    }
  });

  it('key hints quote the prefix so no stray comma reads as part of it', () => {
    const openai = getPreset(PROVIDER_CATALOG, 'openai');
    expect(openai?.keyHint).toBe('Starts with "sk-".');
  });
});
