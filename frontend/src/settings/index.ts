import { createElement, useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { t } from '../locale/index';
import { ApiError, requestResponse } from '../api/errors';
import {
  readRoleProfileFromServer,
  readRoleProfilesFromServer,
  writeRoleProfileToServer,
} from './roleProfilesApi';
import { askPermission, installPermissionToolId } from '../chat/permissions';

export type RoleMode = 'PINNED' | 'pool' | 'AUTO';

export interface SettingsRoute {
  path: string;
  titleKey: string;
  purposeKey: string;
  needItNowKey: string;
}

// FXKITUI guided first run: completion record in the settings store. The
// flag is one input to the start gate; the gate always pairs it with live
// server profile state (connected providers plus stored projects), so a
// start decision is never localStorage-only.
export const FIRST_RUN_DONE_KEY = 'agentsi.firstrun.done';

export function readFirstRunDone(): boolean {
  try {
    return window.localStorage.getItem(FIRST_RUN_DONE_KEY) === 'true';
  } catch {
    return false;
  }
}

export function markFirstRunDone(): void {
  try {
    window.localStorage.setItem(FIRST_RUN_DONE_KEY, 'true');
  } catch {
    // Storage unavailable: the in-memory flow still completes this visit.
  }
}

export const SETTINGS_ROUTES: SettingsRoute[] = [
  { path: 'general', titleKey: 'settings.general.title', purposeKey: 'settings.general.purpose', needItNowKey: 'settings.general.needItNow' },
  { path: 'appearance', titleKey: 'settings.appearance.title', purposeKey: 'settings.appearance.purpose', needItNowKey: 'settings.appearance.needItNow' },
  { path: 'localAI', titleKey: 'settings.localAi.title', purposeKey: 'settings.localAi.purpose', needItNowKey: 'settings.localAi.needItNow' },
  { path: 'models', titleKey: 'settings.models.title', purposeKey: 'settings.models.purpose', needItNowKey: 'settings.models.needItNow' },
  { path: 'routing', titleKey: 'settings.routing.title', purposeKey: 'settings.routing.purpose', needItNowKey: 'settings.routing.needItNow' },
  { path: 'optimization', titleKey: 'settings.optimization.title', purposeKey: 'settings.optimization.purpose', needItNowKey: 'settings.optimization.needItNow' },
  { path: 'capabilityDB', titleKey: 'settings.capabilityDb.title', purposeKey: 'settings.capabilityDb.purpose', needItNowKey: 'settings.capabilityDb.needItNow' },
  { path: 'project', titleKey: 'settings.project.title', purposeKey: 'settings.project.purpose', needItNowKey: 'settings.project.needItNow' },
  { path: 'localbench', titleKey: 'settings.localbench.title', purposeKey: 'settings.localbench.purpose', needItNowKey: 'settings.localbench.needItNow' },
];

export interface RoleProfileInput {
  role: string;
  mode: RoleMode;
  provider?: string;
  model?: string;
}

export interface RoleProfileValidation {
  ok: boolean;
  errors: string[];
}

export interface RoleModelProfile {
  mode: RoleMode;
  provider?: string;
  model?: string;
}

export type RoleProfileMap = Record<string, RoleModelProfile>;

export function roleProfilesKey(projectId: string): string {
  return `agentsi.roleProfiles.${projectId}`;
}

function isRoleMode(value: unknown): value is RoleMode {
  return value === 'PINNED' || value === 'pool' || value === 'AUTO';
}

function readCacheMap(projectId: string): RoleProfileMap {
  try {
    const raw = window.sessionStorage.getItem(roleProfilesKey(projectId));
    if (raw === null) {
      return {};
    }
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {};
    }
    const map: RoleProfileMap = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        continue;
      }
      const record = value as Record<string, unknown>;
      if (!isRoleMode(record.mode)) {
        continue;
      }
      const profile: RoleModelProfile = { mode: record.mode };
      if (typeof record.provider === 'string' && record.provider.length > 0) {
        profile.provider = record.provider;
      }
      if (typeof record.model === 'string' && record.model.length > 0) {
        profile.model = record.model;
      }
      map[key] = profile;
    }
    return map;
  } catch {
    return {};
  }
}

function writeCacheMap(projectId: string, map: RoleProfileMap): void {
  try {
    window.sessionStorage.setItem(roleProfilesKey(projectId), JSON.stringify(map));
  } catch {
    // Storage unavailable: the in-memory edit still re-renders.
  }
}

// Server value first; the session copy stays only as a session-scoped
// offline mirror read AFTER the server value (a failed server read falls
// back to it, never the other way round). FXASK F2 keeps this file free of
// browser persistent storage; the mirror never outlives the tab.
export async function readRoleProfiles(projectId: string): Promise<RoleProfileMap> {
  try {
    const server = await readRoleProfilesFromServer(projectId);
    writeCacheMap(projectId, server);
    return server;
  } catch {
    return readCacheMap(projectId);
  }
}

export async function readRoleProfile(
  projectId: string,
  role: string,
): Promise<RoleModelProfile | undefined> {
  // Direct per-role server GET (per project+role route): singular reads must
  // work for any saved role string, while the map stays frozen-roles-based.
  try {
    const profile = await readRoleProfileFromServer(projectId, role);
    if (profile !== undefined) {
      const map = readCacheMap(projectId);
      map[role] = profile;
      writeCacheMap(projectId, map);
      return { ...profile };
    }
  } catch {
    const cached = readCacheMap(projectId)[role];
    return cached === undefined ? undefined : { ...cached };
  }
  return undefined;
}

// Server write first; the cache follows only on success. A failed server
// write rejects (it surfaces, never a silent local-only success) and the
// cache is left untouched.
export async function saveRoleProfile(
  projectId: string,
  input: RoleProfileInput,
): Promise<RoleProfileValidation> {
  const validation = validateRoleProfile(input);
  if (!validation.ok) {
    return validation;
  }
  const role = input.role.trim();
  const profile: RoleModelProfile = { mode: input.mode };
  const provider = (input.provider ?? '').trim();
  const model = (input.model ?? '').trim();
  if (provider.length > 0) {
    profile.provider = provider;
  }
  if (model.length > 0) {
    profile.model = model;
  }
  const saved = await writeRoleProfileToServer(projectId, role, profile);
  const map = readCacheMap(projectId);
  map[role] = saved;
  writeCacheMap(projectId, map);
  return { ok: true, errors: [] };
}

export interface RoleProfileEditorProps {
  projectId: string;
  role: string;
}

export interface AcceptedRiskSwitchProps {
  projectId: string;
}

const ROLE_MODES: RoleMode[] = ['PINNED', 'pool', 'AUTO'];

function modeLabelKey(mode: RoleMode): string {
  if (mode === 'PINNED') {
    return 'settings.roleProfile.modes.pinned';
  }
  if (mode === 'pool') {
    return 'settings.roleProfile.modes.pool';
  }
  return 'settings.roleProfile.modes.auto';
}

export function validateRoleProfile(input: RoleProfileInput): RoleProfileValidation {
  const errors: string[] = [];
  if (input.role.trim().length === 0) {
    errors.push(t('settings.validation.roleRequired'));
  }
  if (!ROLE_MODES.includes(input.mode)) {
    errors.push(t('settings.validation.modeInvalid'));
  }
  if (input.mode === 'PINNED') {
    const provider = (input.provider ?? '').trim();
    const model = (input.model ?? '').trim();
    if (provider.length === 0 || model.length === 0) {
      errors.push(t('settings.validation.pinnedBindingRequired'));
    }
  }
  return { ok: errors.length === 0, errors };
}

export function RoleProfileEditor(props: RoleProfileEditorProps): ReactElement {
  const [roleText, setRoleText] = useState(props.role);
  const [mode, setMode] = useState<RoleMode>('AUTO');
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void readRoleProfile(props.projectId, props.role).then((saved) => {
      if (!alive) {
        return;
      }
      if (saved !== undefined) {
        setMode(saved.mode);
        setProvider(saved.provider ?? '');
        setModel(saved.model ?? '');
      }
    }).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [props.projectId, props.role]);
  function persist(next: {
    role: string;
    mode: RoleMode;
    provider: string;
    model: string;
  }): void {
    void saveRoleProfile(props.projectId, next).then(
      () => {
        setSaveError(null);
      },
      (error: unknown) => {
        setSaveError(error instanceof ApiError ? error.code : 'CONTEXT_MISSING');
      },
    );
  }
  const validation = validateRoleProfile({ role: roleText, mode, provider, model });
  const errors =
    saveError === null
      ? validation.errors
      : [...validation.errors, `${t('errors.generic')} (${saveError})`];
  const baseId = `role-profile-${props.projectId}-${props.role}`;
  return createElement(
    'form',
    null,
    createElement('h3', null, t('settings.roleProfile.title')),
    createElement('label', { htmlFor: `${baseId}-role` }, t('settings.roleProfile.roleLabel')),
    createElement('input', {
      id: `${baseId}-role`,
      type: 'text',
      value: roleText,
      onChange: (event: { target: { value: string } }) => {
        const next = event.target.value;
        setRoleText(next);
        persist({ role: next, mode, provider, model });
      },
    }),
    createElement('label', { htmlFor: `${baseId}-mode` }, t('settings.roleProfile.modeLabel')),
    createElement(
      'select',
      {
        id: `${baseId}-mode`,
        value: mode,
        onChange: (event: { target: { value: string } }) => {
          const next = event.target.value as RoleMode;
          setMode(next);
          persist({ role: roleText, mode: next, provider, model });
        },
      },
      ROLE_MODES.map((option) =>
        createElement('option', { key: option, value: option }, t(modeLabelKey(option))),
      ),
    ),
    createElement('label', { htmlFor: `${baseId}-provider` }, t('settings.roleProfile.providerLabel')),
    createElement('input', {
      id: `${baseId}-provider`,
      type: 'text',
      value: provider,
      onChange: (event: { target: { value: string } }) => {
        const next = event.target.value;
        setProvider(next);
        persist({ role: roleText, mode, provider: next, model });
      },
    }),
    createElement('label', { htmlFor: `${baseId}-model` }, t('settings.roleProfile.modelLabel')),
    createElement('input', {
      id: `${baseId}-model`,
      type: 'text',
      value: model,
      onChange: (event: { target: { value: string } }) => {
        const next = event.target.value;
        setModel(next);
        persist({ role: roleText, mode, provider, model: next });
      },
    }),
    createElement(
      'ul',
      null,
      errors.map((error) => createElement('li', { key: error }, error)),
    ),
  );
}

// Accepted risk is a server-recorded grant, never a local toggle
// (PRODUCT_SPEC 18B: accepted_risk_allowed is server-side policy; the F1
// ask-once ledger is append-only, so a grant cannot be un-recorded and the
// switch is a latch). The session mirror only seeds first paint; the
// backend answer stays authoritative on every mount.
function acceptedRiskMirrorKey(projectId: string): string {
  return `agentsi.acceptedRisk.${projectId}`;
}

function readAcceptedRiskMirror(projectId: string): boolean {
  try {
    const stored = window.sessionStorage.getItem(
      acceptedRiskMirrorKey(projectId));
    return stored === 'true';
  } catch {
    return false;
  }
}

function writeAcceptedRiskMirror(projectId: string, accepted: boolean): void {
  try {
    window.sessionStorage.setItem(
      acceptedRiskMirrorKey(projectId), String(accepted));
  } catch {
    // Storage unavailable: the in-memory state still re-renders.
  }
}

export function AcceptedRiskSwitch(props: AcceptedRiskSwitchProps): ReactElement {
  const [accepted, setAccepted] = useState(
    () => readAcceptedRiskMirror(props.projectId));
  const touchedRef = useRef(false);
  useEffect(() => {
    let alive = true;
    void askPermission(installPermissionToolId(props.projectId)).then(
      (outcome) => {
        if (!alive || touchedRef.current) {
          return;
        }
        writeAcceptedRiskMirror(props.projectId, outcome.askedOnce);
        setAccepted(outcome.askedOnce);
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [props.projectId]);
  return createElement(
    'label',
    null,
    createElement('input', {
      type: 'checkbox',
      checked: accepted,
      onChange: (event: { target: { checked: boolean } }) => {
        if (!event.target.checked) {
          return;
        }
        touchedRef.current = true;
        setAccepted(true);
        writeAcceptedRiskMirror(props.projectId, true);
        void askPermission(installPermissionToolId(props.projectId)).then(
          () => undefined,
          () => undefined,
        );
      },
    }),
    t('settings.risk.label'),
    createElement('p', null, t('settings.risk.warning')),
  );
}

// FXKITUI guided-first-run start gate. A fresh profile (first-run not
// completed) opens /firstrun by itself from the start route, even when
// a project already exists; a completed first run or a connected
// provider never redirects again. Provider state is always read live
// from the server, so the decision is never localStorage-only. On the
// Settings General page the gate renders the link to the How-it-works
// diagram; on /firstrun it renders the always-visible skip plus the
// How-it-works link (they live here so the flow component stays
// untouched). A connected provider marks the run done (the profile is
// no longer fresh), so the gate naturally stays quiet afterwards.
// Mounted by the single FXKITUI-FIRSTRUN
// block in App.tsx. Written with createElement: this module is a .ts file.
async function readConnectedProviderIds(): Promise<string[] | null> {
  try {
    const response = await requestResponse('/api/v1/providers', {
      method: 'GET',
    });
    const data: unknown = await response.json();
    if (typeof data !== 'object' || data === null) {
      return null;
    }
    const providers = (data as { providers?: unknown }).providers;
    if (!Array.isArray(providers)) {
      return null;
    }
    const ids: string[] = [];
    for (const row of providers) {
      if (
        typeof row === 'object' &&
        row !== null &&
        typeof (row as { provider_id?: unknown }).provider_id === 'string'
      ) {
        ids.push((row as { provider_id: string }).provider_id);
      }
    }
    return ids;
  } catch {
    return null;
  }
}

export function FirstRunGate(): ReactElement | null {
  const location = useLocation();
  const navigate = useNavigate();
  const [settled, setSettled] = useState<boolean>(() => readFirstRunDone());
  useEffect(() => {
    if (readFirstRunDone()) {
      setSettled(true);
      return;
    }
    let alive = true;
    void readConnectedProviderIds().then(
      (providers) => {
        if (!alive) {
          return;
        }
        setSettled(true);
        if (providers !== null && providers.length > 0) {
          // A connected provider means the profile is no longer fresh:
          // mark the run done and never redirect again.
          markFirstRunDone();
          return;
        }
        if (location.pathname === '/') {
          navigate('/firstrun', { replace: true });
        }
      },
      () => {
        // A failed probe fails open to chat: a start gate must never lock
        // a newcomer out when the server cannot be reached.
        if (alive) {
          setSettled(true);
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [navigate, location.pathname]);
  // Anchors with client-side navigation (createElement over the router
  // Link rejects test ids under .ts typing; the behavior is identical).
  function go(event: { preventDefault(): void }, to: string): void {
    event.preventDefault();
    navigate(to);
  }
  if (location.pathname === '/settings' && settled) {
    return createElement(
      'p',
      { 'data-testid': 'settings-how-it-works-wrap' },
      createElement(
        'a',
        {
          'data-testid': 'settings-how-it-works',
          href: '/how-it-works',
          onClick: (event: { preventDefault(): void }) => {
            go(event, '/how-it-works');
          },
        },
        t('howItWorks.runs.title'),
      ),
    );
  }
  if (location.pathname === '/firstrun') {
    return createElement(
      'p',
      { 'data-testid': 'firstrun-gate-links' },
      createElement(
        'a',
        {
          'data-testid': 'firstrun-skip',
          href: '/',
          onClick: (event: { preventDefault(): void }) => {
            markFirstRunDone();
            go(event, '/');
          },
        },
        t('firstrun.skip'),
      ),
      ' ',
      createElement(
        'a',
        {
          'data-testid': 'firstrun-how-it-works',
          href: '/how-it-works',
          onClick: (event: { preventDefault(): void }) => {
            go(event, '/how-it-works');
          },
        },
        t('howItWorks.runs.title'),
      ),
    );
  }
  return null;
}
