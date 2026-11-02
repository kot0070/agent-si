// U7: dialog backdrops are translucent (no black void), the disconnect
// body names the provider in words (never a raw secret id), and the
// Cancel/Disconnect actions are spaced.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
// @ts-ignore: node fs available offline in this repo's tests
import { readFileSync } from 'node:fs';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import { DisconnectDialog } from '../DisconnectDialog';
import { ConnectDialog } from '../ConnectDialog';
import { PROVIDER_CATALOG, getPreset } from '../catalog';
import {
  createMemorySecretStore,
  secretIdForProvider,
} from '../secretStore';

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

function renderDisconnect(): void {
  render(
    <DisconnectDialog
      provider_id="meta"
      providerLabel="Meta"
      secretId={secretIdForProvider('meta')}
      open
      store={createMemorySecretStore('sess')}
      sessionToken="sess"
      onClose={() => {}}
      onDisconnected={() => {}}
    />,
  );
}

describe('U7 translucent dialogs with a human body', () => {
  it('disconnect backdrop is translucent, not opaque black', () => {
    renderDisconnect();
    const backdrop = screen.getByTestId('disconnect-backdrop');
    expect(getComputedStyle(backdrop).backgroundColor).toBe('rgba(0, 0, 0, 0.5)');
  });

  it('disconnect body names the provider, never a raw secret id', () => {
    renderDisconnect();
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain('Removes the saved key for Meta.');
    expect(dialog.textContent).not.toContain(secretIdForProvider('meta'));
    expect(dialog.textContent).not.toContain('agent_si');
  });

  it('Cancel and Disconnect sit in a spaced action row', () => {
    renderDisconnect();
    const cancel = screen.getByText('Cancel');
    const confirm = screen.getByText('Disconnect');
    expect(confirm.parentElement).toBe(cancel.parentElement);
    expect(confirm.parentElement?.style.gap).not.toBe('');
  });

  it('the key field says the key stays in the Windows store', () => {
    const preset = getPreset(PROVIDER_CATALOG, 'openai');
    expect(preset).toBeDefined();
    render(
      <ConnectDialog
        preset_id="openai"
        preset={preset ?? null}
        open
        store={createMemorySecretStore('sess')}
        onClose={() => {}}
        onConnected={() => {}}
      />,
    );
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('The key stays in your Windows store.')).toBeTruthy();
  });

  it('a wrong key shows the specific refusal plus what to do', async () => {    vi.stubGlobal(
      'fetch',
      async (input: unknown, init?: { method?: string }) => {
        const url = String(input);
        const method = (init?.method ?? 'GET').toUpperCase();
        // Two-step dialog (FXR2E): paste + Check hits the read-only
        // route and refuses here; Save never runs for a bad key.
        if (url === '/api/v1/providers/keys/check' && method === 'POST') {
          return new Response(JSON.stringify({ code: 'KEY_REFUSED' }), {
            status: 401,
            headers: { 'content-type': 'application/json' },
          });
        }
        return new Response(JSON.stringify({ code: 'CONTEXT_MISSING' }), {
          status: 404,
          headers: { 'content-type': 'application/json' },
        });
      },
    );
    const preset = getPreset(PROVIDER_CATALOG, 'openai');
    expect(preset).toBeDefined();
    render(
      <ConnectDialog
        preset_id="openai"
        preset={preset ?? null}
        open
        store={createMemorySecretStore('sess')}
        onClose={() => {}}
        onConnected={() => {}}
      />,
    );
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('API key'), {
      target: { value: 'wrong-key' },
    });
    fireEvent.click(within(dialog).getByText('Check'));
    const status = await within(dialog).findByRole('status');
    // Specific refusal plus what to do, never a machine code.
    expect(status.textContent).toContain('The provider refused this key.');
    expect(status.textContent).toContain('Paste the full key again.');
    expect(dialog.textContent).not.toContain('Connected');
    expect(status.textContent).not.toContain('KEY_REFUSED');
    expect(status.textContent).not.toContain('Something went wrong');
  });
});

describe('J10 connect dialog model list', () => {
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
                { model: 'openai/gpt-4o', kb_known: false, price: null },
              ],
              enabled: ['openai/gpt-4o-mini'],
              source: 'provider',
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

  function renderManage(): void {
    const preset = getPreset(PROVIDER_CATALOG, 'openai');
    expect(preset).toBeDefined();
    render(
      <ConnectDialog
        preset_id="openai"
        preset={preset ?? null}
        open
        store={createMemorySecretStore('sess')}
        initialStep={2}
        onClose={() => {}}
        onConnected={() => {}}
      />,
    );
  }

  it('one header line names the unknown models', async () => {
    stubModels();
    renderManage();
    const note = await screen.findByTestId('connect-models-unknown-note');
    expect(note.textContent).toContain('not in the capability base');
  });

  it('checkboxes are labelled by model id', async () => {
    stubModels();
    renderManage();
    const rows = await screen.findAllByTestId('connect-model-row');
    expect(rows.length).toBe(2);
    for (const id of ['openai/gpt-4o-mini', 'openai/gpt-4o']) {
      const box = within(document.body).getByLabelText(id) as HTMLInputElement;
      expect(box.getAttribute('type')).toBe('checkbox');
    }
  });

  it('model rows wrap safely with 24px checkbox targets', () => {
    const shellCss = readFileSync('src/ui/shell.css', 'utf8');
    expect(shellCss).toMatch(/li\[data-testid="model-row"\][\s\S]*?flex-wrap:\s*wrap/);
    expect(shellCss).toMatch(/li\[data-testid="connect-model-row"\][\s\S]*?flex-wrap:\s*wrap/);
    expect(shellCss).toMatch(/connect-model-row"\] input\[type="checkbox"\][\s\S]*?min-width:\s*24px/);
  });
});
