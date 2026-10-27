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
  const validation = validateRoleProfile({ role: roleText, mode, provider, model });
  const baseId = `role-profile-${props.projectId}`;
  return createElement(
    'form',
    null,
    createElement('h3', null, t('settings.roleProfile.title')),
    createElement('label', { htmlFor: `${baseId}-role` }, t('settings.roleProfile.roleLabel')),
    createElement('input', {
      id: `${baseId}-role`,
      type: 'text',
      value: roleText,
      onChange: (event: { target: { value: string } }) => setRoleText(event.target.value),
    }),
    createElement('label', { htmlFor: `${baseId}-mode` }, t('settings.roleProfile.modeLabel')),
    createElement(
      'select',
      {
        id: `${baseId}-mode`,
        value: mode,
        onChange: (event: { target: { value: string } }) => setMode(event.target.value as RoleMode),
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
      onChange: (event: { target: { value: string } }) => setProvider(event.target.value),
    }),
    createElement('label', { htmlFor: `${baseId}-model` }, t('settings.roleProfile.modelLabel')),
    createElement('input', {
      id: `${baseId}-model`,
      type: 'text',
      value: model,
      onChange: (event: { target: { value: string } }) => setModel(event.target.value),
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
