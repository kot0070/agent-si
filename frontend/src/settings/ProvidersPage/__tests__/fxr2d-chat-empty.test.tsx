// R3: no model list carries a `Модель чату: Вибрати модель` line under
// an empty select. The picker keeps its placeholder option; nothing
// else renders.
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

describe('R3 no empty-select line', () => {
  it('renders the placeholder option but no extra line while Meta is connected and nothing picked', async () => {
    render(
      <ChatModelSelector
        project_id="p-9"
        catalog={PROVIDER_CATALOG}
        states={{ meta: { presetId: 'meta', connected: true, enabledModels: [] } }}
      />,
    );
    const box = await screen.findByTestId('chat-model-selector');
    expect(box.textContent).toContain('Select a model');
    expect(screen.queryByTestId('chat-model-empty')).toBeNull();
  });
});
