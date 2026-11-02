// Lane A project extended views: overview, tasks, runs, time, AI usage,
// tokens, cost, local AI, cloud AI, models, routing decisions (WHY_THIS_MODEL
// from the stored snapshot), audits, errors and reports. Numbers render only
// from served records; served token or audit telemetry has no route, so those
// views stay honestly empty until one lands. The reports export serializes
// stored telemetry; the reports view renders readable rows from records and
// keeps the raw export behind a collapsed details block; derived narrative
// lines carry the DERIVED label and never
// override measured rows. Mounted by the App routes
// /projects/:projectId/* in wave 3.
// L0C-01: every panel loads and fails independently, so one failing read
// never hides the sibling panels.

import { Component, useEffect, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import type {
  BudgetState,
  LedgerRow,
  PartRow,
  ProjectRecord,
  RoutingWhy,
  TaskRecord,
} from "../api/iface";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { useApiClient } from "../app/ApiClientProvider";
import { formatDate, formatNumber, t, useLocale } from "../locale/index";
import type { SupportedLocale } from "../locale/index";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import { placementKey, resolveStatusHuman } from "../agents/agentsApi";
import { TASKS_CHANGED_EVENT, taskStatusLabel } from "../tasks/TaskComposer";
import {
  buildTokenRows,
  changedFiles,
  dedupeLiveRows,
  formatRunMoment,
  formatServedDate,
  humanDuration,
  humanRunRef,
  isFinishedStatus,
  readRuns,
  readTelemetrySummary,
  runStatusText,
  runWallS,
  sumRunsWall,
  sumTokenRows,
} from "./viewsApi";
import type { DevrunRun, TelemetrySummary } from "./viewsApi";
import "./projectview.css";
import {
  PROJECT_VIEWS,
  buildDerivedSplit,
  computeAgeDays,
  CONTEXT_SOURCE,
  contextUsage,
  exportProjectReport,
  projectMenuTestId,
  projectViewTitleKey,
  readLocalTests,
  remainingBudget,
  saveLocalTests,
  sumLedger,
} from "./projectsApi";
import type { ProjectViewName } from "./projectsApi";
import { RunHistory } from "./RunHistory";
import { TestsTab } from "./TestsTab";
import { ProjectLimitsSection } from "../settings/projectLimits";
import { HealthView } from "./observe/HealthView";
import { MatrixView } from "./observe/MatrixView";
import { VerifierView } from "./observe/VerifierView";
import { AttachControl } from "../kb/AttachControl";

export type { ProjectViewName };
export { PROJECT_VIEWS };

export interface ProjectViewProps {
  projectId: string;
  view: ProjectViewName;
  decisionId?: string;
  onSelect?: (view: ProjectViewName) => void;
}

interface PanelError {
  errorKey: string;
  code: string;
}

function toPanelError(error: unknown): PanelError {
  if (error instanceof ApiError) {
    return { errorKey: apiErrorLocaleKey(error.code), code: error.code };
  }
  return { errorKey: "errors.generic", code: "CONTEXT_MISSING" };
}

function readStatusHuman(row: PartRow): unknown {
  return (row as unknown as Record<string, unknown>).status_human;
}

function Fact(props: {
  testId: string;
  labelKey: string;
  value: string | number;
}): ReactElement {
  return (
    <div data-testid={props.testId} className="fxpv-fact">
      <span className="fxpv-fact-label">{t(props.labelKey)}:</span>
      <span className="fxpv-fact-value">{props.value}</span>
    </div>
  );
}

// One deduped agent row: short human name, served role plus model plus
// tokens, attempt count when repeated, finished wording for passed rows,
// and the served reason note for blocked ends. No scope-kind verdict.
function AgentPlacementRow(props: {
  testId: string;
  agent: string;
  role?: string;
  model?: string;
  tokensTotal: number | null;
  attempts: number;
  status: PartRow["status"];
  statusHuman: unknown;
  placementLabel: string;
}): ReactElement {
  const { locale } = useLocale();
  const short = humanRunRef(props.agent);
  return (
    <div key={props.testId} data-testid={props.testId} className="fxpv-row">
      <span title={short.title}>{short.text}</span>
      <span>{props.role ?? t("shell.common.unknown")}</span>
      <span>{props.model ?? t("shell.common.unknown")}</span>
      <span>
        {props.tokensTotal === null
          ? t("shell.common.unknown")
          : formatNumber(props.tokensTotal, locale)}
      </span>
      {props.attempts > 1 ? (
        <span>{t("projectView.attempts", { count: props.attempts })}</span>
      ) : null}
      <span>
        {isFinishedStatus(props.status)
          ? t("projectView.finished")
          : resolveStatusHuman(props.statusHuman, props.status, locale)}
      </span>
      {props.status === "BLOCKED" ? (
        <span className="fxpv-note">{t("projectView.blockedNote")}</span>
      ) : null}
      <span className="fxpv-note">{props.placementLabel}</span>
    </div>
  );
}

export interface ParsedReportExport {
  format: string;
  project: ProjectRecord;
  ledger: LedgerRow[];
  budget: BudgetState;
}

export function parseReportExport(
  text: string | null,
): ParsedReportExport | null {
  if (text === null || text === "") {
    return null;
  }
  try {
    const data: unknown = JSON.parse(text) as unknown;
    if (typeof data !== "object" || data === null) {
      return null;
    }
    const record = data as Record<string, unknown>;
    if (typeof record.project !== "object" || record.project === null) {
      return null;
    }
    if (!Array.isArray(record.ledger)) {
      return null;
    }
    if (typeof record.budget !== "object" || record.budget === null) {
      return null;
    }
    return data as ParsedReportExport;
  } catch {
    return null;
  }
}

function statusCounts(
  tasks: TaskRecord[],
): Array<{ status: string; count: number }> {
  const counts = new Map<string, number>();
  for (const task of tasks) {
    counts.set(task.status, (counts.get(task.status) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([left], [right]) =>
      left < right ? -1 : left > right ? 1 : 0,
    )
    .map(([status, count]) => ({ status, count }));
}

// One-line task rollup for the overview: "1 done", or the total with a
// per-status split ("2 (1 queued, 1 running)"). Served status text only.
function taskSummary(tasks: TaskRecord[]): string {
  const parts = statusCounts(tasks).map(
    ({ status, count }) => `${count} ${taskStatusLabel(status).toLowerCase()}`,
  );
  if (parts.length === 1) {
    return parts[0] as string;
  }
  if (parts.length === 0) {
    return `${tasks.length}`;
  }
  return `${tasks.length} (${parts.join(", ")})`;
}

function formatTaskDate(createdAt: string, locale: SupportedLocale): string {
  const parsed = Date.parse(createdAt);
  if (Number.isNaN(parsed)) {
    return createdAt;
  }
  return formatDate(new Date(parsed), locale);
}

export function ReportReadable(props: {
  project: ProjectRecord;
  tasks: TaskRecord[];
  budget: BudgetState;
  report: string | null;
}): ReactElement {
  if (parseReportExport(props.report) === null) {
    return (
      <div data-testid="project-report-readable">
        <span>{props.report ?? ""}</span>
      </div>
    );
  }
  return (
    <div data-testid="project-report-readable">
      <div data-testid="report-project-name">
        <span>{t("shell.topbar.project")}</span>
        <span>{props.project.name}</span>
      </div>
      <div data-testid="report-task-counts">
        <span>{t("tasks.list.title")}</span>
        {statusCounts(props.tasks).map(({ status, count }) => (
          <div key={status} data-testid={`report-task-count-${status}`}>
            <span>{taskStatusLabel(status)}</span>
            <span>{count}</span>
          </div>
        ))}
      </div>
      <div data-testid="report-budget-spent">
        <span>{t("telemetry.cost")}</span>
        <span>{`${props.budget.spent} ${props.budget.currency}`}</span>
      </div>
      <div data-testid="report-budget-reserved">
        <span>{t("projects.cost.title")}</span>
        <span>{`${props.budget.reserved} ${props.budget.currency}`}</span>
      </div>
      <div data-testid="report-budget-limit">
        <span>{t("ui.card.total")}</span>
        <span>{`${props.budget.hard_limit} ${props.budget.currency}`}</span>
      </div>
    </div>
  );
}

// R349B: a render throw inside the limits section (missing locale key,
// unexpected row shape) must never unmount the sibling project content, so
// the section always renders behind this boundary. Fetch failures are
// already owned by the section itself (its own loading and error states).
class LimitsSectionBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }
  componentDidCatch(): void {
    return undefined;
  }
  render(): ReactNode {
    if (this.state.failed) {
      return null;
    }
    return <>{this.props.children}</>;
  }
}

// FXTESTSUI: the ONE local-tests switch. Settings area by
// ProjectLimitsSection (overview only, never in the Tests tab). The
// checkbox defaults to the GET answer; toggling POSTs once with the UI
// session token (x-ui-session-token header via kind "write") and reads
// back the served value. Labels are inline English (FXLAYOUT owns locale
// files); only staged keys go through t().
export function LocalTestsSwitch(props: {
  projectId: string;
}): ReactElement {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [failed, setFailed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let alive = true;
    void readLocalTests(props.projectId)
      .then((state) => {
        if (alive) {
          setEnabled(state.enabled);
          setFailed(false);
        }
      })
      .catch(() => {
        if (alive) {
          setEnabled(null);
          setFailed(true);
        }
      });
    return () => {
      alive = false;
    };
  }, [props.projectId, nonce]);

  async function onToggle(): Promise<void> {
    if (enabled === null || saving) {
      return;
    }
    const next = !enabled;
    setSaving(true);
    try {
      await saveLocalTests(props.projectId, next);
      const reread = await readLocalTests(props.projectId);
      setEnabled(reread.enabled);
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  if (enabled === null) {
    return (
      <section data-testid="local-tests-section">
        {failed ? (
          <div data-testid="local-tests-error">
            <span>{t("errors.generic")}</span>
            <button
              type="button"
              data-testid="local-tests-retry"
              onClick={() => {
                setNonce((value) => value + 1);
              }}
            >
              {t("ui.error.retry")}
            </button>
          </div>
        ) : (
          <p>{t("ui.loading.more")}</p>
        )}
      </section>
    );
  }

  return (
    <section data-testid="local-tests-section">
      <p>{t("projects.tests.local.title")}</p>
      <p>{t("projects.tests.local.body")}</p>
      {failed ? (
        <div data-testid="local-tests-error">
          <span>{t("errors.generic")}</span>
          <button
            type="button"
            data-testid="local-tests-retry"
            onClick={() => {
              setNonce((value) => value + 1);
            }}
          >
            {t("ui.error.retry")}
          </button>
        </div>
      ) : null}
      <label htmlFor="local-tests-switch">{t("projects.tests.local.label")}</label>
      <input
        id="local-tests-switch"
        data-testid="local-tests-switch"
        type="checkbox"
        checked={enabled}
        disabled={saving}
        onChange={() => {
          void onToggle();
        }}
      />
      <span data-testid="local-tests-value">{enabled ? t("projects.tests.local.on") : t("projects.tests.local.off")}</span>
    </section>
  );
}

// One plain first-time-user sentence per tab. Inline English: the locale
// tables are owned by another lane, and these sentences are product copy
// mandated for the views rework (same precedent as LocalTestsSwitch).
const VIEW_SENTENCE: Record<ProjectViewName, string | null> = {
  overview: "What this project is and how it is doing.",
  tasks: "Things to do, with their current state.",
  runs: "Every run of this project, and what came out of it.",
  time: "How long the runs took.",
  "ai-usage": "Where the AI work happened.",
  tokens: "Tokens used per role and model; money lives on the Cost tab.",
  cost: "Money spent, reserved and left, against the budget limit.",
  "local-ai": "Work running on this machine.",
  "cloud-ai": "Work running with cloud providers.",
  models: "Which model did each job.",
  "routing-decisions": "Why this model was chosen.",
  audits: "What needs attention.",
  errors: "What went wrong.",
  reports: "Totals and files from the runs.",
  // The tests tab already opens with its own served explainer line.
  tests: null,
};

const RUNS_VIEWS: ReadonlySet<string> = new Set([
  "overview",
  "time",
  "cost",
  "reports",
  "audits",
]);

export function ProjectView(props: ProjectViewProps): ReactElement {
  const client = useApiClient();
  const { locale } = useLocale();
  // L0C-01: one state per served read. No shared Promise.all and no shared
  // failure flag: each panel below renders from its own state and shows its
  // own ErrorPanel, so a single failing read never unmounts the others.
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [projectError, setProjectError] = useState<PanelError | null>(null);
  const [tasks, setTasks] = useState<TaskRecord[] | null>(null);
  const [tasksError, setTasksError] = useState<PanelError | null>(null);
  const [ledger, setLedger] = useState<LedgerRow[] | null>(null);
  const [ledgerError, setLedgerError] = useState<PanelError | null>(null);
  const [budget, setBudget] = useState<BudgetState | null>(null);
  const [budgetError, setBudgetError] = useState<PanelError | null>(null);
  const [live, setLive] = useState<PartRow[] | null>(null);
  const [liveError, setLiveError] = useState<PanelError | null>(null);
  const [runs, setRuns] = useState<DevrunRun[] | null>(null);
  const [why, setWhy] = useState<RoutingWhy | null>(null);
  const [whyError, setWhyError] = useState<PanelError | null>(null);
  const [whyLoading, setWhyLoading] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [reportError, setReportError] = useState<PanelError | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [telemetry, setTelemetry] = useState<TelemetrySummary | null>(null);
  const [nonce, setNonce] = useState(0);

  function retry(): void {
    setNonce((value) => value + 1);
  }

  function panelError(error: PanelError): ReactElement {
    return (
      <ErrorPanel
        errorKey={error.errorKey}
        code={error.code}
        onRetry={retry}
      />
    );
  }

  useEffect(() => {
    let alive = true;
    void client
      .readProject(props.projectId)
      .then((row) => {
        if (alive) {
          setProject(row);
          setProjectError(null);
        }
      })
      .catch((error: unknown) => {
        if (alive) {
          setProject(null);
          setProjectError(toPanelError(error));
        }
      });
    return () => {
      alive = false;
    };
  }, [client, props.projectId, nonce]);

  useEffect(() => {
    let alive = true;
    void client
      .listTasks(props.projectId)
      .then((rows) => {
        if (alive) {
          setTasks(rows);
          setTasksError(null);
        }
      })
      .catch((error: unknown) => {
        if (alive) {
          setTasks(null);
          setTasksError(toPanelError(error));
        }
      });
    return () => {
      alive = false;
    };
  }, [client, props.projectId, nonce]);

  useEffect(() => {
    let alive = true;
    void client
      .readLedger(props.projectId)
      .then((rows) => {
        if (alive) {
          setLedger(rows);
          setLedgerError(null);
        }
      })
      .catch((error: unknown) => {
        if (alive) {
          setLedger(null);
          setLedgerError(toPanelError(error));
        }
      });
    return () => {
      alive = false;
    };
  }, [client, props.projectId, nonce]);

  useEffect(() => {
    let alive = true;
    void client
      .readBudget(props.projectId)
      .then((row) => {
        if (alive) {
          setBudget(row);
          setBudgetError(null);
        }
      })
      .catch((error: unknown) => {
        if (alive) {
          setBudget(null);
          setBudgetError(toPanelError(error));
        }
      });
    return () => {
      alive = false;
    };
  }, [client, props.projectId, nonce]);

  useEffect(() => {
    let alive = true;
    void client
      .listAgentsLive()
      .then((rows) => {
        if (alive) {
          setLive(rows);
          setLiveError(null);
        }
      })
      .catch((error: unknown) => {
        if (alive) {
          setLive(null);
          setLiveError(toPanelError(error));
        }
      });
    return () => {
      alive = false;
    };
  }, [client, nonce]);

  useEffect(() => {
    if (
      (props.view !== "routing-decisions" && props.view !== "models") ||
      props.decisionId === undefined
    ) {
      setWhy(null);
      setWhyError(null);
      setWhyLoading(false);
      return;
    }
    let alive = true;
    setWhyLoading(true);
    void client
      .readRoutingWhy(props.decisionId)
      .then((row) => {
        if (alive) {
          setWhy(row);
          setWhyError(null);
          setWhyLoading(false);
        }
      })
      .catch((error: unknown) => {
        if (alive) {
          setWhy(null);
          setWhyError(toPanelError(error));
          setWhyLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [client, props.view, props.decisionId, nonce]);

  useEffect(() => {
    if (props.view !== "reports") {
      setReport(null);
      setReportError(null);
      setReportLoading(false);
      return;
    }
    let alive = true;
    setReportLoading(true);
    void exportProjectReport(client, props.projectId)
      .then((exported) => {
        if (alive) {
          setReport(exported);
          setReportError(null);
          setReportLoading(false);
        }
      })
      .catch((error: unknown) => {
        if (alive) {
          setReport(null);
          setReportError(toPanelError(error));
          setReportLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [client, props.projectId, props.view, nonce]);

  // FXVIEWS: optional telemetry enrichment for the tokens and audits
  // tabs. A missing doc reads null and the tabs stay honestly empty.
  useEffect(() => {
    if (props.view !== "tokens" && props.view !== "audits") {
      setTelemetry(null);
      return;
    }
    let alive = true;
    void readTelemetrySummary(props.projectId).then((doc) => {
      if (alive) {
        setTelemetry(doc);
      }
    });
    return () => {
      alive = false;
    };
  }, [props.projectId, props.view]);

  useEffect(() => {
    if (props.view !== "tasks") {
      return;
    }
    function onTasksChanged(event: Event): void {
      const detail = (
        event as CustomEvent<{ projectId?: unknown } | null>
      ).detail;
      if (
        detail !== null &&
        typeof detail === "object" &&
        detail.projectId === props.projectId
      ) {
        setNonce((value) => value + 1);
      }
    }
    window.addEventListener(TASKS_CHANGED_EVENT, onTasksChanged);
    return () => {
      window.removeEventListener(TASKS_CHANGED_EVENT, onTasksChanged);
    };
  }, [props.projectId, props.view]);

  // FXVIEWS3: the same ledger route serves devrun run rows under the
  // "runs" key (FXVIEWS2 additions-only); readRuns reads that key. A
  // missing doc reads [] (honestly empty tabs), never an error panel
  // over missing enrichment; the runs tab itself owns load failure.
  useEffect(() => {
    if (!RUNS_VIEWS.has(props.view)) {
      setRuns(null);
      return;
    }
    let alive = true;
    void readRuns(props.projectId).then((rows) => {
      if (alive) {
        setRuns(rows);
      }
    });
    return () => {
      alive = false;
    };
  }, [props.projectId, props.view, nonce]);

  // FXVIEWS V4: run events land as served task rows, so while any task is
  // still open the tasks tab re-reads on a short interval; a finished run
  // stops polling by itself. FXVIEWS2 serves lowercase statuses too.
  const tasksUnfinished =
    tasks !== null &&
    tasks.some(
      (task) =>
        task.status === "QUEUED" ||
        task.status === "RUNNING" ||
        task.status === "CREATED" ||
        task.status === "queued" ||
        task.status === "running" ||
        task.status === "created",
    );
  useEffect(() => {
    if (props.view !== "tasks" || !tasksUnfinished) {
      return;
    }
    const timer = setInterval(() => {
      setNonce((value) => value + 1);
    }, 5000);
    return () => {
      clearInterval(timer);
    };
  }, [props.view, tasksUnfinished]);

  function renderContent(): ReactElement {
    switch (props.view) {
      case "overview": {
        const age =
          project === null ? null : computeAgeDays(project.created_at, Date.now());
        const sums = ledger === null ? null : sumLedger(ledger);
        const runsWall = runs === null ? null : sumRunsWall(runs);
        return (
          <div>
            {projectError !== null ? (
              panelError(projectError)
            ) : project === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <>
                <Fact
                  testId="overview-name"
                  labelKey="shell.topbar.project"
                  value={project.name}
                />
                <Fact
                  testId="overview-created"
                  labelKey="projectView.overview.created"
                  value={formatServedDate(project.created_at, locale)}
                />
                {age === null ? (
                  <Fact
                    testId="overview-age-days"
                    labelKey="projectView.overview.ageDays"
                    value={t("shell.common.unknown")}
                  />
                ) : (
                  <Fact
                    testId="overview-age-days"
                    labelKey="projectView.overview.ageDays"
                    value={age}
                  />
                )}
              </>
            )}
            {tasksError !== null ? (
              panelError(tasksError)
            ) : tasks === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <Fact
                testId="overview-task-count"
                labelKey="tasks.list.title"
                value={taskSummary(tasks)}
              />
            )}
            {ledgerError !== null ? (
              panelError(ledgerError)
            ) : ledger === null || sums === null || runs === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <>
                <Fact
                  testId="overview-package-count"
                  labelKey="projects.runs.title"
                  value={sums.packages + runs.length}
                />
                <Fact
                  testId="overview-agents-total"
                  labelKey="agents.live.title"
                  value={sums.agents}
                />
                <Fact
                  testId="overview-wall-total"
                  labelKey="projects.time.title"
                  value={
                    humanDuration(sums.wall + (runsWall ?? 0)) ??
                    t("shell.common.unknown")
                  }
                />
              </>
            )}
            {budgetError !== null ? (
              panelError(budgetError)
            ) : budget === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <>
                <Fact
                  testId="overview-budget-spent"
                  labelKey="projectView.cost.spent"
                  value={`${budget.spent} ${budget.currency}`}
                />
                <Fact
                  testId="overview-budget-remaining"
                  labelKey="projectView.cost.remaining"
                  value={`${remainingBudget(budget)} ${budget.currency}`}
                />
              </>
            )}
            <LimitsSectionBoundary>
              <ProjectLimitsSection projectId={props.projectId} />
              <LocalTestsSwitch projectId={props.projectId} />
            </LimitsSectionBoundary>
            <AttachControl projectId={props.projectId} />
          </div>
        );
      }
      case "tasks": {
        if (tasksError !== null) {
          return panelError(tasksError);
        }
        if (tasks === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        if (tasks.length === 0) {
          return (
            <EmptyState
              stateKey="tasks.list.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            {tasks.map((task) => (
              <div
                key={task.task_id}
                data-testid={`task-row-${task.task_id}`}
                className="fxpv-task-row"
              >
                <span>{task.title}</span>
                <span className="fxpv-task-chip">
                  {taskStatusLabel(task.status)}
                </span>
                <span>{formatTaskDate(task.created_at, locale)}</span>
              </div>
            ))}
          </div>
        );
      }
      case "runs": {
        return (
          <RunHistory
            projectId={props.projectId}
            packageId={ledger?.[0]?.package_id}
          />
        );
      }
      case "time": {
        if (ledgerError !== null) {
          return panelError(ledgerError);
        }
        if (ledger === null || runs === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        if (ledger.length === 0 && runs.length === 0) {
          return (
            <EmptyState
              stateKey="ui.table.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        const unknown = t("shell.common.unknown");
        return (
          <div>
            <div data-testid="time-runs-count" className="fxpv-row">
              <span>
                {t("projects.runs.title")}: {runs.length}
              </span>
            </div>
            {runs.map((run) => {
              const short = humanRunRef(run.run_id);
              const wall = humanDuration(runWallS(run));
              return (
                <div
                  key={run.run_id}
                  data-testid={`time-run-${run.run_id}`}
                  className="fxpv-row"
                >
                  <span>{t("projectView.time.package")}</span>
                  <span title={short.title}>{short.text}</span>
                  <span>{formatRunMoment(run.start, locale)}</span>
                  <span>{formatRunMoment(run.end, locale)}</span>
                  <span>{wall ?? unknown}</span>
                </div>
              );
            })}
            {ledger.map((row) => {
              const short = humanRunRef(row.package_id);
              return (
                <div
                  key={row.package_id}
                  data-testid={`time-row-${row.package_id}`}
                  className="fxpv-row"
                >
                  <span>{t("projectView.time.package")}</span>
                  <span title={short.title}>{short.text}</span>
                  <span>{humanDuration(row.wall_time_s)}</span>
                </div>
              );
            })}
            <Fact
              testId="time-wall-total"
              labelKey="projects.time.title"
              value={
                humanDuration(sumLedger(ledger).wall) ??
                t("shell.common.unknown")
              }
            />
          </div>
        );
      }
      case "ai-usage": {
        const sums = ledger === null ? null : sumLedger(ledger);
        // XOR: an empty ledger reads as one empty state, never zero rows
        // plus another empty state; an empty live list reads as a note.
        if (ledgerError === null && sums !== null && ledger?.length === 0) {
          return (
            <div>
              <EmptyState
                stateKey="ui.table.empty"
                actionKey={null}
                onAction={null}
              />
            </div>
          );
        }
        return (
          <div>
            {ledgerError !== null ? (
              panelError(ledgerError)
            ) : sums === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <>
                <Fact
                  testId="usage-agents-total"
                  labelKey="agents.live.title"
                  value={sums.agents}
                />
                <Fact
                  testId="usage-peak-max"
                  labelKey="ui.card.total"
                  value={sums.peak}
                />
                <Fact
                  testId="usage-wall-total"
                  labelKey="projects.time.title"
                  value={sums.wall}
                />
              </>
            )}
            {liveError !== null ? (
              panelError(liveError)
            ) : live === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : live.length === 0 ? (
              <span className="fxpv-note">{t("projectView.noLive")}</span>
            ) : (
              <MatrixView rows={live} />
            )}
          </div>
        );
      }
      // FXVIEWS V2: the tokens tab reads served token cells only (live
      // rows plus the analytics telemetry doc): one row per role plus
      // model with its token count, never money. Missing cells read
      // UNKNOWN; an unknown project still errors like every tab.
      case "tokens": {
        if (projectError !== null) {
          return panelError(projectError);
        }
        if (project === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        if (liveError !== null) {
          return panelError(liveError);
        }
        if (live === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        const rows = buildTokenRows(live, telemetry);
        const total = sumTokenRows(rows);
        // Any unknown cell poisons the total: a sum over partial cells
        // would read as measured. "Other calls" names the role-less row.
        const hasUnknown = rows.some((row) => row.tokens === null);
        const unknown = t("shell.common.unknown");
        if (rows.length === 0) {
          return (
            <div>
              <EmptyState
                stateKey="ui.table.empty"
                actionKey={null}
                onAction={null}
              />
            </div>
          );
        }
        return (
          <div>
            <Fact
              testId="tokens-spent"
              labelKey="projectView.tokens.used"
              value={
                total === null || hasUnknown
                  ? "not known yet"
                  : formatNumber(total, locale)
              }
            />
            {rows.map((row, index) => (
                <div
                  key={`${row.role ?? ""}-${row.model ?? ""}-${index}`}
                  data-testid={`tokens-row-${index}`}
                  className="fxpv-row"
                >
                  <span>{row.role ?? "Other calls"}</span>
                  <span>{row.model ?? unknown}</span>
                  <span>
                    {row.tokens === null
                      ? unknown
                      : formatNumber(row.tokens, locale)}
                  </span>
                  {row.calls === null ? null : (
                    <span>
                      {t("projectView.tokens.calls")}: {row.calls}
                    </span>
                  )}
                </div>
              ))}
          </div>
        );
      }
      case "cost": {
        const usage = budget === null ? null : contextUsage(budget);
        return (
          <div>
            {budgetError !== null ? (
              panelError(budgetError)
            ) : budget === null || usage === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <>
                <div data-testid="context-card">
                  <span>{t("projects.tokens.title")}</span>
                  <span data-testid="context-remaining">{usage.remaining}</span>
                  <span data-testid="context-total">{usage.total}</span>
                  <span data-testid="context-source">{CONTEXT_SOURCE}</span>
                </div>
                <Fact
                  testId="cost-spent"
                  labelKey="projectView.cost.spent"
                  value={`${budget.spent} ${budget.currency}`}
                />
                <Fact
                  testId="cost-reserved"
                  labelKey="projectView.cost.reserved"
                  value={`${budget.reserved} ${budget.currency}`}
                />
                <Fact
                  testId="cost-limit"
                  labelKey="projectView.cost.limit"
                  value={`${budget.hard_limit} ${budget.currency}`}
                />
                <Fact
                  testId="cost-remaining"
                  labelKey="projectView.cost.remaining"
                  value={`${remainingBudget(budget)} ${budget.currency}`}
                />
                <p data-testid="cost-limit-explainer" className="fxpv-note">
                  {t("projectView.cost.limitExplainer")}
                </p>
              </>
            )}
            {budgetError !== null ? (
              panelError(budgetError)
            ) : ledgerError !== null ? (
              panelError(ledgerError)
            ) : budget === null || ledger === null || runs === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : ledger.length === 0 && runs.length === 0 ? (
              <span className="fxpv-note">{t("projectView.noLedger")}</span>
            ) : (
              <HealthView ledger={ledger} budget={budget} />
            )}
            {runs === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <div data-testid="health-runs-count" className="fxpv-row">
                <span>
                  {t("projects.runs.title")}: {runs.length}
                </span>
              </div>
            )}
          </div>
        );
      }
      // FXVIEWS V5: one row per agent plus role plus model with served
      // tokens; repeated attempts fold into one row with a count; passed
      // rows say finished; blocked ends carry the served reason note.
      case "local-ai":
      case "cloud-ai": {
        if (liveError !== null) {
          return panelError(liveError);
        }
        if (live === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        const wanted = props.view === "local-ai" ? "LOCAL" : "CLOUD";
        const rows = dedupeLiveRows(live).filter(
          (row) => row.placement === wanted,
        );
        if (rows.length === 0) {
          return (
            <EmptyState
              stateKey="agents.live.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        const agentCounts = new Map<string, number>();
        for (const row of rows) {
          agentCounts.set(row.agent, (agentCounts.get(row.agent) ?? 0) + 1);
        }
        return (
          <div>
            {rows.map((row, index) => (
              <AgentPlacementRow
                key={`${row.agent}-${row.status}-${row.role ?? ""}-${row.model ?? ""}`}
                testId={
                  (agentCounts.get(row.agent) ?? 0) > 1
                    ? `place-row-${row.agent}-${index}`
                    : `place-row-${row.agent}`
                }
                agent={row.agent}
                role={row.role}
                model={row.model}
                tokensTotal={row.tokensTotal}
                attempts={row.attempts}
                status={row.status}
                statusHuman={readStatusHuman(
                  live.find(
                    (candidate) =>
                      candidate.agent === row.agent &&
                      candidate.status === row.status,
                  ) ?? live[0],
                )}
                placementLabel={t(placementKey(wanted))}
              />
            ))}
          </div>
        );
      }
      // FXVIEWS: decision replay rows plus the served live rows (role
      // plus model plus tokens); either side alone is enough for content.
      case "models": {
        if (whyError !== null) {
          return panelError(whyError);
        }
        if (whyLoading) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        if (live === null && liveError === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        const liveModels =
          live === null
            ? []
            : dedupeLiveRows(live).filter(
                (row) => row.role !== undefined || row.model !== undefined,
              );
        if (why === null && liveModels.length === 0) {
          return (
            <EmptyState
              stateKey="ui.table.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        const unknown = t("shell.common.unknown");
        return (
          <div>
            {why === null ? null : (
              <div>
                {why.assignments.map((assignment, index) => (
                  <div key={index} data-testid={`model-row-${index}`}>
                    <span>
                      {assignment.provider_id}/{assignment.model}{" "}
                      {assignment.role}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {liveModels.length === 0 ? null : (
              <div>
                <p data-testid="models-live-title">
                  {t("projectView.models.liveTitle")}
                </p>
                {liveModels.map((row, index) => (
                  <div
                    key={`${row.agent}-${row.role ?? ""}-${row.model ?? ""}-${index}`}
                    data-testid={`model-live-${index}`}
                    className="fxpv-row"
                  >
                    <span>{row.role ?? unknown}</span>
                    <span>{row.model ?? unknown}</span>
                    <span>
                      {row.tokensTotal === null
                        ? unknown
                        : formatNumber(row.tokensTotal, locale)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      }
      case "routing-decisions": {
        if (whyError !== null) {
          return panelError(whyError);
        }
        if (whyLoading) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        if (why === null) {
          return (
            <EmptyState
              stateKey="ui.table.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            <div data-testid="why-this-model">
              <span>{t("projects.why_this_model.title")}</span>
              <span data-testid="why-this-model-reason">
                {why.reason.fit_basis}
              </span>
              <span>{why.reason.task_class}</span>
              <span>{why.reason.price_basis}</span>
              <span>{why.reason.quality_basis}</span>
              {why.reason.rejected.map((name) => (
                <span key={name}>{name}</span>
              ))}
            </div>
            <div data-testid="why-version">
              <span>{t("projects.routing.title")}</span>
              <span>{why.decision.policy_ref}</span>
            </div>
            <div data-testid="why-candidates">
              <span>{t("projects.models.title")}</span>
              {why.assignments.length === 0 ? (
                <EmptyState
                  stateKey="ui.table.empty"
                  actionKey={null}
                  onAction={null}
                />
              ) : (
                why.assignments.map((assignment, index) => (
                  <div key={index} data-testid={`why-candidate-${index}`}>
                    <span>
                      {assignment.provider_id}/{assignment.model}{" "}
                      {assignment.role}
                    </span>
                  </div>
                ))
              )}
            </div>
            <div data-testid="why-provenance">
              <span>{humanRunRef(why.snapshot.snapshot_ref).text}</span>
              <span>
                {formatServedDate(why.snapshot.captured_at, locale)}
              </span>
            </div>
            <div data-testid="why-this-model-decision">
              <span>{why.decision.decision_id}</span>
              <span>{why.decision.policy_ref}</span>
              <span>{why.snapshot.snapshot_ref}</span>
            </div>
            <VerifierView why={why} />
          </div>
        );
      }
      // FXVIEWS V4: the audits tab reads the served analytics counts plus
      // every served row that needs attention (blocked or rejected live
      // rows, blocked or rejected tasks). Nothing served reads as the
      // honest empty state, never invented zeros.
      case "audits": {
        if (tasksError !== null) {
          return panelError(tasksError);
        }
        if (liveError !== null) {
          return panelError(liveError);
        }
        if (tasks === null || live === null || runs === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        const attention = dedupeLiveRows(live).filter(
          (row) => row.status === "BLOCKED" || row.status === "REJECTED",
        );
        const attentionTasks = tasks.filter(
          (task) => task.status === "BLOCKED" || task.status === "REJECTED",
        );
        const counts = telemetry?.project;
        const runParts = runs.flatMap((run) =>
          run.parts.map((part) => ({ run, part })),
        );
        if (
          counts === undefined &&
          attention.length === 0 &&
          attentionTasks.length === 0 &&
          runParts.length === 0
        ) {
          return (
            <EmptyState
              stateKey="ui.table.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        const unknown = t("shell.common.unknown");
        return (
          <div>
            {counts === undefined ? null : (
              <div data-testid="audits-project-counts" className="fxpv-row">
                <span>{t("projectView.audits.projectTasks")}</span>
                <span>{counts.tasks ?? unknown}</span>
                <span>{t("projectView.audits.projectAudits")}</span>
                <span>{counts.audits ?? unknown}</span>
              </div>
            )}
            {runParts.length === 0 ? null : (
              <div>
                <p data-testid="audits-run-verdicts">
                  {t("projects.runs.title")}
                </p>
                {runParts.map(({ run, part }) => (
                  <div
                    key={`${run.run_id}-${part.part_id}`}
                    data-testid={`audit-part-${run.run_id}-${part.part_id}`}
                    className="fxpv-row"
                  >
                    <span>{humanRunRef(run.run_id).text}</span>
                    <span>{part.part_id}</span>
                    <span>{part.verdict ?? unknown}</span>
                    <span>{runStatusText(run)}</span>
                    {part.reason === undefined || part.reason === "" ? null : (
                      <span>{part.reason}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            {attention.length === 0 && attentionTasks.length === 0 ? null : (
              <div>
                <p data-testid="audits-attention">
                  {t("projectView.audits.attention")}
                </p>
                {attention.map((row, index) => (
                  <div
                    key={`${row.agent}-${row.status}-${index}`}
                    data-testid={`audit-row-${index}`}
                    className="fxpv-row"
                  >
                    <span>{humanRunRef(row.agent).text}</span>
                    <span>
                      {resolveStatusHuman(
                        readStatusHuman(
                          live.find(
                            (candidate) =>
                              candidate.agent === row.agent &&
                              candidate.status === row.status,
                          ) ?? live[0],
                        ),
                        row.status,
                        locale,
                      )}
                    </span>
                  </div>
                ))}
                {attentionTasks.map((task) => (
                  <div
                    key={task.task_id}
                    data-testid={`audit-task-${task.task_id}`}
                    className="fxpv-row"
                  >
                    <span>{task.title}</span>
                    <span>{taskStatusLabel(task.status)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      }
      // FXVIEWS: served failure rows only (blocked live rows, blocked or
      // rejected tasks). No served failure reads as the honest empty
      // state; an unknown project still errors.
      case "errors": {
        if (projectError !== null) {
          return panelError(projectError);
        }
        if (project === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        if (tasksError !== null) {
          return panelError(tasksError);
        }
        if (liveError !== null) {
          return panelError(liveError);
        }
        if (tasks === null || live === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        const blocked = dedupeLiveRows(live).filter(
          (row) => row.status === "BLOCKED",
        );
        const failedTasks = tasks.filter(
          (task) => task.status === "BLOCKED" || task.status === "REJECTED",
        );
        if (blocked.length === 0 && failedTasks.length === 0) {
          return (
            <EmptyState
              stateKey="ui.table.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            {blocked.map((row, index) => (
              <div
                key={`${row.agent}-${index}`}
                data-testid={`error-blocked-${index}`}
                className="fxpv-row"
              >
                <span>{t("projectView.errors.blockedAgents")}</span>
                <span>{humanRunRef(row.agent).text}</span>
                <span className="fxpv-note">
                  {t("projectView.blockedNote")}
                </span>
              </div>
            ))}
            {failedTasks.map((task) => (
              <div
                key={task.task_id}
                data-testid={`error-task-${task.task_id}`}
                className="fxpv-row"
              >
                <span>{t("projectView.errors.failedTasks")}</span>
                <span>{task.title}</span>
                <span>{taskStatusLabel(task.status)}</span>
              </div>
            ))}
          </div>
        );
      }
      case "reports": {
        return (
          <div>
            <p data-testid="project-reports-subtitle">{t("projects.reports.subtitle")}</p>
            <div data-testid="project-report-readable">
              {projectError !== null ? (
                panelError(projectError)
              ) : project === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : (
                <div data-testid="report-project-name">
                  <span>{t("shell.topbar.project")}:</span>
                  <span>{project.name}</span>
                </div>
              )}
              {tasksError !== null ? (
                panelError(tasksError)
              ) : tasks === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : (
                <div data-testid="report-task-counts">
                  <span>{t("tasks.list.title")}:</span>
                  {tasks.length === 0 ? (
                    <span>0</span>
                  ) : (
                    statusCounts(tasks).map(({ status, count }) => (
                      <div key={status} data-testid={`report-task-count-${status}`}>
                        <span>{taskStatusLabel(status)}</span>
                        <span>{count}</span>
                      </div>
                    ))
                  )}
                </div>
              )}
              {budgetError !== null ? (
                panelError(budgetError)
              ) : budget === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : (
                <>
                  <div data-testid="report-budget-spent">
                    <span>{t("projectView.cost.spent")}:</span>
                    <span>{`${budget.spent} ${budget.currency}`}</span>
                  </div>
                  <div data-testid="report-budget-reserved">
                    <span>{t("projectView.cost.reserved")}:</span>
                    <span>{`${budget.reserved} ${budget.currency}`}</span>
                  </div>
                  <div data-testid="report-budget-limit">
                    <span>{t("projectView.cost.limit")}:</span>
                    <span>{`${budget.hard_limit} ${budget.currency}`}</span>
                  </div>
                </>
              )}
            </div>
            {reportError !== null ? (
              panelError(reportError)
            ) : reportLoading || report === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <details data-testid="project-report-raw">
                <summary>{t("ui.disclosure.more")}</summary>
                <pre data-testid="project-report-export">{report ?? ""}</pre>
              </details>
            )}
            <div data-testid="project-report-derived">
              {tasksError !== null ? (
                panelError(tasksError)
              ) : ledgerError !== null ? (
                panelError(ledgerError)
              ) : budgetError !== null ? (
                panelError(budgetError)
              ) : tasks === null || ledger === null || budget === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : (
                <>
                  <span>{t("projects.derived.label")}:</span>
                  {(
                    [
                      ["projectView.reports.packages", formatNumber(sumLedger(ledger).packages, locale)],
                      ["projectView.reports.tasks", formatNumber(tasks.length, locale)],
                      ["projectView.reports.agents", formatNumber(sumLedger(ledger).agents, locale)],
                      ["projectView.reports.peak", formatNumber(sumLedger(ledger).peak, locale)],
                      ["projectView.reports.wall", formatNumber(sumLedger(ledger).wall, locale)],
                      ["projectView.reports.spent", `${formatNumber(budget.spent, locale)} ${budget.currency}`],
                      ["projectView.reports.reserved", `${formatNumber(budget.reserved, locale)} ${budget.currency}`],
                      [
                        "projectView.reports.remaining",
                        `${formatNumber(remainingBudget(budget), locale)} ${budget.currency}`,
                      ],
                    ] as Array<[string, string]>
                  ).map(([labelKey, value]) => (
                    <div key={labelKey} className="fxpv-row">
                      <span>{t(labelKey)}:</span>
                      <span>{value}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
            <div data-testid="project-report-derived-split">
              {tasksError !== null ? (
                panelError(tasksError)
              ) : ledgerError !== null ? (
                panelError(ledgerError)
              ) : budgetError !== null ? (
                panelError(budgetError)
              ) : ledger === null || budget === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : buildDerivedSplit({ ledger, budget }).length === 0 ? null : (
                buildDerivedSplit({ ledger, budget }).map((allocation) => (
                  <div
                    key={allocation.packageId}
                    data-testid={`derived-split-${allocation.packageId}`}
                    className="fxpv-row"
                  >
                    <span>{t(allocation.labelKey)}</span>
                    <span>{humanRunRef(allocation.packageId).text}</span>
                    <span>
                      {formatNumber(allocation.derivedCost, locale)}{" "}
                      {allocation.currency}
                    </span>
                  </div>
                ))
              )}
            </div>
            <div data-testid="project-report-files">
              <span>{t("projectView.reports.changedFiles")}</span>
              {liveError !== null ? (
                panelError(liveError)
              ) : live === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : changedFiles(live).length === 0 ? (
                <span className="fxpv-note">
                  {t("projectView.reports.noFiles")}
                </span>
              ) : (
                changedFiles(live).map((file) => (
                  <div
                    key={file}
                    data-testid="report-file-row"
                    className="fxpv-row"
                  >
                    <span title={file}>{humanRunRef(file).text}</span>
                  </div>
                ))
              )}
            </div>
            <div data-testid="project-report-runs">
              <span>{t("projects.runs.title")}</span>
              {runs === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : runs.length === 0 ? (
                <EmptyState
                  stateKey="ui.table.empty"
                  actionKey={null}
                  onAction={null}
                />
              ) : (
                runs.map((run) => (
                  <div
                    key={run.run_id}
                    data-testid={`report-run-${run.run_id}`}
                    className="fxpv-row"
                  >
                    <span title={run.run_id}>
                      {humanRunRef(run.run_id).text}
                    </span>
                    <span>{runStatusText(run)}</span>
                    <span>{run.summary}</span>
                    {run.files.map((file) => (
                      <span
                        key={file}
                        data-testid="report-run-file-row"
                        title={file}
                      >
                        {humanRunRef(file).text}
                      </span>
                    ))}
                  </div>
                ))
              )}
            </div>
          </div>
        );
      }
      case "tests": {
        return <TestsTab projectId={props.projectId} />;
      }
    }
  }

  return (
    <div>
      <nav aria-label={t("projectView.tabsLabel")} className="fxpv-tabs">
        {PROJECT_VIEWS.map((name) => (
          <button
            key={name}
            type="button"
            data-testid={projectMenuTestId(name)}
            aria-current={props.view === name ? "true" : undefined}
            className={
              props.view === name ? "fxpv-tab fxpv-tab-selected" : "fxpv-tab"
            }
            onClick={() => {
              props.onSelect?.(name);
            }}
            onKeyDown={(event) => {
              // W6: keyboard tabs navigate like clicks (App onSelect).
              if (event.key === "Enter") {
                props.onSelect?.(name);
              }
            }}
          >
            {t(projectViewTitleKey(name))}
          </button>
        ))}
      </nav>
      {VIEW_SENTENCE[props.view] === null ? null : (
        <p data-testid="tab-purpose">{VIEW_SENTENCE[props.view]}</p>
      )}
      <section
        data-testid={`kit-card-project-${props.view}`}
        aria-label={t(projectViewTitleKey(props.view))}
        className="fxpv-tabpanel"
      >
        <h2>{t(projectViewTitleKey(props.view))}</h2>
        {renderContent()}
      </section>
    </div>
  );
}
