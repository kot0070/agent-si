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
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";
import { placementKey, resolveStatusHuman } from "../agents/agentsApi";
import { TASKS_CHANGED_EVENT, taskStatusLabel } from "../tasks/TaskComposer";
import {
  PROJECT_VIEWS,
  buildDerivedSplit,
  buildReportNarrative,
  computeAgeDays,
  CONTEXT_SOURCE,
  contextUsage,
  exportProjectReport,
  projectMenuTestId,
  projectViewTitleKey,
  readLocalTests,
  remainingBudget,
  saveLocalTests,
  splitRowsByPlacement,
  sumLedger,
} from "./projectsApi";
import type { ProjectViewName } from "./projectsApi";
import { RunHistory } from "./RunHistory";
import { TestsTab } from "./TestsTab";
import { ProjectLimitsSection } from "../settings/projectLimits";
import { HealthView } from "./observe/HealthView";
import { MatrixView } from "./observe/MatrixView";
import { VerifierView } from "./observe/VerifierView";
import { classifyScope } from "./scope";
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
    <div data-testid={props.testId}>
      <span>{t(props.labelKey)}</span>
      <span>{props.value}</span>
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
      <h2>Local tests</h2>
      <p>Catalog checks this machine runs before spend. One switch only.</p>
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
      <label htmlFor="local-tests-switch">Local tests</label>
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
      <span data-testid="local-tests-value">{enabled ? "on" : "off"}</span>
    </section>
  );
}

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
  const [why, setWhy] = useState<RoutingWhy | null>(null);
  const [whyError, setWhyError] = useState<PanelError | null>(null);
  const [whyLoading, setWhyLoading] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [reportError, setReportError] = useState<PanelError | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [nonce, setNonce] = useState(0);
  const [collapsed, setCollapsed] = useState(false);

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

  function renderContent(): ReactElement {
    switch (props.view) {
      case "overview": {
        const age =
          project === null ? null : computeAgeDays(project.created_at, Date.now());
        const sums = ledger === null ? null : sumLedger(ledger);
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
                  labelKey="chat.stream.timestamp"
                  value={project.created_at}
                />
                {age === null ? (
                  <EmptyState
                    stateKey="ui.table.empty"
                    actionKey={null}
                    onAction={null}
                  />
                ) : (
                  <Fact
                    testId="overview-age-days"
                    labelKey="projects.time.title"
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
                value={tasks.length}
              />
            )}
            {ledgerError !== null ? (
              panelError(ledgerError)
            ) : ledger === null || sums === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <>
                <Fact
                  testId="overview-package-count"
                  labelKey="projects.runs.title"
                  value={sums.packages}
                />
                <Fact
                  testId="overview-agents-total"
                  labelKey="agents.live.title"
                  value={sums.agents}
                />
                <Fact
                  testId="overview-peak-max"
                  labelKey="ui.card.total"
                  value={sums.peak}
                />
                <Fact
                  testId="overview-wall-total"
                  labelKey="projects.time.title"
                  value={sums.wall}
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
                  labelKey="telemetry.cost"
                  value={budget.spent}
                />
                <Fact
                  testId="overview-budget-remaining"
                  labelKey="projects.derived.label"
                  value={remainingBudget(budget)}
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
              <div key={task.task_id} data-testid={`task-row-${task.task_id}`}>
                <span>{task.title}</span>
                <span>{taskStatusLabel(task.status)}</span>
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
        if (ledger === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        if (ledger.length === 0) {
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
            {ledger.map((row) => (
              <div key={row.package_id} data-testid={`time-row-${row.package_id}`}>
                <span>{row.package_id}</span>
                <span>{row.wall_time_s}</span>
              </div>
            ))}
            <Fact
              testId="time-wall-total"
              labelKey="projects.time.title"
              value={sumLedger(ledger).wall}
            />
          </div>
        );
      }
      case "ai-usage": {
        const sums = ledger === null ? null : sumLedger(ledger);
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
            ) : (
              <MatrixView rows={live} />
            )}
          </div>
        );
      }
      case "tokens": {
        if (budgetError !== null) {
          return panelError(budgetError);
        }
        if (budget === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        return (
          <div>
            <Fact
              testId="tokens-spent"
              labelKey="telemetry.cost"
              value={budget.spent}
            />
            <Fact
              testId="tokens-reserved"
              labelKey="projects.cost.title"
              value={budget.reserved}
            />
            <Fact
              testId="tokens-limit"
              labelKey="ui.card.total"
              value={budget.hard_limit}
            />
            <Fact
              testId="tokens-remaining"
              labelKey="projects.derived.label"
              value={remainingBudget(budget)}
            />
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
                  labelKey="telemetry.cost"
                  value={budget.spent}
                />
                <Fact
                  testId="cost-reserved"
                  labelKey="projects.cost.title"
                  value={budget.reserved}
                />
                <Fact
                  testId="cost-limit"
                  labelKey="ui.card.total"
                  value={budget.hard_limit}
                />
                <Fact
                  testId="cost-remaining"
                  labelKey="projects.derived.label"
                  value={remainingBudget(budget)}
                />
              </>
            )}
            {budgetError !== null ? (
              panelError(budgetError)
            ) : ledgerError !== null ? (
              panelError(ledgerError)
            ) : budget === null || ledger === null ? (
              <LoadingState loadingKey="ui.loading.more" />
            ) : (
              <HealthView ledger={ledger} budget={budget} />
            )}
          </div>
        );
      }
      case "local-ai":
      case "cloud-ai": {
        if (liveError !== null) {
          return panelError(liveError);
        }
        if (live === null) {
          return <LoadingState loadingKey="ui.loading.more" />;
        }
        const wanted = props.view === "local-ai" ? "LOCAL" : "CLOUD";
        const rows = splitRowsByPlacement(live)[wanted];
        if (rows.length === 0) {
          return (
            <EmptyState
              stateKey="agents.live.empty"
              actionKey={null}
              onAction={null}
            />
          );
        }
        return (
          <div>
            {rows.map((row) => (
              <div key={row.agent} data-testid={`place-row-${row.agent}`}>
                <span>{row.agent}</span>
                <span>{row.scope}</span>
                <span data-testid={`scope-kind-${row.agent}`}>
                  {classifyScope(row.scope)}
                </span>
                <span>
                  {resolveStatusHuman(
                    readStatusHuman(row),
                    row.status,
                    locale,
                  )}
                </span>
                <span>{t(placementKey(wanted))}</span>
              </div>
            ))}
          </div>
        );
      }
      case "models": {
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
            {why.assignments.map((assignment, index) => (
              <div key={index} data-testid={`model-row-${index}`}>
                <span>
                  {assignment.provider_id}/{assignment.model} {assignment.role}
                </span>
              </div>
            ))}
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
              <span>{why.snapshot.snapshot_ref}</span>
              <span>{why.snapshot.captured_at}</span>
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
      case "audits": {
        return (
          <EmptyState
            stateKey="ui.table.empty"
            actionKey={null}
            onAction={null}
          />
        );
      }
      case "errors": {
        if (projectError !== null) {
          return panelError(projectError);
        }
        return (
          <EmptyState
            stateKey="ui.table.empty"
            actionKey={null}
            onAction={null}
          />
        );
      }
      case "reports": {
        return (
          <div>
            <div data-testid="project-report-readable">
              {projectError !== null ? (
                panelError(projectError)
              ) : project === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : (
                <div data-testid="report-project-name">
                  <span>{t("shell.topbar.project")}</span>
                  <span>{project.name}</span>
                </div>
              )}
              {tasksError !== null ? (
                panelError(tasksError)
              ) : tasks === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : (
                <div data-testid="report-task-counts">
                  <span>{t("tasks.list.title")}</span>
                  {statusCounts(tasks).map(({ status, count }) => (
                    <div key={status} data-testid={`report-task-count-${status}`}>
                      <span>{taskStatusLabel(status)}</span>
                      <span>{count}</span>
                    </div>
                  ))}
                </div>
              )}
              {budgetError !== null ? (
                panelError(budgetError)
              ) : budget === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : (
                <>
                  <div data-testid="report-budget-spent">
                    <span>{t("telemetry.cost")}</span>
                    <span>{`${budget.spent} ${budget.currency}`}</span>
                  </div>
                  <div data-testid="report-budget-reserved">
                    <span>{t("projects.cost.title")}</span>
                    <span>{`${budget.reserved} ${budget.currency}`}</span>
                  </div>
                  <div data-testid="report-budget-limit">
                    <span>{t("ui.card.total")}</span>
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
              <span>{t("projects.derived.label")}</span>
              {tasksError !== null ? (
                panelError(tasksError)
              ) : ledgerError !== null ? (
                panelError(ledgerError)
              ) : budgetError !== null ? (
                panelError(budgetError)
              ) : tasks === null || ledger === null || budget === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : (
                buildReportNarrative({
                  tasks,
                  ledger,
                  budget,
                }).map((line) => <span key={line}>{line}</span>)
              )}
            </div>
            <div data-testid="project-report-derived-split">
              <span>{t("projects.derived.label")}</span>
              {tasksError !== null ? (
                panelError(tasksError)
              ) : ledgerError !== null ? (
                panelError(ledgerError)
              ) : budgetError !== null ? (
                panelError(budgetError)
              ) : ledger === null || budget === null ? (
                <LoadingState loadingKey="ui.loading.more" />
              ) : buildDerivedSplit({ ledger, budget }).length === 0 ? (
                <EmptyState stateKey="ui.table.empty" actionKey={null} onAction={null} />
              ) : (
                buildDerivedSplit({ ledger, budget }).map((allocation) => (
                  <div
                    key={allocation.packageId}
                    data-testid={`derived-split-${allocation.packageId}`}
                  >
                    <span>{t(allocation.labelKey)}</span>
                    <span>{allocation.packageId}</span>
                    <span>
                      {formatNumber(allocation.derivedCost, locale)}{" "}
                      {allocation.currency}
                    </span>
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
      <nav>
        {PROJECT_VIEWS.map((name) => (
          <button
            key={name}
            type="button"
            data-testid={projectMenuTestId(name)}
            onClick={() => {
              props.onSelect?.(name);
            }}
          >
            {t(projectViewTitleKey(name))}
          </button>
        ))}
      </nav>
      <Card
        cardId={`project-${props.view}`}
        titleKey={projectViewTitleKey(props.view)}
        collapsed={collapsed}
        onToggle={(expanded) => {
          setCollapsed(!expanded);
        }}
      >
        {renderContent()}
      </Card>
    </div>
  );
}
