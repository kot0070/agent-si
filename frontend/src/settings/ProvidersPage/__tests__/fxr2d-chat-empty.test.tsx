// U10: chat-model empty state reads as one plain sentence while a
// provider is connected but no chat model is picked yet.
/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import { ChatModelSelector } from '../ChatModelSelector';
import { PROVIDER_CATALOG } from '../catalog';

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

describe('U10 chat-model empty sentence', () => {
  it('says "Chat model: Select a model" while Meta is connected and nothing picked', async () => {
    render(
      <ChatModelSelector
        project_id="p-9"
        catalog={PROVIDER_CATALOG}
        states={{ meta: { presetId: 'meta', connected: true, enabledModels: [] } }}
      />,
    );
    const box = await screen.findByTestId('chat-model-selector');
    expect(box.textContent).toContain('Chat model: Select a model');
    expect(await screen.findByTestId('chat-model-empty')).toBeTruthy();
  });
});
