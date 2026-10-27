import { createElement, useState } from 'react';
import type { ReactElement } from 'react';
import { t } from '../locale/index';

export type RoleMode = 'PINNED' | 'pool' | 'AUTO';

export interface SettingsRoute {
  path: string;
  titleKey: string;
  purposeKey: string;
  needItNowKey: string;
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

export function readRoleProfiles(projectId: string): RoleProfileMap {
  try {
    const raw = window.localStorage.getItem(roleProfilesKey(projectId));
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

export function readRoleProfile(projectId: string, role: string): RoleModelProfile | undefined {
  const profile = readRoleProfiles(projectId)[role];
  if (profile === undefined) {
    return undefined;
  }
  return { ...profile };
}

export function saveRoleProfile(projectId: string, input: RoleProfileInput): RoleProfileValidation {
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
  const map = readRoleProfiles(projectId);
  map[role] = profile;
  try {
    window.localStorage.setItem(roleProfilesKey(projectId), JSON.stringify(map));
  } catch {
    // Storage unavailable: the in-memory edit still re-renders.
  }
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
  const saved = readRoleProfile(props.projectId, props.role);
  const [roleText, setRoleText] = useState(props.role);
  const [mode, setMode] = useState<RoleMode>(saved?.mode ?? 'AUTO');
  const [provider, setProvider] = useState(saved?.provider ?? '');
  const [model, setModel] = useState(saved?.model ?? '');
  const validation = validateRoleProfile({ role: roleText, mode, provider, model });
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
        saveRoleProfile(props.projectId, { role: next, mode, provider, model });
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
          saveRoleProfile(props.projectId, { role: roleText, mode: next, provider, model });
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
        saveRoleProfile(props.projectId, { role: roleText, mode, provider: next, model });
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
        saveRoleProfile(props.projectId, { role: roleText, mode, provider, model: next });
      },
    }),
    createElement(
      'ul',
      null,
      validation.errors.map((error) => createElement('li', { key: error }, error)),
    ),
  );
}

function acceptedRiskKey(projectId: string): string {
  return `agentsi.acceptedRisk.${projectId}`;
}

function readAcceptedRisk(projectId: string): boolean {
  try {
    return window.localStorage.getItem(acceptedRiskKey(projectId)) === 'true';
  } catch {
    return false;
  }
}

export function AcceptedRiskSwitch(props: AcceptedRiskSwitchProps): ReactElement {
  const [accepted, setAccepted] = useState(() => readAcceptedRisk(props.projectId));
  const key = acceptedRiskKey(props.projectId);
  return createElement(
    'label',
    null,
    createElement('input', {
      type: 'checkbox',
      checked: accepted,
      onChange: (event: { target: { checked: boolean } }) => {
        const next = event.target.checked;
        setAccepted(next);
        try {
          window.localStorage.setItem(key, String(next));
        } catch {
          // Storage unavailable: the switch still re-renders in memory.
        }
      },
    }),
    t('settings.risk.label'),
    createElement('p', null, t('settings.risk.warning')),
  );
}
