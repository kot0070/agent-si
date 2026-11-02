/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  SETTINGS_ROUTES,
  readRoleProfile,
  readRoleProfiles,
  saveRoleProfile,
} from '../index';
import { RoleProfileEditor } from '../index';
import { SettingsLayout } from '../../shell/SettingsLayout';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import en from '../../locale/en.json';

const serverRows = new Map<string, Record<string, unknown>>();
let putCalls = 0;

function rowKey(projectId: string, role: string): string {
  return `${projectId}::${role}`;
}

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

// Permissive fake of the role route: this file proves the frontend
// save/load contract (trim, per-role/per-project isolation, offline
// cache order), not backend role validation (backend tests own that).
function stubBoundary(): void {
  serverRows.clear();
  putCalls = 0;
  vi.stubGlobal('fetch', async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    let body: unknown = null;
    if (typeof init?.body === 'string' && init.body.length > 0) {
      try {
        body = JSON.parse(init.body) as unknown;
      } catch {
        body = null;
      }
    }
    if (url === '/api/v1/routing/role' && method === 'PUT') {
      putCalls += 1;
      const record = (body ?? {}) as Record<string, unknown>;
      const projectId = String(record['project_id'] ?? '');
      const role = String(record['role'] ?? '');
      const mode = String(record['mode'] ?? '');
      const row: Record<string, unknown> = {
        role,
        project_id: projectId,
        mode,
        provider: mode === 'PINNED' ? (record['provider'] ?? null) : null,
        model: mode === 'PINNED' ? (record['model'] ?? null) : null,
        binding: 'DEFAULT',
        version: 1,
      };
      serverRows.set(rowKey(projectId, role), row);
      return jsonBody({ ok: true, profile: row });
    }
    if (url.startsWith('/api/v1/routing/role?') && method === 'GET') {
      const query = new URLSearchParams(url.split('?')[1] ?? '');
      const row = serverRows.get(
        rowKey(query.get('project_id') ?? '', query.get('role') ?? ''),
      );
      if (row === undefined) {
        return jsonBody({ error: 'missing' }, 404);
      }
      return jsonBody({ profile: row });
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  window.sessionStorage.clear();
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('roleProfilesKey + save + reload per role', () => {
  it('saves one row keyed by trimmed role and reloads it', async () => {
    const result = await saveRoleProfile('project-1', {
      role: '  manager  ',
      mode: 'PINNED',
      provider: 'acme',
      model: 'm1',
    });
    expect(result.ok).toBe(true);
    expect(window.sessionStorage.getItem('agentsi.roleProfiles.project-1')).toContain('"manager"');
    const loaded = await readRoleProfile('project-1', 'manager');
    expect(loaded).toEqual({ mode: 'PINNED', provider: 'acme', model: 'm1' });
  });
});

describe('per-role isolation', () => {
  it('keeps one row per role without touching other roles', async () => {
    expect((await saveRoleProfile('project-1', { role: 'manager', mode: 'AUTO' })).ok).toBe(true);
    expect(
      (await saveRoleProfile('project-1', { role: 'reviewer', mode: 'pool' })).ok,
    ).toBe(true);
    expect(await readRoleProfile('project-1', 'manager')).toEqual({ mode: 'AUTO' });
    expect(await readRoleProfile('project-1', 'reviewer')).toEqual({ mode: 'pool' });
  });
});

describe('per-project isolation', () => {
  it('stores the same role separately per project', async () => {
    expect(
      (await saveRoleProfile('project-1', { role: 'manager', mode: 'AUTO' })).ok,
    ).toBe(true);
    expect(
      (await saveRoleProfile('project-2', {
        role: 'manager',
        mode: 'PINNED',
        provider: 'acme',
        model: 'm1',
      })).ok,
    ).toBe(true);
    expect(await readRoleProfile('project-1', 'manager')).toEqual({ mode: 'AUTO' });
    expect(await readRoleProfile('project-2', 'manager')).toEqual({
      mode: 'PINNED',
      provider: 'acme',
      model: 'm1',
    });
  });
});

describe('unknown role', () => {
  it('returns undefined with no fallback row', async () => {
    expect((await saveRoleProfile('project-1', { role: 'manager', mode: 'AUTO' })).ok).toBe(true);
    expect(await readRoleProfile('project-1', 'stranger')).toBeUndefined();
    const map = await readRoleProfiles('project-1');
    expect(Object.keys(map).sort()).toEqual(['manager']);
    expect(('default' + '_manager') in map).toBe(false);
  });
});

describe('invalid input is not persisted', () => {
  it('rejects PINNED without binding and writes nothing', async () => {
    const result = await saveRoleProfile('project-1', { role: 'manager', mode: 'PINNED' });
    expect(result.ok).toBe(false);
    expect(result.errors).toContain(en.settings.validation.pinnedBindingRequired);
    expect(window.sessionStorage.getItem('agentsi.roleProfiles.project-1')).toBeNull();
    expect(await readRoleProfiles('project-1')).toEqual({});
  });

  it('issues no server write for invalid input', async () => {
    putCalls = 0;
    await saveRoleProfile('project-1', { role: 'manager', mode: 'PINNED' });
    expect(putCalls).toBe(0);
  });
});

describe('failed server write surfaces', () => {
  it('rejects and leaves the cache untouched', async () => {
    vi.stubGlobal('fetch', async () => jsonBody({ error: 'down' }, 500));
    await expect(
      saveRoleProfile('project-1', {
        role: 'manager',
        mode: 'PINNED',
        provider: 'acme',
        model: 'm1',
      }),
    ).rejects.toBeTruthy();
    expect(window.sessionStorage.getItem('agentsi.roleProfiles.project-1')).toBeNull();
  });
});

describe('corrupt stored JSON', () => {
  it('reads back as an empty map', async () => {
    window.sessionStorage.setItem('agentsi.roleProfiles.project-1', 'not-json{{{');
    expect(await readRoleProfiles('project-1')).toEqual({});
    expect(await readRoleProfile('project-1', 'manager')).toBeUndefined();
  });

  it('falls back to the cache when the server is unreachable', async () => {
    await saveRoleProfile('project-1', { role: 'manager', mode: 'AUTO' });
    window.sessionStorage.setItem(
      'agentsi.roleProfiles.project-1',
      JSON.stringify({ manager: { mode: 'pool' } }),
    );
    vi.stubGlobal('fetch', async () => {
      throw new TypeError('offline');
    });
    expect(await readRoleProfiles('project-1')).toEqual({ manager: { mode: 'pool' } });
    window.sessionStorage.setItem('agentsi.roleProfiles.project-1', 'not-json{{{');
    expect(await readRoleProfiles('project-1')).toEqual({});
  });

  it('reads a missing key as an empty map', async () => {
    expect(await readRoleProfiles('project-9')).toEqual({});
  });
});

describe('RoleProfileEditor persists and reloads', () => {
  it('persists an edit and restores it after unmount/remount', async () => {
    const { unmount } = render(<RoleProfileEditor projectId="project-1" role="manager" />);
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modeLabel), {
      target: { value: 'PINNED' },
    });
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.providerLabel), {
      target: { value: 'acme' },
    });
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modelLabel), {
      target: { value: 'm1' },
    });
    await waitFor(() => {
      expect(serverRows.get(rowKey('project-1', 'manager'))?.['mode']).toBe('PINNED');
    });
    expect(await readRoleProfile('project-1', 'manager')).toEqual({
      mode: 'PINNED',
      provider: 'acme',
      model: 'm1',
    });
    unmount();
    render(<RoleProfileEditor projectId="project-1" role="manager" />);
    await waitFor(() => {
      expect(
        (screen.getByLabelText(en.settings.roleProfile.modeLabel) as HTMLSelectElement).value,
      ).toBe('PINNED');
    });
    expect(
      (screen.getByLabelText(en.settings.roleProfile.providerLabel) as HTMLInputElement).value,
    ).toBe('acme');
    expect(
      (screen.getByLabelText(en.settings.roleProfile.modelLabel) as HTMLInputElement).value,
    ).toBe('m1');
  });
});

describe('REAL PAGE: SettingsLayout around RoleProfileEditor', () => {
  it('persists and reloads inside the real project settings page', async () => {
    const route = SETTINGS_ROUTES.find((entry) => entry.path === 'project')!;
    const { unmount } = render(
      <SettingsLayout
        titleKey={route.titleKey}
        purposeKey={route.purposeKey}
        needItNowKey={route.needItNowKey}
      >
        <RoleProfileEditor projectId="project-7" role="manager" />
      </SettingsLayout>,
    );
    expect(screen.getByText(en.settings.project.title)).toBeTruthy();
    expect(screen.getByText(en.settings.roleProfile.title)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modeLabel), {
      target: { value: 'pool' },
    });
    await waitFor(() => {
      expect(serverRows.get(rowKey('project-7', 'manager'))?.['mode']).toBe('pool');
    });
    expect(await readRoleProfile('project-7', 'manager')).toEqual({ mode: 'pool' });
    unmount();
    render(
      <SettingsLayout
        titleKey={route.titleKey}
        purposeKey={route.purposeKey}
        needItNowKey={route.needItNowKey}
      >
        <RoleProfileEditor projectId="project-7" role="manager" />
      </SettingsLayout>,
    );
    await waitFor(() => {
      expect(
        (screen.getByLabelText(en.settings.roleProfile.modeLabel) as HTMLSelectElement).value,
      ).toBe('pool');
    });
  });
});
