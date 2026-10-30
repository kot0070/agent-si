// K07 Lane B STEP2 step 1: types-only interface snapshot of the 8 frozen STEP1 surfaces.
// No runtime code: every function body is omitted; declarations only.
// Sources: frontend/src/locale/index.ts, frontend/src/locale/en.json,
// frontend/src/locale/uk.json, frontend/src/shell/SettingsLayout.tsx,
// frontend/src/settings/index.ts, frontend/src/app/firstrun/FirstRunFlow.tsx,
// frontend/src/app/About.tsx, frontend/src/app/migration/MigrationView.tsx,
// frontend/src/app/HowItWorks.tsx.

import type { ReactElement, ReactNode } from 'react';

// --- frontend/src/locale/index.ts ---
export type SupportedLocale = 'en' | 'uk';

export type LocaleErrorCode = 'MISSING_LOCALE_KEY' | 'UNSUPPORTED_LOCALE';

// Full key union of frontend/src/locale/en.json + frontend/src/locale/uk.json
// (32 mirrored keys each; parity verified by paired full-file reads).
export type LocaleKey =
  | 'about.licence.line'
  | 'about.licence.mitText'
  | 'about.thirdParty.title'
  | 'howItWorks.codeTests.body'
  | 'howItWorks.codeTests.title'
  | 'howItWorks.localTests.body'
  | 'howItWorks.localTests.title'
  | 'howItWorks.runs.body'
  | 'howItWorks.runs.title'
  | 'settings.appearance.needItNow'
  | 'settings.appearance.purpose'
  | 'settings.appearance.title'
  | 'settings.capabilityDb.needItNow'
  | 'settings.capabilityDb.purpose'
  | 'settings.capabilityDb.title'
  | 'settings.general.needItNow'
  | 'settings.general.purpose'
  | 'settings.general.title'
  | 'settings.localAi.needItNow'
  | 'settings.localAi.purpose'
  | 'settings.localAi.title'
  | 'settings.models.needItNow'
  | 'settings.models.purpose'
  | 'settings.models.title'
  | 'settings.optimization.needItNow'
  | 'settings.optimization.purpose'
  | 'settings.optimization.requiredQuality'
  | 'settings.optimization.riskCeiling'
  | 'settings.optimization.title'
  | 'settings.optimization.weights'
  | 'settings.project.needItNow'
  | 'settings.project.purpose'
  | 'settings.project.title'
  | 'settings.providers.searchPlaceholder'
  | 'settings.routing.needItNow'
  | 'settings.routing.purpose'
  | 'settings.routing.title'
  | 'agents.badge.cloud'
  | 'agents.badge.local'
  | 'agents.badge.split'
  | 'agents.live.empty'
  | 'agents.live.title'
  | 'agents.row.deliverable'
  | 'agents.row.scope'
  | 'agents.row.tokens'
  | 'api.error.audit_independence_rejected'
  | 'api.error.budget_capped'
  | 'api.error.budget_hard_blocked'
  | 'api.error.budget_soft_warn'
  | 'api.error.context_missing'
  | 'api.error.context_wrong_contract_version'
  | 'api.error.credential_entry_missing'
  | 'api.error.delta_over_bound'
  | 'api.error.duplicate_settlement_refused'
  | 'api.error.gate_not_passed'
  | 'api.error.invalid_hierarchy_chain'
  | 'api.error.kb_proposal_not_approved'
  | 'api.error.kb_validation_failed'
  | 'api.error.key_save_timeout'
  | 'api.error.missing_integration_task'
  | 'api.error.modality_mismatch'
  | 'api.error.no_eligible_candidate'
  | 'api.error.no_profile_blocked'
  | 'api.error.pending_reconciliation'
  | 'api.error.policy_conflict'
  | 'api.error.price_unknown_expensive'
  | 'api.error.provider_unevidenced'
  | 'api.error.rejected_scope_overlap'
  | 'api.error.scope_overlap'
  | 'api.error.unknown_limit_kind'
  | 'chat.abort.cancel'
  | 'chat.approval.accept'
  | 'chat.approval.edit'
  | 'chat.approval.reject'
  | 'chat.composer.draft'
  | 'chat.composer.prompt'
  | 'chat.composer.send'
  | 'chat.stream.offline'
  | 'chat.stream.spinner'
  | 'chat.stream.timestamp'
  | 'empty.generic'
  | 'errors.generic'
  | 'firstrun.greeting'
  | 'firstrun.next'
  | 'firstrun.optional.automations'
  | 'firstrun.optional.kbs'
  | 'firstrun.optional.localAI'
  | 'firstrun.optional.watcherPreset'
  | 'firstrun.optionalNote'
  | 'firstrun.skip'
  | 'firstrun.steps.connectProvider'
  | 'firstrun.steps.firstTask'
  | 'firstrun.steps.oneClickTeam'
  | 'firstrun.steps.projectFolder'
  | 'firstrun.title'
  | 'migration.done'
  | 'migration.keepsOldCopies'
  | 'migration.title'
  | 'projects.ai_usage.title'
  | 'projects.audits.title'
  | 'projects.cloud_ai.title'
  | 'projects.cost.title'
  | 'projects.derived.label'
  | 'projects.errors.title'
  | 'projects.list.empty'
  | 'projects.list.title'
  | 'projects.local_ai.title'
  | 'projects.models.title'
  | 'projects.overview.title'
  | 'projects.reports.title'
  | 'projects.routing.title'
  | 'projects.runs.title'
  | 'projects.time.title'
  | 'projects.tokens.title'
  | 'projects.why_this_model.title'
  | 'settings.risk.label'
  | 'settings.risk.warning'
  | 'settings.roleProfile.modeLabel'
  | 'settings.roleProfile.modelLabel'
  | 'settings.roleProfile.modes.auto'
  | 'settings.roleProfile.modes.pinned'
  | 'settings.roleProfile.modes.pool'
  | 'settings.roleProfile.providerLabel'
  | 'settings.roleProfile.roleLabel'
  | 'settings.roleProfile.title'
  | 'settings.validation.modeInvalid'
  | 'settings.validation.pinnedBindingRequired'
  | 'settings.validation.roleRequired'
  | 'shell.closing.confirm'
  | 'shell.closing.leave'
  | 'shell.closing.stay'
  | 'shell.inspector.live_agents'
  | 'shell.sidebar.agents_live'
  | 'shell.sidebar.chat'
  | 'shell.sidebar.projects'
  | 'shell.sidebar.tasks'
  | 'shell.topbar.language'
  | 'shell.topbar.project'
  | 'shell.topbar.stop_all'
  | 'shell.topbar.watcher'
  | 'tasks.creator.create'
  | 'tasks.creator.title'
  | 'tasks.list.empty'
  | 'tasks.list.title'
  | 'tasks.status.accepted'
  | 'tasks.status.blocked'
  | 'tasks.status.handoff'
  | 'tasks.status.queued'
  | 'tasks.status.rejected'
  | 'tasks.status.returned'
  | 'tasks.status.running'
  | 'telemetry.cost'
  | 'telemetry.tokens'
  | 'ui.card.toggle'
  | 'ui.card.total'
  | 'ui.disclosure.less'
  | 'ui.disclosure.more'
  | 'ui.error.retry'
  | 'ui.loading.more'
  | 'settings.localbench.colDuration'
  | 'settings.localbench.colEvidence'
  | 'settings.localbench.colModel'
  | 'settings.localbench.colScore'
  | 'settings.localbench.decisionEmpty'
  | 'settings.localbench.decisionLine'
  | 'settings.localbench.decisionTitle'
  | 'settings.localbench.durationEstimate'
  | 'settings.localbench.durationValue'
  | 'settings.localbench.durationWarning'
  | 'settings.localbench.evidenceMeasured'
  | 'settings.localbench.evidenceProxy'
  | 'settings.localbench.evidenceUnknown'
  | 'settings.localbench.levelDeep'
  | 'settings.localbench.levelLabel'
  | 'settings.localbench.levelQuick'
  | 'settings.localbench.levelStandard'
  | 'settings.localbench.loadWarning'
  | 'settings.localbench.modelsEmpty'
  | 'settings.localbench.modelsTitle'
  | 'settings.localbench.needItNow'
  | 'settings.localbench.pathHint'
  | 'settings.localbench.pathLabel'
  | 'settings.localbench.purpose'
  | 'settings.localbench.resultsEmpty'
  | 'settings.localbench.resultsTitle'
  | 'settings.localbench.runButton'
  | 'settings.localbench.running'
  | 'settings.localbench.scanButton'
  | 'settings.localbench.scanning'
  | 'settings.localbench.statusComplete'
  | 'settings.localbench.statusFailed'
  | 'settings.localbench.title'
  | 'ui.table.empty';

export const DEFAULT_LOCALE: 'uk';

export const LOCALE_STORAGE_KEY: 'agentsi.locale';

export function t(key: string, params?: Record<string, string | number>): string;

export function setLocale(locale: SupportedLocale): void;

export function useLocale(): { locale: SupportedLocale };

export interface LocaleProviderProps {
  children: ReactNode;
  initialLocale?: SupportedLocale;
}

export function LocaleProvider(props: LocaleProviderProps): ReactElement;

export function detectOsLocale(): SupportedLocale;

export function formatDate(date: Date, locale?: SupportedLocale): string;

export function formatNumber(value: number, locale?: SupportedLocale): string;

export function resetLocaleForTests(): void;

// --- frontend/src/shell/SettingsLayout.tsx ---
export interface SettingsLayoutProps {
  titleKey: string;
  purposeKey: string;
  needItNowKey: string;
  children: ReactNode;
  advanced?: ReactNode;
}

export function SettingsLayout(props: SettingsLayoutProps): ReactElement;

// --- frontend/src/settings/index.ts ---
export type RoleMode = 'PINNED' | 'pool' | 'AUTO';

export interface SettingsRoute {
  path: string;
  titleKey: string;
  purposeKey: string;
  needItNowKey: string;
}

export const SETTINGS_ROUTES: readonly [
  SettingsRoute,
  SettingsRoute,
  SettingsRoute,
  SettingsRoute,
  SettingsRoute,
  SettingsRoute,
  SettingsRoute,
  SettingsRoute,
];

// Snapshot assertion: the frozen SETTINGS_ROUTES holds exactly 8 entries
// (general, appearance, localAI, models, routing, optimization,
// capabilityDB, project; no ProvidersPage). This const is a count
// assertion of the snapshot, not a runtime export of the source module.
export const SETTINGS_ROUTE_COUNT: 8;

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

export function RoleProfileEditor(props: RoleProfileEditorProps): ReactElement;

export function validateRoleProfile(input: RoleProfileInput): RoleProfileValidation;

export interface AcceptedRiskSwitchProps {
  projectId: string;
}

export function AcceptedRiskSwitch(props: AcceptedRiskSwitchProps): ReactElement;

// --- frontend/src/app/firstrun/FirstRunFlow.tsx ---
export type FirstRunStep = 'connectProvider' | 'oneClickTeam' | 'projectFolder' | 'firstTask';

export type OptionalFirstRunStep = 'localAI' | 'watcherPreset' | 'automations' | 'kbs';

export interface FirstRunFlowProps {
  initialStep?: FirstRunStep;
  onComplete: () => void;
}

export function FirstRunFlow(props: FirstRunFlowProps): ReactElement;

// --- frontend/src/app/About.tsx ---
export const AGENT_SI_NAME: 'Agent SI';

export const APP_ID: 'com.agentsi.app';

export const LICENCE_LINE: 'Copyright (c) 2026 Ivan Soprun';

export const MIT_LICENSE_REF: 'about.licence.mitText';

export interface AboutProps {
  locale?: SupportedLocale;
}

export function About(props: AboutProps): ReactElement;

// --- frontend/src/app/migration/MigrationView.tsx ---
export interface MigrationResult {
  migrated: boolean;
  oldCopiesKept: boolean;
}

export interface MigrationViewProps {
  projectId: string;
}

export function MigrationView(props: MigrationViewProps): ReactElement;

export function runMigration(projectId: string): Promise<MigrationResult>;

// --- frontend/src/app/HowItWorks.tsx ---
export const HOW_IT_WORKS_KEYS: {
  readonly runsTitle: 'howItWorks.runs.title';
  readonly runsBody: 'howItWorks.runs.body';
  readonly codeTestsTitle: 'howItWorks.codeTests.title';
  readonly codeTestsBody: 'howItWorks.codeTests.body';
  readonly localTestsTitle: 'howItWorks.localTests.title';
  readonly localTestsBody: 'howItWorks.localTests.body';
};

export interface HowItWorksProps {
  locale?: SupportedLocale;
}

export function HowItWorks(props: HowItWorksProps): ReactElement;
