// Lane A app composition root: route table per frontend/src/app/iface.ts,
// chat-first layout with top bar, short navigation, compact inspector and
// unsaved-edit guard. Every route mounts the real wave-1/wave-2 page with
// record data from the shared ApiClient entry; page chunks load lazily so
// the first paint stays chat-first. Production entry:
// frontend/src/app/main.tsx.

import { Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import {
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import type { RouteTable } from "./iface";
import type { ApiClient } from "../api/iface";
import type { ProjectRecord } from "../api/iface";
import { ENDPOINTS } from "../api/endpoints";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import {
  useApiClient,
  useCurrentProject,
} from "./ApiClientProvider";
import type { CurrentProject } from "./ApiClientProvider";
import { ProjectListProvider, useProjectList } from "../projects/projectList";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  LocaleProvider,
  setLocale,
  t,
  useLocale,
} from "../locale/index";
import type { SupportedLocale } from "../locale/index";
import { SETTINGS_GROUPS, SETTINGS_HELP_ROWS, SETTINGS_ROUTES, AcceptedRiskSwitch, FirstRunGate, InstallGrantsList, RoleProfileEditor, clearFirstRunDone, markFirstRunDone } from "../settings/index";
import { listConnectedProviders } from "../settings/ProvidersPage/connectApi";
import { getProviderCatalog } from "../settings/ProvidersPage/catalog";
import { OptimizationPolicySection } from "../settings/optimizationPolicy";
import { LocalConnectSection, ProvidersPage } from "../settings/ProvidersPage";
import {
  LocalBenchDecisionList,
  LocalBenchTab,
  readStoredLocalBench,
} from "../settings/LocalBenchTab";
import { HttpLocalBenchClient } from "../settings/LocalBenchClient";
import { EVIDENCE_LOCALE_KEYS } from "../settings/LocalBenchTypes";
import { SettingsLayout } from "../shell/SettingsLayout";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import { TopBar, TOPBAR_LOCALE_EVENT } from "../shell/TopBar";
import { Sidebar } from "../shell/Sidebar";
import { ThemeToggle } from "../shell/ThemeToggle";
import { readTheme } from "../shell/theme";
import { ContractDefaultsBar } from "../settings/ContractDefaultsBar";
import { Inspector } from "../shell/Inspector";
import { ClosingGuard } from "../shell/ClosingGuard";
import { useLivePumpActive } from "../chat/index";
import type { ProjectViewName } from "../projects/ProjectView";
import { LocaleCoverage } from "../k07next/LocaleCoverage";
import { TelemetryThemes } from "../k07next/TelemetryThemes";
import { BenchGatewayCheck } from "../k07next2/BenchGatewayCheck";
import { TelemetrySummary } from "../k07next2/TelemetrySummary";
import { BenchHistoryList } from "../k07next3/BenchHistoryList";
import { DiagnosticsSection } from "../settings/DiagnosticsSection";
import { QaCatalogSection } from "../settings/QaCatalogSection";
import { WatcherTab } from "../watcher/WatcherTab";
import { AutomationsPage } from "../automations/AutomationsPage";
import { KbRefreshProposal } from "../k07next2/KbRefreshProposal";

export const ROUTES: RouteTable = {
  chat: "/",
  agentsLive: "/agents/live",
  projects: "/projects",
  projectOverview: "/projects/:projectId/overview",
  projectTasks: "/projects/:projectId/tasks",
  projectRuns: "/projects/:projectId/runs",
  projectTime: "/projects/:projectId/time",
  projectAiUsage: "/projects/:projectId/ai-usage",
  projectTokens: "/projects/:projectId/tokens",
  projectCost: "/projects/:projectId/cost",
  projectLocalAi: "/projects/:projectId/local-ai",
  projectCloudAi: "/projects/:projectId/cloud-ai",
  projectModels: "/projects/:projectId/models",
  projectRouting: "/projects/:projectId/routing-decisions",
  projectAudits: "/projects/:projectId/audits",
  projectErrors: "/projects/:projectId/errors",
  projectReports: "/projects/:projectId/reports",
};

// FXTESTSUI: the Tests tab route path. It lives next to ROUTES (not in
// it) because the frozen RouteTable in app/iface.ts is owned by another
// lane; the literal path below matches the merged project route shape.
export const TESTS_ROUTE_PATH = "/projects/:projectId/tests";

// FXCHATHIST Part 2: the Chat tab route path, same pattern as the Tests
// tab above (frozen RouteTable untouched). Every project entry point
// (Sidebar, TopBar, ProjectsPage) lands here: the mounted ChatArea reads
// the store slice plus the served history for that project.
export const CHAT_TAB_ROUTE_PATH = "/projects/:projectId/chat";

const ChatAreaView = lazy(() =>
  import("../chat/index").then((module) => ({ default: module.ChatArea })),
);
const AgentsLiveView = lazy(() =>
  import("../agents/AgentsLive").then((module) => ({
    default: module.AgentsLive,
  })),
);
const ProjectsPageView = lazy(() =>
  import("../projects/ProjectsPage").then((module) => ({
    default: module.ProjectsPage,
  })),
);
const ProjectViewPage = lazy(() =>
  import("../projects/ProjectView").then((module) => ({
    default: module.ProjectView,
  })),
);
const TaskComposerView = lazy(() =>
  import("../tasks/TaskComposer").then((module) => ({
    default: module.TaskComposer,
  })),
);
const TeamModelQuickFixView = lazy(() =>
  import("../tasks/TeamModelQuickFix").then((module) => ({
    default: module.TeamModelQuickFix,
  })),
);
const AboutView = lazy(() =>
  import("./About").then((module) => ({ default: module.About })),
);

// R-372: the routed About confirms the shipped third-party notices;
// the bare component keeps them opt-in so embeds stay minimal.
function AboutRoute(): ReactElement {
  return <AboutView showThirdParty />;
}
const FirstRunFlowView = lazy(() =>
  import("./firstrun/FirstRunFlow").then((module) => ({
    default: module.FirstRunFlow,
  })),
);
const HowItWorksView = lazy(() =>
  import("./HowItWorks").then((module) => ({ default: module.HowItWorks })),
);
const MigrationViewPage = lazy(() =>
  import("./migration/MigrationView").then((module) => ({
    default: module.MigrationView,
  })),
);

// Stored local-AI config panel: the bench-stored scan path and models with
// evidence, the endpoint string from the ENDPOINTS registry, and the bench
// per-change decision record. Read-only; the bench tab owns the flow that
// writes the stored state. Every label resolves through the locale; the
// stored values and the registry string render raw.
function LocalAiStoredPanel(): ReactElement {
  const stored = readStoredLocalBench();
  return (
    <div data-testid="localai-stored">
      <h3>{t("settings.localbench.modelsTitle")}</h3>
      {stored.path === null ? null : (
        <p data-testid="localai-path">
          <span>{t("settings.localbench.pathLabel")}</span>
          <span>{stored.path}</span>
        </p>
      )}
      {stored.models.length === 0 ? (
        <p data-testid="localai-models-empty">
          {t("settings.localbench.modelsEmpty")}
        </p>
      ) : (
        <ul data-testid="localai-models">
          {stored.models.map((model) => (
            <li
              key={model.model_id}
              data-testid={`localai-model-${model.model_id}`}
            >
              <span>{model.display_name}</span>
              <span>{t(EVIDENCE_LOCALE_KEYS[model.evidence])}</span>
            </li>
          ))}
        </ul>
      )}
      <LocalBenchDecisionList decisions={stored.decisions} />
    </div>
  );
}

function useOptionalApiClient(): ApiClient | null {
  try {
    return useApiClient();
  } catch {
    return null;
  }
}

function useOptionalCurrentProject(): CurrentProject | null {
  try {
    return useCurrentProject();
  } catch {
    return null;
  }
}

function readStoredLocale(): SupportedLocale {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored === "en" || stored === "uk") {
      return stored;
    }
  } catch {
    // Storage unavailable: fall back to the default locale.
  }
  return DEFAULT_LOCALE;
}

// Chat-first start box for the no-project case (kit PRODUCT_SPEC:4154):
// the / route always mounts a working message box; the first sent message
// creates the first project and starts a task in it, then selects it so the
// route continues in the regular chat surface. Reuses the chat composer
// testids so the route stays chat-first before any project exists.
function ChatStartBox(props: {
  initialDraft?: string;
  onFirstMessage?: (projectId: string, message: string) => void;
}): ReactElement {
  const client = useApiClient();
  const current = useCurrentProject();
  // FXPROJ J1: the first message creates the project after every list
  // mounted; refresh the shared list so the left rows and the Projects
  // page show it at once.
  const { refresh } = useProjectList();
  const [draft, setDraft] = useState(props.initialDraft ?? "");
  const [busy, setBusy] = useState(false);
  const [blocking, setBlocking] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);

  async function handleSend(): Promise<void> {
    const message = draft.trim();
    if (message === "" || busy) {
      return;
    }
    setBusy(true);
    setBlocking(null);
    try {
      const compact = message.replace(/\s+/g, " ").slice(0, 80);
      const project = await client.createProject({
        name: compact,
        folder_ref: compact,
      });
      current.select(project.project_id);
      refresh();
      await client.createTask(project.project_id, {
        title: message,
        scope: [],
      });
      setDraft("");
      props.onFirstMessage?.(project.project_id, message);
    } catch (error) {
      if (error instanceof ApiError) {
        setBlocking({
          errorKey: apiErrorLocaleKey(error.code),
          code: error.code,
        });
      } else {
        setBlocking({ errorKey: "errors.generic", code: "CONTEXT_MISSING" });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section data-testid="chat-area" aria-label={t("shell.sidebar.chat")}>
      {/* FXDESIGN6: no visible "Chat" heading; the h1 stays for the
          frozen heading contract. */}
      <h1 className="fx-vh">{t("shell.sidebar.chat")}</h1>
      <div data-testid="chat-composer" className="fx-composer">
        <label>
          {t("chat.composer.prompt")}
          <input
            data-testid="chat-prompt"
            id="chat-prompt"
            type="text"
            placeholder={t("chat.composer.prompt")}
            aria-label={t("chat.composer.prompt")}
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void handleSend();
              }
            }}
          />
        </label>
        <button
          type="button"
          data-testid="chat-send"
          disabled={draft.trim() === "" || busy}
          onClick={() => {
            void handleSend();
          }}
        >
          {t("chat.composer.send")}
        </button>
        {busy ? (
          <span data-testid="chat-spinner" role="status">
            {t("chat.stream.spinner")}
          </span>
        ) : null}
      </div>
      {blocking !== null ? (
        <ErrorPanel
          errorKey={blocking.errorKey}
          code={blocking.code}
          onRetry={() => {
            void handleSend();
          }}
        />
      ) : null}
    </section>
  );
}

function ChatRoute(props: {
  initialDraft: string | null;
  oneShot: { projectId: string; text: string } | null;
  onFirstMessage?: (projectId: string, message: string) => void;
  onOneShotConsumed?: () => void;
}): ReactElement {
  const current = useCurrentProject();
  if (current.projectId === null) {
    return (
      <ChatStartBox
        initialDraft={props.initialDraft ?? undefined}
        onFirstMessage={props.onFirstMessage}
      />
    );
  }
  if (
    props.oneShot !== null &&
    props.oneShot.projectId === current.projectId
  ) {
    return (
      <ChatAreaView
        projectId={current.projectId}
        initialDraft={props.initialDraft ?? undefined}
        initialSend={props.oneShot.text}
        onSendConsumed={props.onOneShotConsumed}
      />
    );
  }
  return (
    <ChatAreaView
      projectId={current.projectId}
      initialDraft={props.initialDraft ?? undefined}
    />
  );
}

function AgentsRoute(): ReactElement {
  const current = useCurrentProject();
  if (current.projectId === null) {
    return <ProjectsPageView />;
  }
  return <AgentsLiveView projectId={current.projectId} />;
}

function MigrationRoute(): ReactElement {
  const current = useCurrentProject();
  if (current.projectId === null) {
    return <ProjectsPageView />;
  }
  return <MigrationViewPage projectId={current.projectId} />;
}

function WatcherRoute(): ReactElement {
  const current = useCurrentProject();
  if (current.projectId === null) {
    return <ProjectsPageView />;
  }
  return <WatcherTab projectId={current.projectId} />;
}

// W6: every project tab click/Enter navigates through the App router;
// ProjectView only calls back, so a single onSelect covers all views.
function useProjectSelect(projectId: string): (view: ProjectViewName) => void {
  const navigate = useNavigate();
  return (view: ProjectViewName) => {
    navigate(`/projects/${projectId}/${view}`);
  };
}

function TasksRoute(props: { projectId: string }): ReactElement {
  const [search] = useSearchParams();
  const initialTaskId = search.get("initialTask");
  const onSelect = useProjectSelect(props.projectId);
  return (
    <>
      <ProjectViewPage
        projectId={props.projectId}
        view="tasks"
        onSelect={onSelect}
      />
      <TaskComposerView
        projectId={props.projectId}
        initialTaskId={initialTaskId}
      />
    </>
  );
}

function ModelsRoute(props: {
  projectId: string;
  decisionId?: string;
}): ReactElement {
  const client = useApiClient();
  const [binding, setBinding] = useState<{
    providerId: string;
    model: string;
  } | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const decisionId = props.decisionId;
  useEffect(() => {
    if (decisionId === undefined) {
      return;
    }
    let alive = true;
    client.readRoutingWhy(decisionId).then(
      (why) => {
        if (!alive) {
          return;
        }
        const first = why.assignments[0];
        if (first !== undefined) {
          setBinding({
            providerId: first.provider_id,
            model: first.model,
          });
        }
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [client, decisionId]);
  const onSelect = useProjectSelect(props.projectId);
  return (
    <>
      <ProjectViewPage
        projectId={props.projectId}
        view="models"
        decisionId={decisionId}
        onSelect={onSelect}
      />
      {binding !== null && !dismissed ? (
        <TeamModelQuickFixView
          projectId={props.projectId}
          providerId={binding.providerId}
          model={binding.model}
          onApply={(next) => {
            setBinding(next);
          }}
          onDismiss={() => {
            setDismissed(true);
          }}
        />
      ) : null}
    </>
  );
}

function LocalAiRoute(props: { projectId: string }): ReactElement {
  const onSelect = useProjectSelect(props.projectId);
  return (
    <>
      <ProjectViewPage
        projectId={props.projectId}
        view="local-ai"
        onSelect={onSelect}
      />
      <LocalAiStoredPanel />
    </>
  );
}

// FXCHATHIST Part 2: the project Chat tab. Renders the same ChatArea as
// the root chat route, bound to the URL project; selects it into the
// current project so the shell (TopBar, Sidebar, Inspector) follows.
// FXLOOK D8: the chat route carries NO tab strip and NO purpose line —
// chat and project data are separate surfaces. The top holds one line:
// the project name plus a quiet Project-details button opening the
// Overview data view (whose strip carries Chat first to come back).
function ChatTabRoute(): ReactElement {
  const params = useParams();
  const client = useApiClient();
  const current = useCurrentProject();
  const projectId = params.projectId;
  // Unconditional: hooks never run behind the project guard below.
  const onSelect = useProjectSelect(projectId ?? "");
  const [projectName, setProjectName] = useState<string | null>(null);
  useEffect(() => {
    if (projectId !== undefined && projectId !== current.projectId) {
      current.select(projectId);
    }
  }, [projectId, current]);
  useEffect(() => {
    if (projectId === undefined) {
      return;
    }
    let alive = true;
    client.readProject(projectId).then(
      (project) => {
        if (alive) {
          setProjectName(project.name);
        }
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [client, projectId]);
  if (projectId === undefined) {
    return <ProjectsPageView />;
  }
  return (
    <div className="fx-chat-route">
      <div data-testid="chat-route-head" className="fx-chat-head">
        <span data-testid="chat-route-project">
          {projectName ?? projectId}
        </span>
        <button
          type="button"
          data-testid="project-details-open"
          className="fx-btn-quiet"
          onClick={() => {
            onSelect("overview");
          }}
        >
          {t("projects.details.open")}
        </button>
      </div>
      <ChatAreaView projectId={projectId} />
    </div>
  );
}
function ProjectSubview(props: { view: ProjectViewName }): ReactElement {
  const params = useParams();
  const [search] = useSearchParams();
  const projectId = params.projectId;
  // Unconditional: hooks never run behind the project guard below.
  const onSelect = useProjectSelect(projectId ?? "");
  if (projectId === undefined) {
    return <ProjectsPageView />;
  }
  const decisionId = search.get("decision") ?? undefined;
  if (props.view === "tasks") {
    return <TasksRoute projectId={projectId} />;
  }
  if (props.view === "models") {
    return <ModelsRoute projectId={projectId} decisionId={decisionId} />;
  }
  if (props.view === "local-ai") {
    return <LocalAiRoute projectId={projectId} />;
  }
  return (
    <ProjectViewPage
      projectId={projectId}
      view={props.view}
      decisionId={decisionId}
      onSelect={onSelect}
    />
  );
}

// D7: the grouped section nav beside the content (settings-nav). It wraps
// the existing link strip (settings-tabs, same ten links plus Diagnostics),
// names each settings group, and adds a select for narrow windows. The
// active link carries aria-current="page" through NavLink.
function SettingsTabs(): ReactElement {
  const navigate = useNavigate();
  const params = useParams();
  const active = params.section ?? "";
  const sectionOptions = [
    ...SETTINGS_ROUTES.map((route) => ({
      path: route.path,
      title: t(route.titleKey),
    })),
    { path: "diagnostics", title: t("diagnostics.title") },
    { path: "automations", title: t("settings.automations.title") },
  ];
  return (
    <nav data-testid="settings-nav" aria-label={t("settings.index.title")}>
      <div>
        {SETTINGS_GROUPS.map((group) => (
          <span
            key={group.id}
            data-testid={`settings-nav-group-${group.id}`}
          >
            {t(group.titleKey)}{" "}
          </span>
        ))}
      </div>
      <select
        data-testid="settings-nav-select"
        aria-label={t("settings.index.title")}
        value={active}
        onChange={(event) => {
          navigate(`/settings/${event.target.value}`);
        }}
      >
        {sectionOptions.map((option) => (
          <option key={option.path} value={option.path}>
            {option.title}
          </option>
        ))}
      </select>
      <div data-testid="settings-tabs">
        {SETTINGS_ROUTES.map((route) => (
          <NavLink
            key={route.path}
            to={`/settings/${route.path}`}
            data-testid={`settings-link-${route.path}`}
            end
            className={({ isActive }) =>
              isActive ? "fx-tab-active" : undefined}
          >
            {t(route.titleKey)}
          </NavLink>
        ))}
        <NavLink
          key="diagnostics"
          to="/settings/diagnostics"
          data-testid="settings-link-diagnostics"
          className={({ isActive }) =>
            isActive ? "fx-tab-active" : undefined}
        >
          {t("diagnostics.title")}
        </NavLink>
        {/* FXAUTO: the Watcher and automations group is a row, not a tab,
            so the ten tab links counted by App.test stay exactly ten. */}
        <span data-testid="settings-group-watcher-automations">
          {t("settings.group.watcherAutomations")}
        </span>
        <NavLink
          key="automations"
          to="/settings/automations"
          data-testid="settings-row-automations"
          className={({ isActive }) =>
            isActive ? "fx-tab-active" : undefined}
        >
          {t("settings.automations.title")}
        </NavLink>
      </div>
    </nav>
  );
}

// R6: one quiet Back link on every settings section (Diagnostics
// included, which also closes R4).
function SettingsBackLink(): ReactElement {
  return (
    <Link to="/settings" data-testid="settings-back">
      {t("settings.backToSettings")}
    </Link>
  );
}

// R6: one grouped index row: icon, title, one-line purpose, current
// state at the right (from the section's real source; purpose only
// when the state cannot be read), chevron. Quiet links, no card
// buttons. Existing settings-link-* testids stay.
function SettingsRow(props: { path: string; marker: string }): ReactElement {
  const route = SETTINGS_ROUTES.find((entry) => entry.path === props.path);
  const [state, setState] = useState<string | null>(null);
  const current = useCurrentProject();
  const { locale } = useLocale();
  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      let next: string | null = null;
      try {
        if (props.path === "models") {
          const ids = await listConnectedProviders();
          next = t("settings.index.connectedState", {
            count: String(ids.length),
          });
        } else if (props.path === "localAI") {
          const ids = await listConnectedProviders();
          const catalog = getProviderCatalog();
          const local = catalog
            .filter(
              (preset) => preset.kind === "local" && ids.includes(preset.id),
            )
            .map((preset) => preset.label);
          next = local.length > 0 ? local.join(", ") : null;
        } else if (props.path === "localbench") {
          try {
            const raw = window.localStorage.getItem("agentsi.localbench.scan");
            if (raw !== null) {
              const doc = JSON.parse(raw) as { models?: unknown[] };
              if (Array.isArray(doc.models)) {
                next = t("settings.index.benchModels", {
                  count: String(doc.models.length),
                });
              }
            }
          } catch {
            next = null;
          }
        } else if (props.path === "project") {
          next = current.projectId;
        } else if (props.path === "general") {
          next = t(
            locale === "uk" ? "shell.topbar.langUk" : "shell.topbar.langEn",
          );
        } else if (props.path === "appearance") {
          try {
            const theme = readTheme();
            next = t(
              theme === "dark"
                ? "settings.appearance.dark"
                : "settings.appearance.light",
            );
          } catch {
            next = null;
          }
        }
      } catch {
        next = null;
      }
      if (alive) {
        setState(next);
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [props.path, current.projectId, locale]);
  if (props.path === "diagnostics") {
    return (
      <li className="fx-settings-row">
        <NavLink
          to="/settings/diagnostics"
          data-testid="settings-link-diagnostics"
          className="fx-settings-row-link"
        >
          <span aria-hidden="true" className="fx-settings-row-marker">
            {props.marker}
          </span>
          <span className="fx-settings-row-text">
            <span className="fx-settings-row-title">
              {t("diagnostics.title")}
            </span>
            <span className="fx-settings-row-purpose">
              {state ?? t("diagnostics.purpose")}
            </span>
          </span>
          <span aria-hidden="true" className="fx-settings-row-chevron">
            ›
          </span>
        </NavLink>
      </li>
    );
  }
  if (route === undefined) {
    return (
      <EmptyState stateKey="ui.table.empty" actionKey={null} onAction={null} />
    );
  }
  return (
    <li className="fx-settings-row">
      <NavLink
        to={`/settings/${route.path}`}
        data-testid={`settings-link-${route.path}`}
        end
        className="fx-settings-row-link"
      >
        <span aria-hidden="true" className="fx-settings-row-marker">
          {props.marker}
        </span>
        <span className="fx-settings-row-text">
          <span className="fx-settings-row-title">{t(route.titleKey)}</span>
          <span className="fx-settings-row-purpose">
            {state ?? t(route.purposeKey)}
          </span>
        </span>
        <span aria-hidden="true" className="fx-settings-row-chevron">
          ›
        </span>
      </NavLink>
    </li>
  );
}

// R6 + R9: grouped index (Help group carries How it works, About,
// Migration) — a grouped list, not a link strip.
function SettingsIndexRoute(): ReactElement {
  const markers: Record<string, string> = {
    "models-providers": "▦",
    limits: "◐",
    app: "⚙",
    measure: "▤",
    help: "?",
  };
  return (
    <SettingsLayout
      titleKey="settings.index.title"
      purposeKey="settings.index.purpose"
      needItNowKey="settings.index.needItNow"
    >
      {SETTINGS_GROUPS.map((group) => (
        <section key={group.id} aria-label={t(group.titleKey)}>
          <h3>{t(group.titleKey)}</h3>
          <ul className="fx-settings-rows">
            {group.paths.map((path) => (
              <SettingsRow
                key={path}
                path={path}
                marker={markers[group.id] ?? "•"}
              />
            ))}
          </ul>
        </section>
      ))}
      <section aria-label={t("settings.groups.help")}>
        <h3>{t("settings.groups.help")}</h3>
        <ul className="fx-settings-rows">
          {SETTINGS_HELP_ROWS.map((row) => (
            <li key={row.testId} className="fx-settings-row">
              <Link
                to={row.path}
                data-testid={row.testId}
                className="fx-settings-row-link"
              >
                <span aria-hidden="true" className="fx-settings-row-marker">
                  {markers.help}
                </span>
                <span className="fx-settings-row-text">
                  <span className="fx-settings-row-title">
                    {t(row.titleKey)}
                  </span>
                  <span className="fx-settings-row-purpose">
                    {t(row.purposeKey)}
                  </span>
                </span>
                <span aria-hidden="true" className="fx-settings-row-chevron">
                  ›
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </SettingsLayout>
  );
}

function GeneralSection(): ReactElement {
  const { locale } = useLocale();
  const navigate = useNavigate();
  const [resetNote, setResetNote] = useState(false);
  return (
    <span data-testid="settings-section-body">
      <h3>{t("shell.topbar.language")}</h3>
      <div>
        <button
          type="button"
          data-testid="settings-general-lang-en"
          className="fx-btn-quiet"
          onClick={() => setLocale("en")}
        >
          {t("shell.topbar.langEn")}
        </button>{" "}
        <button
          type="button"
          data-testid="settings-general-lang-uk"
          className="fx-btn-quiet"
          onClick={() => setLocale("uk")}
        >
          {t("shell.topbar.langUk")}
        </button>
        <p data-testid="settings-general-lang-current">
          {locale === "uk"
            ? t("shell.topbar.langUk")
            : t("shell.topbar.langEn")}
        </p>
      </div>
      <h3>{t("settings.general.resetTitle")}</h3>
      <button
        type="button"
        data-testid="settings-general-reset"
        className="fx-btn-quiet"
        onClick={() => {
          clearFirstRunDone();
          setResetNote(true);
          navigate("/firstrun");
        }}
      >
        {t("settings.general.resetSetup")}
      </button>
      {resetNote ? (
        <p role="status">{t("settings.general.resetDone")}</p>
      ) : null}
      <p>{t("settings.general.whereText")}</p>
    </span>
  );
}

function SettingsSectionRoute(): ReactElement {
  const params = useParams();
  const current = useCurrentProject();
  if (params.section === "diagnostics") {
    return (
      <SettingsLayout
        titleKey="diagnostics.title"
        purposeKey="diagnostics.purpose"
      >
        <SettingsTabs />
        <SettingsBackLink />
        <DiagnosticsSection />
      </SettingsLayout>
    );
  }
  // FXAUTO: the automations row lives in the Watcher and automations
  // group, not in SETTINGS_ROUTES, so the ten tab links stay ten.
  const route = SETTINGS_ROUTES.find((entry) => entry.path === params.section) ??
    (params.section === "automations"
      ? {
          path: "automations",
          titleKey: "settings.automations.title",
          purposeKey: "settings.automations.purpose",
          needItNowKey: "settings.automations.needItNow",
        }
      : undefined);
  if (route === undefined) {
    return (
      <EmptyState stateKey="ui.table.empty" actionKey={null} onAction={null} />
    );
  }
  const projectId = current.projectId;
  if (route.path === "automations") {
    return (
      <SettingsLayout
        titleKey={route.titleKey}
        purposeKey={route.purposeKey}
        needItNowKey={route.needItNowKey}
      >
        <SettingsTabs />
        <span data-testid="settings-section-body">
          <AutomationsPage projectId={projectId} />
        </span>
      </SettingsLayout>
    );
  }
  // R6: the need-it-now block shows only on Models and Routing.
  const showNeedItNow = route.path === "models" || route.path === "routing";
  return (
    <SettingsLayout
      titleKey={route.titleKey}
      purposeKey={route.purposeKey}
      needItNowKey={showNeedItNow ? route.needItNowKey : undefined}
      // FXNAV P16-needitnow: the Project page renders purpose plus
      // need-it-now like the other settings pages; the kit probe id
      // rides the section.
      sectionTestId={
        route.path === "project" ? "kit-card-needitnow-project" : undefined
      }
    >
      <SettingsTabs />
      <SettingsBackLink />
      {route.path === "project" ? (
        // FXPOINT1 P1: the role editor stays mounted even with no project
        // selected so its labelled Mode/Role controls always resolve; the
        // server-backed reads fall back to defaults and a save without a
        // project surfaces an error instead of unmounting the section.
        <>
          <RoleProfileEditor projectId={projectId ?? ""} role="manager" />
          {projectId !== null ? (
            <>
              <ContractDefaultsBar projectId={projectId} role="manager" />
              <AcceptedRiskSwitch projectId={projectId} />
              <InstallGrantsList projectId={projectId} />
            </>
          ) : null}
        </>
      ) : route.path === "general" ? (
        <GeneralSection />
      ) : route.path === "appearance" ? (
        <span data-testid="settings-section-body">
          <ThemeToggle />
        </span>
      ) : route.path === "localAI" ? (
        <>
          <LocalConnectSection projectId={projectId ?? "local"} />
          <LocalAiStoredPanel />
        </>
      ) : route.path === "localbench" ? (
        <span data-testid="settings-section-body">
          <LocalBenchTab client={new HttpLocalBenchClient()} />
        </span>
      ) : route.path === "qacatalog" ? (
        <span data-testid="settings-section-body">
          <QaCatalogSection />
        </span>
      ) : route.path === "models" || route.path === "routing" ? (
        <span data-testid="settings-section-body">
          <ProvidersPage
            project_id={projectId ?? "local"}
            mode={route.path === "routing" ? "routing" : "models"}
          />
        </span>
      ) : route.path === "capabilityDB" ? (
        <span data-testid="settings-section-body">
          <KbRefreshProposal />
        </span>
      ) : route.path === "optimization" ? (
        <span data-testid="settings-section-body">
          <OptimizationPolicySection />
          <ProvidersPage project_id={projectId ?? "local"} />
        </span>
      ) : (
        <span data-testid="settings-section-body" />
      )}
    </SettingsLayout>
  );
}

// FXPOINT1 PREFILL: completing the last first-run step seeds the chat
// composer with the first task text. The title is read back from the
// served tasks so the composer shows what the flow just created; a failed
// read still lands in chat with an empty composer.
function FirstRunRoute(props: {
  onSeedPrefill: (title: string) => void;
}): ReactElement {
  const navigate = useNavigate();
  const client = useApiClient();
  const current = useCurrentProject();
  return (
    <FirstRunFlowView
      onComplete={() => {
        // Finishing the wizard completes the first run: the start
        // gate must never send this profile back to /firstrun.
        markFirstRunDone();
        const pid = current.projectId;
        if (pid === null) {
          navigate(ROUTES.chat);
          return;
        }
        void client.listTasks(pid).then(
          (tasks) => {
            const last = tasks[tasks.length - 1];
            if (last !== undefined) {
              props.onSeedPrefill(last.title);
            }
            navigate(ROUTES.chat);
          },
          () => {
            navigate(ROUTES.chat);
          },
        );
      }}
    />
  );
}

function AppShellInner(): ReactElement {
  const current = useCurrentProject();
  const projectId = current.projectId;
  // FXSAVED item 5: arm the close warning while any chat pump streams.
  const livePump = useLivePumpActive();
  const [chatPrefill, setChatPrefill] = useState<string | null>(null);
  const [chatOneShot, setChatOneShot] = useState<{
    projectId: string;
    text: string;
  } | null>(null);
  return (
    <div data-testid="app-shell">
      {/* FXKITUI-FIRSTRUN-BEGIN */}
      <FirstRunGate />
      {/* FXKITUI-FIRSTRUN-END */}
      {/* J11: skip link first in tab order; the composer input carries
          the matching id on every route. */}
      <a data-testid="skip-to-composer" href="#chat-prompt">
        {t("shell.skipToComposer")}
      </a>
      <TopBar projectId={projectId} />
      {/* J11: the centre column sits before either rail in DOM order, so
          keyboard tabbing reads the working area before the rails. The
          grid areas keep the visuals unchanged. */}
      <main data-testid="app-main">
        {/* FXLOOK D5: the guard names the live run, never a bare
            "Close anyway?". */}
        <ClosingGuard armed={livePump} confirmKey="shell.closing.runWorking">
          <Suspense
            fallback={<LoadingState loadingKey="ui.loading.more" />}
          >
            <Routes>
              <Route
                path={ROUTES.chat}
                element={
                  <ChatRoute
                    initialDraft={chatPrefill}
                    oneShot={chatOneShot}
                    onFirstMessage={(nextProjectId, text) => {
                      setChatOneShot({ projectId: nextProjectId, text });
                    }}
                    onOneShotConsumed={() => {
                      setChatOneShot(null);
                    }}
                  />
                }
              />
              <Route path={ROUTES.agentsLive} element={<AgentsRoute />} />
              <Route path="/watcher" element={<WatcherRoute />} />
              <Route path={ROUTES.projects} element={<ProjectsPageView />} />
              <Route
                path={ROUTES.projectOverview}
                element={<ProjectSubview view="overview" />}
              />
              <Route
                path={ROUTES.projectTasks}
                element={<ProjectSubview view="tasks" />}
              />
              <Route
                path={ROUTES.projectRuns}
                element={<ProjectSubview view="runs" />}
              />
              <Route
                path={ROUTES.projectTime}
                element={<ProjectSubview view="time" />}
              />
              <Route
                path={ROUTES.projectAiUsage}
                element={<ProjectSubview view="ai-usage" />}
              />
              <Route
                path={ROUTES.projectTokens}
                element={<ProjectSubview view="tokens" />}
              />
              <Route
                path={ROUTES.projectCost}
                element={<ProjectSubview view="cost" />}
              />
              <Route
                path={ROUTES.projectLocalAi}
                element={<ProjectSubview view="local-ai" />}
              />
              <Route
                path={ROUTES.projectCloudAi}
                element={<ProjectSubview view="cloud-ai" />}
              />
              <Route
                path={ROUTES.projectModels}
                element={<ProjectSubview view="models" />}
              />
              <Route
                path={ROUTES.projectRouting}
                element={<ProjectSubview view="routing-decisions" />}
              />
              <Route
                path={ROUTES.projectAudits}
                element={<ProjectSubview view="audits" />}
              />
              <Route
                path={ROUTES.projectErrors}
                element={<ProjectSubview view="errors" />}
              />
              <Route
                path={ROUTES.projectReports}
                element={<ProjectSubview view="reports" />}
              />
              <Route
                path={TESTS_ROUTE_PATH}
                element={<ProjectSubview view="tests" />}
              />
              <Route path={CHAT_TAB_ROUTE_PATH} element={<ChatTabRoute />} />
              <Route path="/settings" element={<SettingsIndexRoute />} />
              <Route
                path="/settings/:section"
                element={<SettingsSectionRoute />}
              />
              <Route
                path="/firstrun"
                element={<FirstRunRoute onSeedPrefill={setChatPrefill} />}
              />
              <Route path="/about" element={<AboutRoute />} />
              <Route path="/migration" element={<MigrationRoute />} />
              <Route path="/how-it-works" element={<HowItWorksView />} />
              <Route path="/diagnostics/locale-coverage" element={<LocaleCoverage />} />
              <Route path="/diagnostics/telemetry-themes" element={<TelemetryThemes />} />
              <Route path="/diagnostics/bench-check" element={<BenchGatewayCheck />} />
              <Route path="/diagnostics/telemetry" element={<TelemetrySummary />} />
              <Route path="/diagnostics/bench-history" element={<BenchHistoryList />} />
              <Route
                path="*"
                element={<Navigate to={ROUTES.chat} replace />}
              />
            </Routes>
          </Suspense>
        </ClosingGuard>
      </main>
      <Sidebar projectId={projectId} />
      <Inspector
        projectId={projectId}
        // W9: single agents-live source. The route view owns the one
        // AgentsLive instance; the Inspector team card renders its own
        // rows, so the second copy (and its skeleton-vs-empty clash)
        // stays unmounted.
        live={null}
      />
    </div>
  );
}

function AppShell(): ReactElement {
  const current = useCurrentProject();
  // FXPROJ J1: first selection rides the shared list load in the same
  // tick (no extra fetch, no extra render hop). Later loads never
  // reselect: the ref guards the null case at call time.
  // FXSAVED item 3: a stored pick restores as-is (ApiClientProvider
  // inits from the same localStorage); a stored id of a deleted
  // project is a ghost: fall back to rows[0] and rewrite the store
  // through select. No second clear here: FXOPEN owns
  // CurrentProject.clear() (SH-04) and reuses this same key.
  const selectionRef = useRef(current.projectId);
  selectionRef.current = current.projectId;
  const selectFirst = useCallback(
    (rows: ProjectRecord[]) => {
      const first = rows[0];
      if (first === undefined) {
        return;
      }
      const stored = selectionRef.current;
      if (stored === null) {
        current.select(first.project_id);
        return;
      }
      if (!rows.some((row) => row.project_id === stored)) {
        current.select(first.project_id);
      }
    },
    [current],
  );
  // FXPROJ J1: the one shared project list for the whole shell
  // (Sidebar, Projects page, first-message create). It reads the route,
  // so it mounts inside the router, around the shell content.
  return (
    <ProjectListProvider onLoad={selectFirst}>
      <AppShellInner />
    </ProjectListProvider>
  );
}

export function App(): ReactElement {
  const client = useOptionalApiClient();
  const selection = useOptionalCurrentProject();
  const [locale, setLocaleState] = useState<SupportedLocale>(readStoredLocale);
  useEffect(() => {
    function onLocaleEvent(event: Event): void {
      const next = (event as CustomEvent<SupportedLocale>).detail;
      if (next === "en" || next === "uk") {
        setLocaleState(next);
      }
    }
    window.addEventListener(TOPBAR_LOCALE_EVENT, onLocaleEvent);
    return () => {
      window.removeEventListener(TOPBAR_LOCALE_EVENT, onLocaleEvent);
    };
  }, []);
  if (client === null || selection === null) {
    return <p data-testid="app-no-client">{t("errors.generic")}</p>;
  }
  return (
    <LocaleProvider initialLocale={locale}>
      <AppShell />
    </LocaleProvider>
  );
}
