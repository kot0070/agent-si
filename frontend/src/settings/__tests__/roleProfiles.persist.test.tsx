/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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

describe('roleProfilesKey + save + reload per role', () => {
  it('saves one row keyed by trimmed role and reloads it', () => {
    const result = saveRoleProfile('project-1', {
      role: '  manager  ',
      mode: 'PINNED',
      provider: 'acme',
      model: 'm1',
    });
    expect(result.ok).toBe(true);
    expect(window.localStorage.getItem('agentsi.roleProfiles.project-1')).toContain('"manager"');
    const loaded = readRoleProfile('project-1', 'manager');
    expect(loaded).toEqual({ mode: 'PINNED', provider: 'acme', model: 'm1' });
  });
});

describe('per-role isolation', () => {
  it('keeps one row per role without touching other roles', () => {
    expect(saveRoleProfile('project-1', { role: 'manager', mode: 'AUTO' }).ok).toBe(true);
    expect(
      saveRoleProfile('project-1', { role: 'reviewer', mode: 'pool' }).ok,
    ).toBe(true);
    expect(readRoleProfile('project-1', 'manager')).toEqual({ mode: 'AUTO' });
    expect(readRoleProfile('project-1', 'reviewer')).toEqual({ mode: 'pool' });
  });
});

describe('per-project isolation', () => {
  it('stores the same role separately per project', () => {
    expect(
      saveRoleProfile('project-1', { role: 'manager', mode: 'AUTO' }).ok,
    ).toBe(true);
    expect(
      saveRoleProfile('project-2', {
        role: 'manager',
        mode: 'PINNED',
        provider: 'acme',
        model: 'm1',
      }).ok,
    ).toBe(true);
    expect(readRoleProfile('project-1', 'manager')).toEqual({ mode: 'AUTO' });
    expect(readRoleProfile('project-2', 'manager')).toEqual({
      mode: 'PINNED',
      provider: 'acme',
      model: 'm1',
    });
  });
});

describe('unknown role', () => {
  it('returns undefined with no fallback row', () => {
    expect(saveRoleProfile('project-1', { role: 'manager', mode: 'AUTO' }).ok).toBe(true);
    expect(readRoleProfile('project-1', 'stranger')).toBeUndefined();
    const map = readRoleProfiles('project-1');
    expect(Object.keys(map).sort()).toEqual(['manager']);
    expect(('default' + '_manager') in map).toBe(false);
  });
});

describe('invalid input is not persisted', () => {
  it('rejects PINNED without binding and writes nothing', () => {
    const result = saveRoleProfile('project-1', { role: 'manager', mode: 'PINNED' });
    expect(result.ok).toBe(false);
    expect(result.errors).toContain(en.settings.validation.pinnedBindingRequired);
    expect(window.localStorage.getItem('agentsi.roleProfiles.project-1')).toBeNull();
    expect(readRoleProfiles('project-1')).toEqual({});
  });
});

describe('corrupt stored JSON', () => {
  it('reads back as an empty map', () => {
    window.localStorage.setItem('agentsi.roleProfiles.project-1', 'not-json{{{');
    expect(readRoleProfiles('project-1')).toEqual({});
    expect(readRoleProfile('project-1', 'manager')).toBeUndefined();
  });

  it('reads a missing key as an empty map', () => {
    expect(readRoleProfiles('project-9')).toEqual({});
  });
});

describe('RoleProfileEditor persists and reloads', () => {
  it('persists an edit and restores it after unmount/remount', () => {
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
    expect(readRoleProfile('project-1', 'manager')).toEqual({
      mode: 'PINNED',
      provider: 'acme',
      model: 'm1',
    });
    unmount();
    render(<RoleProfileEditor projectId="project-1" role="manager" />);
    expect(
      (screen.getByLabelText(en.settings.roleProfile.modeLabel) as HTMLSelectElement).value,
    ).toBe('PINNED');
    expect(
      (screen.getByLabelText(en.settings.roleProfile.providerLabel) as HTMLInputElement).value,
    ).toBe('acme');
    expect(
      (screen.getByLabelText(en.settings.roleProfile.modelLabel) as HTMLInputElement).value,
    ).toBe('m1');
  });
});

describe('REAL PAGE: SettingsLayout around RoleProfileEditor', () => {
  it('persists and reloads inside the real project settings page', () => {
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
    expect(readRoleProfile('project-7', 'manager')).toEqual({ mode: 'pool' });
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
    expect(
      (screen.getByLabelText(en.settings.roleProfile.modeLabel) as HTMLSelectElement).value,
    ).toBe('pool');
  });
});
