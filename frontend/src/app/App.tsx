// Lane A app composition root: route table per frontend/src/app/iface.ts,
// chat-first layout with top bar, short navigation, compact inspector and
// unsaved-edit guard. Every route mounts the real wave-1/wave-2 page with
// record data from the shared ApiClient entry; page chunks load lazily so
// the first paint stays chat-first. Production entry:
// frontend/src/app/main.tsx.

import { Suspense, lazy, useEffect, useState } from "react";
import type { ReactElement } from "react";
import {
  Link,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import type { RouteTable } from "./iface";
import type { ApiClient } from "../api/iface";
import { ENDPOINTS } from "../api/endpoints";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import {
  useApiClient,
  useCurrentProject,
} from "./ApiClientProvider";
import type { CurrentProject } from "./ApiClientProvider";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  LocaleProvider,
  t,
} from "../locale/index";
import type { SupportedLocale } from "../locale/index";
import { SETTINGS_ROUTES, AcceptedRiskSwitch, RoleProfileEditor } from "../settings/index";
import { ProvidersPage } from "../settings/ProvidersPage";
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
import { Inspector } from "../shell/Inspector";
import { ClosingGuard } from "../shell/ClosingGuard";
import type { ProjectViewName } from "../projects/ProjectView";

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
      <p data-testid="localai-endpoint-label">{t("settings.localAi.title")}</p>
      <p data-testid="localai-endpoint">{ENDPOINTS.agentsLive}</p>
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

function useEnsureProjectSelection(): void {
  const client = useApiClient();
  const current = useCurrentProject();
  useEffect(() => {
    if (current.projectId !== null) {
      return;
    }
    let alive = true;
    client.listProjects().then(
      (rows) => {
        if (!alive) {
          return;
        }
        const first = rows[0];
        if (first !== undefined) {
          current.select(first.project_id);
        }
      },
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [client, current]);
}

// Chat-first start box for the no-project case (kit PRODUCT_SPEC:4154):
// the / route always mounts a working message box; the first sent message
// creates the first project and starts a task in it, then selects it so the
// route continues in the regular chat surface. Reuses the chat composer
// testids so the route stays chat-first before any project exists.
function ChatStartBox(): ReactElement {
  const client = useApiClient();
  const current = useCurrentProject();
  const [draft, setDraft] = useState("");
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
      await client.createTask(project.project_id, {
        title: message,
        scope: [],
      });
      setDraft("");
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
      <div data-testid="chat-composer">
        <input
          data-testid="chat-prompt"
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

function ChatRoute(): ReactElement {
  const current = useCurrentProject();
  if (current.projectId === null) {
    return <ChatStartBox />;
  }
  return <ChatAreaView projectId={current.projectId} />;
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

function TasksRoute(props: { projectId: string }): ReactElement {
  const [search] = useSearchParams();
  const initialTaskId = search.get("initialTask");
  return (
    <>
      <ProjectViewPage projectId={props.projectId} view="tasks" />
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
  return (
    <>
      <ProjectViewPage
        projectId={props.projectId}
        view="models"
        decisionId={decisionId}
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
  return (
    <>
      <ProjectViewPage projectId={props.projectId} view="local-ai" />
      <LocalAiStoredPanel />
    </>
  );
}

function ProjectSubview(props: { view: ProjectViewName }): ReactElement {
  const params = useParams();
  const [search] = useSearchParams();
  const projectId = params.projectId;
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
    />
  );
}

function SettingsIndexRoute(): ReactElement {
  const general = SETTINGS_ROUTES[0];
  if (general === undefined) {
    return (
      <EmptyState stateKey="ui.table.empty" actionKey={null} onAction={null} />
    );
  }
  return (
    <SettingsLayout
      titleKey={general.titleKey}
      purposeKey={general.purposeKey}
      needItNowKey={general.needItNowKey}
    >
      <nav>
        {SETTINGS_ROUTES.map((route) => (
          <Link
            key={route.path}
            to={`/settings/${route.path}`}
            data-testid={`settings-link-${route.path}`}
          >
            {t(route.titleKey)}
          </Link>
        ))}
      </nav>
    </SettingsLayout>
  );
}

function SettingsSectionRoute(): ReactElement {
  const params = useParams();
  const current = useCurrentProject();
  const route = SETTINGS_ROUTES.find((entry) => entry.path === params.section);
  if (route === undefined) {
    return (
      <EmptyState stateKey="ui.table.empty" actionKey={null} onAction={null} />
    );
  }
  const projectId = current.projectId;
  return (
    <SettingsLayout
      titleKey={route.titleKey}
      purposeKey={route.purposeKey}
      needItNowKey={route.needItNowKey}
    >
      {route.path === "project" && projectId !== null ? (
        <>
          <RoleProfileEditor projectId={projectId} role="manager" />
          <AcceptedRiskSwitch projectId={projectId} />
        </>
      ) : route.path === "localAI" ? (
        <LocalAiStoredPanel />
      ) : route.path === "localbench" ? (
        <span data-testid="settings-section-body">
          <LocalBenchTab client={new HttpLocalBenchClient()} />
        </span>
      ) : route.path === "models" ||
        route.path === "routing" ||
        route.path === "optimization" ||
        route.path === "capabilityDB" ? (
        <span data-testid="settings-section-body">
          <ProvidersPage project_id={projectId ?? "local"} />
        </span>
      ) : (
        <span data-testid="settings-section-body" />
      )}
    </SettingsLayout>
  );
}

function FirstRunRoute(): ReactElement {
  const navigate = useNavigate();
  return (
    <FirstRunFlowView
      onComplete={() => {
        navigate(ROUTES.chat);
      }}
    />
  );
}

function AppShell(): ReactElement {
  const current = useCurrentProject();
  const projectId = current.projectId;
  useEnsureProjectSelection();
  return (
    <div data-testid="app-shell">
      <TopBar projectId={projectId} />
      <Sidebar projectId={projectId} />
      <main data-testid="app-main">
        <ClosingGuard armed={false} confirmKey="shell.closing.confirm">
          <Suspense
            fallback={<LoadingState loadingKey="ui.loading.more" />}
          >
            <Routes>
              <Route path={ROUTES.chat} element={<ChatRoute />} />
              <Route path={ROUTES.agentsLive} element={<AgentsRoute />} />
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
              <Route path="/settings" element={<SettingsIndexRoute />} />
              <Route
                path="/settings/:section"
                element={<SettingsSectionRoute />}
              />
              <Route path="/firstrun" element={<FirstRunRoute />} />
              <Route path="/about" element={<AboutView />} />
              <Route path="/migration" element={<MigrationRoute />} />
              <Route path="/how-it-works" element={<HowItWorksView />} />
              <Route
                path="*"
                element={<Navigate to={ROUTES.chat} replace />}
              />
            </Routes>
          </Suspense>
        </ClosingGuard>
      </main>
      <Inspector
        projectId={projectId}
        live={
          projectId === null ? (
            <EmptyState
              stateKey="agents.live.empty"
              actionKey={null}
              onAction={null}
            />
          ) : (
            <AgentsLiveView projectId={projectId} />
          )
        }
      />
    </div>
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
