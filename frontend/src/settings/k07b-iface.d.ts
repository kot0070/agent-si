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
// (420 mirrored keys each; parity verified by paired full-file reads, diagnostics section included).
export type LocaleKey =
  | 'about.licence.line'
  | 'about.licence.mitText'
  | 'about.thirdParty.title'
  | 'agents.badge.cloud'
  | 'agents.badge.local'
  | 'agents.badge.split'
  | 'agents.live.empty'
  | 'agents.live.subtitle'
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
  | 'chat.composer.noModel'
  | 'chat.composer.prompt'
  | 'chat.composer.send'
  | 'chat.composer.statusReady'
  | 'chat.hierarchy.agents'
  | 'chat.composer.statusWorking'
  | 'chat.hierarchy.auditorSplit'
  | 'chat.hierarchy.auto'
  | 'chat.hierarchy.collapse'
  | 'chat.hierarchy.connect'
  | 'chat.hierarchy.director'
  | 'chat.hierarchy.expand'
  | 'chat.hierarchy.manager'
  | 'chat.hierarchy.noProject'
  | 'chat.hierarchy.openSettings'
  | 'chat.hierarchy.title'
  | 'chat.permission.allowOnce'
  | 'chat.permission.allowProject'
  | 'chat.permission.allowed'
  | 'chat.permission.body'
  | 'chat.permission.denied'
  | 'chat.permission.deny'
  | 'chat.permission.title'
  | 'chat.permission.why'
  | 'chat.stream.offline'
  | 'chat.stream.spinner'
  | 'chat.stream.timestamp'
  | 'diagnostics.benchCheck'
  | 'diagnostics.benchHistory'
  | 'diagnostics.localeCoverage'
  | 'diagnostics.needItNow'
  | 'diagnostics.purpose'
  | 'diagnostics.telemetry'
  | 'diagnostics.telemetryThemes'
  | 'diagnostics.title'
  | 'empty.generic'
  | 'errors.generic'
  | 'firstrun.greeting'
  | 'firstrun.next'
  | 'firstrun.optional.automations'
  | 'firstrun.optional.kbs'
  | 'firstrun.optional.localAI'
  | 'firstrun.optional.watcherPreset'
  | 'firstrun.optionalNote'
  | 'firstrun.provider.localNote'
  | 'firstrun.skip'
  | 'firstrun.steps.connectProvider'
  | 'firstrun.steps.firstTask'
  | 'firstrun.steps.oneClickTeam'
  | 'firstrun.steps.projectFolder'
  | 'firstrun.title'
  | 'howItWorks.codeTests.body'
  | 'howItWorks.codeTests.title'
  | 'howItWorks.localTests.body'
  | 'howItWorks.localTests.title'
  | 'howItWorks.runs.body'
  | 'howItWorks.runs.title'
  | 'migration.done'
  | 'migration.keepsOldCopies'
  | 'migration.title'
  | 'projectForm.folder.label'
  | 'projectForm.folder.placeholder'
  | 'projectForm.name.label'
  | 'projectForm.name.placeholder'
  | 'projectView.attempts'
  | 'projects.ai_usage.title'
  | 'projectView.audits.attention'
  | 'projects.audits.title'
  | 'projectView.audits.projectAudits'
  | 'projects.cloud_ai.title'
  | 'projectView.audits.projectTasks'
  | 'projects.cost.title'
  | 'projectView.blockedNote'
  | 'projects.derived.label'
  | 'projectView.cost.limit'
  | 'projects.errors.title'
  | 'projectView.cost.limitExplainer'
  | 'projects.folder.choose'
  | 'projectView.cost.notKnown'
  | 'projectView.cost.remaining'
  | 'projects.kbAttach.kbId'
  | 'projectView.cost.reserved'
  | 'projects.kbAttach.kind'
  | 'projectView.cost.spent'
  | 'projects.kbAttach.purpose'
  | 'projectView.errors.blockedAgents'
  | 'projects.kbAttach.submit'
  | 'projectView.errors.failedTasks'
  | 'projects.kbAttach.title'
  | 'projectView.finished'
  | 'projects.list.create'
  | 'projectView.models.liveTitle'
  | 'projects.list.created'
  | 'projectView.noLedger'
  | 'projects.list.duplicate'
  | 'projects.list.empty'
  | 'projectView.noLive'
  | 'projectView.live.role'
  | 'projectView.live.model'
  | 'projectView.live.tokens'
  | 'projectView.live.cost'
  | 'projects.list.subtitle'
  | 'projectView.overview.ageDays'
  | 'projects.list.title'
  | 'projectView.overview.created'
  | 'projects.local_ai.title'
  | 'projectView.purpose.aiUsage'
  | 'projects.models.title'
  | 'projectView.purpose.audits'
  | 'projects.overview.title'
  | 'projectView.purpose.cloudAi'
  | 'projects.reports.subtitle'
  | 'projectView.purpose.cost'
  | 'projects.reports.title'
  | 'projectView.purpose.errors'
  | 'projects.routing.title'
  | 'projectView.purpose.localAi'
  | 'projects.runs.title'
  | 'projects.runs.empty'
  | 'projectView.purpose.models'
  | 'projects.tests.counter.active'
  | 'projectView.purpose.overview'
  | 'projects.tests.counter.passed'
  | 'projectView.purpose.reports'
  | 'projects.tests.counter.remaining'
  | 'projectView.purpose.routing'
  | 'projects.tests.emptyHow'
  | 'projectView.purpose.runs'
  | 'projects.tests.explainer'
  | 'projectView.purpose.tasks'
  | 'projects.tests.hideOutput'
  | 'projectView.purpose.time'
  | 'projects.tests.kind.ai'
  | 'projectView.purpose.tokens'
  | 'projects.tests.kind.code'
  | 'projectView.reports.agents'
  | 'projects.tests.kind.human'
  | 'projectView.reports.changedFiles'
  | 'projects.tests.kind.unknown'
  | 'projectView.reports.noFiles'
  | 'projects.tests.local.body'
  | 'projectView.reports.packages'
  | 'projects.tests.local.label'
  | 'projectView.reports.peak'
  | 'projects.tests.local.off'
  | 'projectView.reports.remaining'
  | 'projects.tests.local.on'
  | 'projectView.reports.reserved'
  | 'projects.tests.local.title'
  | 'projectView.reports.spent'
  | 'projects.tests.showOutput'
  | 'projectView.reports.tasks'
  | 'projects.tests.title'
  | 'projectView.reports.wall'
  | 'projects.time.title'
  | 'projectView.runs.agents'
  | 'projects.tokens.title'
  | 'projectView.runs.files'
  | 'projects.why_this_model.detail'
  | 'projectView.runs.package'
  | 'projects.why_this_model.title'
  | 'projectView.runs.peak'
  | 'providers.chat.contributorWarning'
  | 'projectView.runs.verdict'
  | 'providers.chat.label'
  | 'projectView.runs.wall'
  | 'providers.chat.selectOption'
  | 'projectView.tabsLabel'
  | 'providers.connect.apiKey'
  | 'projectView.time.package'
  | 'providers.connect.baseUrl'
  | 'projectView.time.seconds'
  | 'providers.connect.cancel'
  | 'projectView.tokens.calls'
  | 'providers.connect.close'
  | 'projectView.tokens.empty'
  | 'providers.connect.closeGlyph'
  | 'projectView.tokens.explainer'
  | 'providers.connect.connected'
  | 'projectView.tokens.model'
  | 'providers.connect.failedCode'
  | 'projectView.tokens.role'
  | 'providers.connect.failedGeneric'
  | 'projectView.tokens.used'
  | 'providers.connect.failedMessage'
  | 'providers.connect.getKey'
  | 'providers.connect.retryHint'
  | 'providers.connect.storeNote'
  | 'providers.connect.unknownModelsNote'
  | 'providers.connect.hintMismatch'
  | 'providers.connect.keyFormat'
  | 'providers.connect.kind'
  | 'providers.connect.providerId'
  | 'providers.connect.refusedMismatch'
  | 'providers.connect.refusedNoModel'
  | 'providers.connect.save'
  | 'providers.connect.saveFailed'
  | 'providers.connect.needOneModel'
  | 'providers.connect.saving'
  | 'providers.connect.timeout'
  | 'providers.connect.title'
  | 'providers.disconnect.body'
  | 'providers.disconnect.busy'
  | 'providers.disconnect.cancel'
  | 'providers.disconnect.close'
  | 'providers.disconnect.closeGlyph'
  | 'providers.disconnect.confirm'
  | 'providers.disconnect.failed'
  | 'providers.disconnect.failedCode'
  | 'providers.disconnect.failedGeneric'
  | 'providers.disconnect.failedMessage'
  | 'providers.disconnect.refused'
  | 'providers.disconnect.title'
  | 'providers.leftover.cancel'
  | 'providers.leftover.confirmDelete'
  | 'providers.leftover.created'
  | 'providers.leftover.delete'
  | 'providers.leftover.deleteAria'
  | 'providers.leftover.deleteFailed'
  | 'providers.leftover.deleted'
  | 'providers.leftover.empty'
  | 'providers.leftover.inUse'
  | 'providers.leftover.inUseTitle'
  | 'providers.leftover.listFailed'
  | 'providers.leftover.rotated'
  | 'providers.page.chatSaveError'
  | 'providers.page.chatSaveFailed'
  | 'providers.page.chatSaved'
  | 'providers.page.chatTitle'
  | 'providers.page.connectCta'
  | 'providers.page.connectLabel'
  | 'providers.page.disconnectCta'
  | 'providers.page.disconnectLabel'
  | 'providers.page.leftoverTitle'
  | 'providers.page.noneEnabled'
  | 'providers.page.poolSaveFailed'
  | 'providers.page.poolSaved'
  | 'providers.page.rolePoolsTitle'
  | 'providers.page.searchLabel'
  | 'providers.page.setupHide'
  | 'providers.page.setupSaved'
  | 'providers.page.setupShow'
  | 'providers.page.setupTitle'
  | 'providers.page.title'
  | 'providers.role.auditor'
  | 'providers.role.director'
  | 'providers.role.manager'
  | 'providers.role.watcher'
  | 'providers.role.worker'
  | 'providers.rolepool.helpAuto'
  | 'providers.rolepool.helpPinned'
  | 'providers.rolepool.helpPool'
  | 'providers.rolepool.modeAuto'
  | 'providers.rolepool.modePinned'
  | 'providers.rolepool.modePool'
  | 'providers.rolepool.pinnedAria'
  | 'providers.rolepool.selectOption'
  | 'providers.rolepool.strategyAria'
  | 'providers.rolepool.strategyAuto'
  | 'providers.rolepool.strategyDirectorPerTask'
  | 'providers.rolepool.strategyFallbackOrder'
  | 'providers.rolepool.strategyHelpAuto'
  | 'providers.rolepool.strategyHelpDirectorPerTask'
  | 'providers.rolepool.strategyHelpFallbackOrder'
  | 'providers.rolepool.strategyHelpSplitParallel'
  | 'providers.rolepool.strategySplitParallel'
  | 'providers.setup.autoOption'
  | 'providers.setup.finish'
  | 'providers.setup.hint'
  | 'providers.setup.title'
  | 'settings.appearance.needItNow'
  | 'settings.appearance.purpose'
  | 'settings.appearance.title'
  | 'settings.capabilityDb.needItNow'
  | 'settings.capabilityDb.purpose'
  | 'settings.capabilityDb.result'
  | 'settings.capabilityDb.title'
  | 'settings.capabilityDb.update'
  | 'settings.general.needItNow'
  | 'settings.general.purpose'
  | 'settings.general.title'
  | 'settings.hub.about'
  | 'settings.hub.howItWorks'
  | 'settings.grants.empty'
  | 'settings.grants.remove'
  | 'settings.grants.title'
  | 'settings.index.subtitle'
  | 'settings.localAi.needItNow'
  | 'settings.localAi.purpose'
  | 'settings.localAi.title'
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
  | 'settings.project.parallel'
  | 'settings.project.purpose'
  | 'settings.project.save'
  | 'settings.project.spendCaps'
  | 'settings.project.stepsHint'
  | 'settings.project.taskStepsLabel'
  | 'settings.project.chatStepsLabel'
  | 'settings.project.title'
  | 'settings.providers.searchPlaceholder'
  | 'settings.risk.label'
  | 'settings.risk.warning'
  | 'settings.roleProfile.modeLabel'
  | 'settings.roleProfile.modelLabel'
  | 'settings.roleProfile.modes.auto'
  | 'settings.roleProfile.modes.pinned'
  | 'settings.roleProfile.modes.pool'
  | 'settings.roleProfile.notSet'
  | 'settings.roleProfile.providerLabel'
  | 'settings.roleProfile.roleLabel'
  | 'settings.roleProfile.title'
  | 'settings.routing.needItNow'
  | 'settings.routing.purpose'
  | 'settings.routing.title'
  | 'settings.validation.modeInvalid'
  | 'settings.validation.pinnedBindingRequired'
  | 'settings.validation.roleRequired'
  | 'shell.cards.apps.active'
  | 'shell.cards.apps.connected'
  | 'shell.cards.apps.paused'
  | 'shell.cards.apps.subtitle'
  | 'shell.cards.apps.title'
  | 'shell.cards.apps.total'
  | 'shell.cards.background.subtitle'
  | 'shell.cards.background.title'
  | 'shell.cards.budget.remaining'
  | 'shell.cards.budget.reserved'
  | 'shell.cards.budget.spent'
  | 'shell.cards.budget.subtitle'
  | 'shell.cards.budget.title'
  | 'shell.cards.budget.total'
  | 'shell.cards.context.input'
  | 'shell.cards.context.noUsage'
  | 'shell.cards.context.output'
  | 'shell.cards.context.percent'
  | 'shell.cards.context.percentValue'
  | 'shell.cards.context.source'
  | 'shell.cards.context.sourceLive'
  | 'shell.cards.context.subtitle'
  | 'shell.cards.context.title'
  | 'shell.cards.context.window'
  | 'shell.cards.context.windowValue'
  | 'shell.cards.localai.subtitle'
  | 'shell.cards.localai.title'
  | 'shell.cards.localai.total'
  | 'shell.cards.providers.subtitle'
  | 'shell.cards.providers.title'
  | 'shell.cards.providers.total'
  | 'shell.cards.results.next'
  | 'shell.cards.results.open'
  | 'shell.cards.results.openFolder'
  | 'shell.cards.results.subtitle'
  | 'shell.cards.results.title'
  | 'shell.cards.showLess'
  | 'shell.cards.team.file'
  | 'shell.cards.showMore'
  | 'shell.cards.team.lastAction'
  | 'shell.cards.team.openAgents'
  | 'shell.cards.team.silentMin'
  | 'shell.cards.team.step'
  | 'shell.cards.team.subtitle'
  | 'shell.cards.team.title'
  | 'shell.cards.team.waiting'
  | 'shell.cards.team.warnings'
  | 'shell.cards.tests.subtitle'
  | 'shell.cards.tests.title'
  | 'shell.cards.tests.total'
  | 'shell.cards.tokens.subtitle'
  | 'shell.cards.tokens.title'
  | 'shell.cards.tokens.total'
  | 'shell.cards.watcher.failed'
  | 'shell.cards.watcher.ok'
  | 'shell.cards.watcher.open'
  | 'shell.cards.watcher.state'
  | 'shell.cards.watcher.subtitle'
  | 'shell.cards.watcher.title'
  | 'shell.closing.confirm'
  | 'shell.closing.leave'
  | 'shell.closing.stay'
  | 'shell.common.unknown'
  | 'shell.inspector.live_agents'
  | 'shell.sidebar.agents_live'
  | 'shell.sidebar.chat'
  | 'shell.sidebar.projects'
  | 'shell.sidebar.resultsHint'
  | 'shell.sidebar.settings'
  | 'shell.sidebar.tasks'
  | 'shell.topbar.brand'
  | 'shell.topbar.language'
  | 'shell.topbar.panels'
  | 'shell.topbar.project'
  | 'shell.topbar.projectPlaceholder'
  | 'shell.topbar.stop_all'
  | 'shell.topbar.stop_clear'
  | 'shell.topbar.stop_result'
  | 'shell.topbar.watcher'
  | 'tasks.creator.create'
  | 'tasks.creator.subtitle'
  | 'tasks.creator.title'
  | 'tasks.creator.titleRequired'
  | 'tasks.list.empty'
  | 'tasks.list.title'
  | 'tasks.status.accepted'
  | 'tasks.status.blocked'
  | 'tasks.status.handoff'
  | 'tasks.status.queued'
  | 'tasks.status.rejected'
  | 'tasks.status.returned'
  | 'tasks.status.running'
  | 'telemetry.audits'
  | 'telemetry.calls'
  | 'telemetry.cost'
  | 'telemetry.model'
  | 'telemetry.perModel'
  | 'telemetry.perProvider'
  | 'telemetry.project'
  | 'telemetry.provider'
  | 'telemetry.tasks'
  | 'telemetry.tokens'
  | 'telemetry.unavailable'
  | 'ui.card.toggle'
  | 'ui.card.total'
  | 'ui.disclosure.less'
  | 'ui.disclosure.more'
  | 'ui.error.retry'
  | 'ui.loading.more'
  | 'ui.table.empty'
  | 'watcher.tab.cloudFallback'
  | 'watcher.tab.failed'
  | 'watcher.tab.loading'
  | 'watcher.tab.fallbackNote'
  | 'watcher.tab.model'
  | 'watcher.tab.modelApi'
  | 'watcher.tab.modelLocal'
  | 'watcher.tab.modelOff'
  | 'watcher.tab.ok'
  | 'watcher.tab.settings'
  | 'watcher.tab.subtitle';

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
