/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AcceptedRiskSwitch, RoleProfileEditor, validateRoleProfile } from '../index';
import type { RoleMode } from '../index';
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

describe('validateRoleProfile', () => {
  it('accepts a manager AUTO profile', () => {
    expect(validateRoleProfile({ role: 'manager', mode: 'AUTO' }).ok).toBe(true);
  });

  it('accepts pool and pinned-with-binding profiles', () => {
    expect(validateRoleProfile({ role: 'manager', mode: 'pool' }).ok).toBe(true);
    expect(
      validateRoleProfile({ role: 'manager', mode: 'PINNED', provider: 'acme', model: 'm1' }).ok,
    ).toBe(true);
  });

  it('rejects an empty role', () => {
    const result = validateRoleProfile({ role: '   ', mode: 'AUTO' });
    expect(result.ok).toBe(false);
    expect(result.errors).toContain(en.settings.validation.roleRequired);
  });

  it('rejects a bad mode', () => {
    const result = validateRoleProfile({ role: 'manager', mode: 'XX' as RoleMode });
    expect(result.ok).toBe(false);
    expect(result.errors).toContain(en.settings.validation.modeInvalid);
  });

  it('rejects PINNED without provider or model', () => {
    const missingBoth = validateRoleProfile({ role: 'manager', mode: 'PINNED' });
    expect(missingBoth.ok).toBe(false);
    const missingModel = validateRoleProfile({ role: 'manager', mode: 'PINNED', provider: 'acme' });
    expect(missingModel.ok).toBe(false);
    const missingProvider = validateRoleProfile({ role: 'manager', mode: 'PINNED', model: 'm1' });
    expect(missingProvider.ok).toBe(false);
    expect(missingBoth.errors).toContain(en.settings.validation.pinnedBindingRequired);
  });
});

describe('RoleProfileEditor', () => {
  it('renders the form with labels', () => {
    render(<RoleProfileEditor projectId="project-1" role="manager" />);
    expect(screen.getByText(en.settings.roleProfile.title)).toBeTruthy();
    expect(screen.getByLabelText(en.settings.roleProfile.roleLabel)).toBeTruthy();
    expect(screen.getByLabelText(en.settings.roleProfile.modeLabel)).toBeTruthy();
    expect(screen.getByLabelText(en.settings.roleProfile.providerLabel)).toBeTruthy();
    expect(screen.getByLabelText(en.settings.roleProfile.modelLabel)).toBeTruthy();
  });

  it('shows inline feedback and clears it when fixed', () => {
    render(<RoleProfileEditor projectId="project-1" role="manager" />);
    const roleInput = screen.getByLabelText(en.settings.roleProfile.roleLabel);
    fireEvent.change(roleInput, { target: { value: '' } });
    expect(screen.getByText(en.settings.validation.roleRequired)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modeLabel), {
      target: { value: 'PINNED' },
    });
    expect(screen.getByText(en.settings.validation.pinnedBindingRequired)).toBeTruthy();
    fireEvent.change(roleInput, { target: { value: 'manager' } });
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.providerLabel), {
      target: { value: 'acme' },
    });
    fireEvent.change(screen.getByLabelText(en.settings.roleProfile.modelLabel), {
      target: { value: 'm1' },
    });
    expect(screen.queryByText(en.settings.validation.roleRequired)).toBeNull();
    expect(screen.queryByText(en.settings.validation.pinnedBindingRequired)).toBeNull();
  });
});

describe('AcceptedRiskSwitch', () => {
  it('renders the label and the plain warning', () => {
    render(<AcceptedRiskSwitch projectId="project-1" />);
    expect(screen.getByText(en.settings.risk.label)).toBeTruthy();
    expect(screen.getByText(en.settings.risk.warning)).toBeTruthy();
  });

  it('toggles, re-renders and persists per project', () => {
    const { unmount } = render(<AcceptedRiskSwitch projectId="project-1" />);
    const box = screen.getByRole('checkbox') as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(box);
    expect(box.checked).toBe(true);
    expect(window.localStorage.getItem('agentsi.acceptedRisk.project-1')).toBe('true');
    unmount();
    render(<AcceptedRiskSwitch projectId="project-1" />);
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(true);
    cleanup();
    render(<AcceptedRiskSwitch projectId="project-2" />);
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
  });
});
