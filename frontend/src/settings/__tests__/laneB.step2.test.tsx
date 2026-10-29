/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AcceptedRiskSwitch, RoleProfileEditor, validateRoleProfile } from '../index';
import type { RoleMode } from '../index';
import { resetLocaleForTests, setLocale } from '../../locale/index';
import en from '../../locale/en.json';

const serverRows = new Map<string, Record<string, unknown>>();

function jsonBody(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

// The editor saves through the server now, so the boundary answers the
// role route; validation assertions below stay exactly as they were.
function stubBoundary(): void {
  serverRows.clear();
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
      const record = (body ?? {}) as Record<string, unknown>;
      const row: Record<string, unknown> = {
        role: String(record['role'] ?? ''),
        project_id: String(record['project_id'] ?? ''),
        mode: String(record['mode'] ?? ''),
        provider: record['provider'] ?? null,
        model: record['model'] ?? null,
        binding: 'DEFAULT',
        version: 1,
      };
      serverRows.set(`${row['project_id']}::${row['role']}`, row);
      return jsonBody({ ok: true, profile: row });
    }
    if (url.startsWith('/api/v1/routing/role?') && method === 'GET') {
      return jsonBody({ error: 'missing' }, 404);
    }
    throw new Error(`unexpected fetch ${method} ${url}`);
  });
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  stubBoundary();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
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
