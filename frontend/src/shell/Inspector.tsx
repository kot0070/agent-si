// FXLAYOUT compact inspector: five live cards (Team now / Context /
// Results / Background work / Watcher) plus six collapsed-by-default
// metric cards (Tokens / Tests / Budget / Providers / Local AI /
// Third-party apps). Every number is a served record or a sum of served
// records; a missing record renders the shared empty line or UNKNOWN,
// never an invented value.

import { useEffect, useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router-dom";
import type {
  BudgetState,
  LedgerRow,
  PartRow,
  TaskRecord,
} from "../api/iface";
import type { InspectorProps as InspectorBaseProps } from "../app/iface";
import { useApiClient } from "../app/ApiClientProvider";
import { useLiveRows } from "../agents/liveStore";
import { readLedgerWithRuns } from "../api/projectsApi";
import type { RunLedgerRow } from "../api/projectsApi";
import { dedupeLiveRows, readLiveExtras } from "../projects/viewsApi";
import { readProjectTelemetry } from "../k07next2/k07next2Api";
import type { ProjectTelemetry } from "../k07next2/k07next2Api";
import { ApiError, requestResponse } from "../api/errors";
import { formatNumber, t } from "../locale/index";
import { formatDateTime } from "../locale/index";
import { shortenLiveRef } from "../agents/agentsApi";
import {
  placementForRow,
  placementKey,
  statusHumanKey,
} from "../agents/agentsApi";
import { Icon } from "../ui/icons";
import { remainingBudget } from "../projects/projectsApi";
import { MetricCard } from "../ui/MetricCard";
import { useKitExpanded } from "../ui/Card";
import { fetchAppsCard } from "../watcher/AppsCard";
import type { AppsCardData } from "../watcher/AppsCard";
import {
  fetchWatcherJournal,
  fetchWatcherStatus,
  watcherModelName,
} from "../watcher/WatcherTab";
import { WATCHER_JOURNAL_ROUTE } from "../watcher/WatcherTab";
import type {
  WatcherJournalEntry,
  WatcherStatusData,
} from "../watcher/WatcherTab";
import { loadWatcherSettings } from "../watcher/watcherSettings";
import { useCollapsedCard } from "./collapsed";

export interface InspectorProps extends InspectorBaseProps {
  live: ReactNode;
}

const PROJECT_POLL_MS = 15000;
const DASH = "\u2013";

function readExtra(row: PartRow, name: string): unknown {
  return (row as unknown as Record<string, unknown>)[name];
}

function readText(value: unknown): string {
  if (value === undefined || value === null || value === "") {
    return DASH;
  }
  return String(value);
}

function readTokenSum(rows: PartRow[], kind: string): number {
  let sum = 0;
  for (const row of rows) {
    const tokens = readExtra(row, "tokens");
    if (typeof tokens === "object" && tokens !== null) {
      const value = (tokens as Record<string, unknown>)[kind];
      if (typeof value === "number" && Number.isFinite(value) && value > 0) {
        sum += value;
      }
    }
  }
  return sum;
}

function readCount(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return value;
  }
  return null;
}

function readSilent(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return t("shell.cards.team.silentMin", { minutes: String(value) });
  }
  return DASH;
}

function readWaiting(value: unknown): string {
  if (Array.isArray(value) && value.length > 0) {
    return value.map((item) => String(item)).join(", ");
  }
  return DASH;
}

function readRoleText(value: unknown): string {
  if (typeof value === "string") {
    const key = value.toLowerCase();
    if (key === "director") {
      return t("providers.role.director");
    }
    if (key === "manager") {
      return t("providers.role.manager");
    }
    if (key === "worker") {
      return t("providers.role.worker");
    }
    if (key === "auditor") {
      return t("providers.role.auditor");
    }
    if (key === "watcher") {
      return t("providers.role.watcher");
    }
  }
  return DASH;
}

interface RefText {
  text: string;
  title?: string;
}

function readRef(value: unknown): RefText {
  if (value === undefined || value === null || value === "") {
    return { text: DASH };
  }
  const text = String(value);
  return text.length > 40 ? { text, title: text } : { text };
}

// FXDESIGN8 short model name: the registry tail after the last slash or
// colon (provider prefixes never render in the one-line row).
function shortModelName(value: string): string {
  const afterSlash = value.split("/");
  const tail = afterSlash[afterSlash.length - 1] ?? value;
  const afterColon = tail.split(":");
  const head = afterColon[afterColon.length - 1] ?? tail;
  return head === "" ? value : head;
}

function readTaskStatus(status: string): string {
  if (status === "RUNNING") {
    return t("tasks.status.running");
  }
  if (status === "QUEUED") {
    return t("tasks.status.queued");
  }
  return status;
}

// FXDESIGN8: Team now lists every served row, including finished runs:
// after a run the rail still shows the last run's team with its real
// state (real state or none, never an Unknown chip).
function isLiveRowActive(_row: PartRow): boolean {
  return true;
}

function fractionOf(value: number, total: number): number {
  if (!(total > 0)) {
    return 0;
  }
  return value / total;
}

export function Inspector(props: InspectorProps): ReactElement {
  const client = useApiClient();
  const projectId = props.projectId;
  // FXDESIGN8: the shared agents-live store owns the single poller;
  // the rail only subscribes.
  const live = useLiveRows(client);
  const liveRows = live.rows;
  const [ledger, setLedger] = useState<LedgerRow[] | null>(null);
  const [runs, setRuns] = useState<RunLedgerRow[] | null>(null);
  const [telemetry, setTelemetry] = useState<ProjectTelemetry | null>(null);
  const [nudge, setNudge] = useState<string | null>(null);
  const [tasks, setTasks] = useState<TaskRecord[] | null>(null);
  const [budget, setBudget] = useState<BudgetState | null>(null);
  const [watcherStatus, setWatcherStatus] =
    useState<WatcherStatusData | null>(null);
  const [providers, setProviders] = useState<string[] | null>(null);
  const [testRuns, setTestRuns] = useState<string | null>(null);
  const [localModels, setLocalModels] = useState<string[] | null>(null);
  const [watchDecided, setWatchDecided] = useState<boolean | null>(null);
  const [journal, setJournal] = useState<WatcherJournalEntry[] | null>(null);
  const [watcherFailed, setWatcherFailed] = useState(false);
  const [apps, setApps] = useState<AppsCardData | null>(null);
  const [appsFailed, setAppsFailed] = useState(false);

  const [tokensCollapsed, onTokensToggle] = useCollapsedCard("fx-tokens", true);
  const [testsCollapsed, onTestsToggle] = useCollapsedCard("fx-tests", true);
  const [budgetCollapsed, onBudgetToggle] = useCollapsedCard(
    "fx-budget",
    true,
  );
  const [providersCollapsed, onProvidersToggle] = useCollapsedCard(
    "fx-providers",
    true,
  );
  const [localAiCollapsed, onLocalAiToggle] = useCollapsedCard(
    "fx-localai",
    true,
  );
  const [appsCollapsed, onAppsToggle] = useCollapsedCard("fx-apps", true);

  // FXDESIGN8: the live snapshot comes from the shared store above.

  // §6: the newest WATCH_DECISION row proves the watcher decided; the
  // served receipt carries no model, so the value stays the configured
  // setting and only the label differs (state vs setting).
  useEffect(() => {
    if (projectId === null) {
      setWatchDecided(null);
      return;
    }
    let alive = true;
    void fetch(
      `${WATCHER_JOURNAL_ROUTE}?project_id=${encodeURIComponent(projectId)}&kind=WATCH_DECISION`,
    )
      .then((response) => {
        if (!response.ok) {
          throw new Error(`watcher journal request failed: ${response.status}`);
        }
        return response.json() as Promise<unknown>;
      })
      .then((body) => {
        if (alive) {
          setWatchDecided(Array.isArray(body) && body.length > 0);
        }
      })
      .catch(() => {
        if (alive) {
          setWatchDecided(null);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId]);

  useEffect(() => {
    let alive = true;
    async function loadProject(target: string): Promise<void> {
      try {
        // FXDESIGN8: one ledger-route round trip serves both the package
        // rows and the runs key (last run verdict/tokens/files).
        const { rows, runs: runRows } = await readLedgerWithRuns(target);
        if (!alive) {
          return;
        }
        setLedger(rows);
        setRuns(runRows);
        const last = rows[rows.length - 1];
        if (last === undefined) {
          setNudge(null);
        } else {
          try {
            const report = await client.readNextPackageNudge(
              last.package_id,
            );
            if (alive) {
              setNudge(report.nudge);
            }
          } catch {
            if (alive) {
              setNudge(null);
            }
          }
        }
      } catch {
        if (alive) {
          setLedger([]);
          setRuns([]);
          setNudge(null);
        }
      }
      // FXDESIGN8: the runs key of the same ledger route is already
      // loaded above with the package rows; no second round trip.
      // FXDESIGN8: token totals per model plus the project totals, read
      // from served telemetry (metric names are served text:
      // tokens_total, cloud_calls, cost). Never invented, never a guess.
      try {
        const doc = await readProjectTelemetry(target);
        if (alive) {
          setTelemetry(doc);
        }
      } catch {
        if (alive) {
          setTelemetry(null);
        }
      }
      try {
        const next = await client.listTasks(target);
        if (alive) {
          setTasks(next);
        }
      } catch {
        if (alive) {
          setTasks([]);
        }
      }
      try {
        const next = await client.readBudget(target);
        if (alive) {
          setBudget(next);
        }
      } catch {
        if (alive) {
          setBudget(null);
        }
      }
      try {
        const [status, entries] = await Promise.all([
          fetchWatcherStatus(target),
          fetchWatcherJournal(target),
        ]);
        if (alive) {
          setWatcherStatus(status);
          setJournal(entries);
          setWatcherFailed(false);
        }
      } catch {
        if (alive) {
          setWatcherStatus(null);
          setJournal(null);
          setWatcherFailed(true);
        }
      }
      try {
        const card = await fetchAppsCard(target);
        if (alive) {
          setApps(card);
          setAppsFailed(false);
        }
      } catch {
        if (alive) {
          setApps(null);
          setAppsFailed(true);
        }
      }
      // FXTELEM: providers name connected ids from GET /api/v1/providers
      // (never an invented Unknown); tests read the latest staged run when
      // the teststage lane serves one; local AI reads the local models
      // route. Every miss reads a quiet honest line, never Unknown.
      try {
        const response = await fetch("/api/v1/providers");
        if (!response.ok) {
          throw new Error(`providers request failed: ${response.status}`);
        }
        const body = (await response.json()) as unknown;
        const rows =
          typeof body === "object" && body !== null
            ? ((body as Record<string, unknown>)["providers"] as unknown)
            : null;
        const names = Array.isArray(rows)
          ? rows
              .map((row) =>
                typeof row === "object" && row !== null
                  ? String(
                      (row as Record<string, unknown>)["provider_id"] ?? "",
                    )
                  : "",
              )
              .filter((name) => name !== "")
          : [];
        if (alive) {
          setProviders(names);
        }
      } catch {
        if (alive) {
          setProviders(null);
        }
      }
      try {
        const planResponse = await fetch(
          `/api/v1/teststage/plans/latest?project_id=${encodeURIComponent(target)}`,
        );
        if (!planResponse.ok) {
          throw new Error(`no test plan: ${planResponse.status}`);
        }
        const planBody = (await planResponse.json()) as Record<string, unknown>;
        const planId = planBody["plan_id"];
        const runResponse = await fetch(
          `/api/v1/teststage/runs/latest?project_id=${encodeURIComponent(target)}`,
        );
        if (!runResponse.ok) {
          throw new Error(`no test run: ${runResponse.status}`);
        }
        const runBody = (await runResponse.json()) as Record<string, unknown>;
        const runId = runBody["run_id"];
        if (alive) {
          setTestRuns(
            typeof planId === "string" &&
              planId !== "" &&
              typeof runId === "string" &&
              runId !== ""
              ? `${planId} / ${runId}`
              : typeof runId === "string" && runId !== ""
                ? runId
                : null,
          );
        }
      } catch {
        if (alive) {
          setTestRuns(null);
        }
      }
      try {
        const response = await fetch("/api/v1/local/models");
        if (!response.ok) {
          throw new Error(`local models request failed: ${response.status}`);
        }
        const body = (await response.json()) as unknown;
        const names = Array.isArray(body)
          ? body
              .map((row) =>
                typeof row === "object" && row !== null
                  ? String((row as Record<string, unknown>)["model"] ?? "")
                  : "",
              )
              .filter((name) => name !== "")
          : [];
        if (alive) {
          setLocalModels(names);
        }
      } catch {
        if (alive) {
          setLocalModels(null);
        }
      }
    }
    if (projectId === null) {
      setLedger(null);
      setRuns(null);
      setTelemetry(null);
      setNudge(null);
      setTasks(null);
      setBudget(null);
      setWatcherStatus(null);
      setJournal(null);
      setWatcherFailed(false);
      setApps(null);
      setAppsFailed(false);
      setProviders(null);
      setTestRuns(null);
      setLocalModels(null);
      return () => {
        alive = false;
      };
    }
    void loadProject(projectId);
    const timer = setInterval(() => {
      void loadProject(projectId);
    }, PROJECT_POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [client, projectId]);

  const rows = (liveRows ?? []).filter(isLiveRowActive);

  // FXTELEM: Team now lists one row per agent+role+model+placement+status
  // with an attempt count (the shared snapshot is the current run while
  // live, else the last run's team). "Now" means now: the dev-run engine
  // serves the run id inside each row's deliverable
  // ("artifact://run/<run_id>/<label>", engine.py), so rows from older
  // runs sort behind a Show more. RUNNING rows come first, then queued,
  // then ended rows newest-run-first. Details come from the first
  // matching live row; rows never invent, they only fold and sort.
  const foldedTeam = useMemo(() => dedupeLiveRows(rows), [rows]);
  const foldedTeamIds = useMemo(() => {
    const counts = new Map<string, number>();
    return foldedTeam.map((entry) => {
      const seen = counts.get(entry.agent) ?? 0;
      counts.set(entry.agent, seen + 1);
      const total = foldedTeam.filter(
        (other) => other.agent === entry.agent,
      ).length;
      return total <= 1
        ? `team-row-${entry.agent}`
        : `team-row-${entry.agent}-${seen}`;
    });
  }, [foldedTeam]);
  function teamRepresentative(entry: {
    agent: string;
    status: PartRow["status"];
    role?: string;
    model?: string;
  }): PartRow | null {
    for (const candidate of rows) {
      if (
        candidate.agent !== entry.agent ||
        candidate.status !== entry.status
      ) {
        continue;
      }
      const extras = readLiveExtras(candidate);
      if ((extras.role ?? undefined) !== entry.role) {
        continue;
      }
      if ((extras.model ?? undefined) !== entry.model) {
        continue;
      }
      return candidate;
    }
    return (
      rows.find(
        (candidate) =>
          candidate.agent === entry.agent &&
          candidate.status === entry.status,
      ) ?? null
    );
  }
  function teamRunIdOf(row: PartRow): string | null {
    const match = /^artifact:\/\/run\/([^/]+)\//.exec(row.deliverable);
    return match ? (match[1] ?? null) : null;
  }
  function teamStatusRank(status: PartRow["status"]): number {
    const key = String(status).toUpperCase();
    if (key === "RUNNING") {
      return 0;
    }
    if (key === "QUEUED" || key === "CREATED") {
      return 1;
    }
    return 2;
  }
  const latestTeamRunId =
    (runs ?? []).length === 0
      ? null
      : (runs?.[(runs?.length ?? 0) - 1]?.run_id ?? null);
  function teamRunRank(runId: string | null): number {
    // Latest run and unattributed rows stay visible; older listed runs
    // sort behind Show more, newest run first (higher runs index first).
    if (runId === null || runId === latestTeamRunId) {
      return Number.MAX_SAFE_INTEGER;
    }
    const at = (runs ?? []).findIndex((run) => run.run_id === runId);
    return at < 0 ? -1 : at;
  }
  interface TeamItem {
    entry: (typeof foldedTeam)[number];
    testId: string;
    row: PartRow;
    running: boolean;
    primary: boolean;
    statusRank: number;
    runRank: number;
  }
  const teamItems = useMemo(() => {
    const items: TeamItem[] = [];
    foldedTeam.forEach((entry, index) => {
      const row = teamRepresentative(entry);
      if (row === null) {
        return;
      }
      const running =
        String(entry.status).toUpperCase() === "RUNNING";
      const runRank = teamRunRank(teamRunIdOf(row));
      items.push({
        entry,
        testId: foldedTeamIds[index] ?? `team-row-${entry.agent}`,
        row,
        running,
        primary:
          running || runRank === Number.MAX_SAFE_INTEGER,
        statusRank: teamStatusRank(entry.status),
        runRank,
      });
    });
    const primary = items
      .filter((item) => item.primary)
      .sort((left, right) => left.statusRank - right.statusRank);
    const secondary = items
      .filter((item) => !item.primary)
      .sort(
        (left, right) =>
          right.runRank - left.runRank ||
          left.statusRank - right.statusRank,
      );
    return { primary, secondary };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [foldedTeam, foldedTeamIds, rows, runs]);

  const [resultsOpen, setResultsOpen] = useState(false);
  const [backgroundOpen, setBackgroundOpen] = useState(false);
  // H6: the native open runs only where the sidecar can open; a 409
  // hides the button, any other refusal names its code quietly.
  const [openFolderOk, setOpenFolderOk] = useState(true);
  const [openFolderNote, setOpenFolderNote] = useState<string | null>(null);

  async function openResultFolder(folder: string): Promise<void> {
    try {
      await requestResponse("/api/v1/sidecar/open-folder", {
        method: "POST",
        kind: "write",
        body: { path: folder },
      });
      setOpenFolderNote(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setOpenFolderOk(false);
        return;
      }
      setOpenFolderNote(
        error instanceof ApiError ? error.code : "CONTEXT_MISSING",
      );
    }
  }

  const [teamMoreOpen, setTeamMoreOpen] = useState(false);
  const teamMoreLabel = teamMoreOpen
    ? t("shell.cards.showLess")
    : t("shell.cards.showMore");

  // FXDESIGN6: the ref legend splits the bar by role. Grouped from the live
  // rows' own extras (role + tokens); with no live token data the legend
  // reads a single UNKNOWN row, never an invented split.
  interface RoleSlice {
    key: string;
    label: string;
    tokens: number;
  }

  function tokensOfRow(row: PartRow): number {
    const tokens = readExtra(row, "tokens");
    if (typeof tokens !== "object" || tokens === null) {
      return 0;
    }
    const bag = tokens as Record<string, unknown>;
    let sum = 0;
    for (const kind of ["input", "output"]) {
      const value = bag[kind];
      if (typeof value === "number" && Number.isFinite(value) && value > 0) {
        sum += value;
      }
    }
    return sum;
  }

  const roleSlices: RoleSlice[] = useMemo(() => {
    const unknownLabel = t("shell.common.unknown");
    const byRole = new Map<string, { label: string; tokens: number }>();
    for (const row of rows) {
      const raw = readExtra(row, "role");
      const key =
        typeof raw === "string" && raw !== "" ? raw.toLowerCase() : "unknown";
      const label =
        typeof raw === "string" && raw !== ""
          ? readRoleText(raw)
          : unknownLabel;
      const entry = byRole.get(key) ?? { label, tokens: 0 };
      entry.tokens += tokensOfRow(row);
      byRole.set(key, entry);
    }
    const slices = [...byRole.entries()].map(([key, entry]) => ({
      key,
      label: entry.label,
      tokens: entry.tokens,
    }));
    slices.sort((a, b) => b.tokens - a.tokens);
    const withTokens = slices.filter((slice) => slice.tokens > 0);
    if (withTokens.length === 0) {
      return [{ key: "unknown", label: unknownLabel, tokens: 0 }];
    }
    return withTokens;
  }, [rows]);

  const roleTotal = roleSlices.reduce((sum, slice) => sum + slice.tokens, 0);

  function slicePercent(slice: RoleSlice): string {
    if (!(roleTotal > 0)) {
      return t("shell.common.unknown");
    }
    return `${Math.round((slice.tokens / roleTotal) * 100)}%`;
  }

  const LEGEND_COLORS = [
    "var(--agent-si-chart-a)",
    "var(--agent-si-chart-b)",
    "var(--agent-si-chart-c)",
    "var(--agent-si-chart-d)",
    "var(--agent-si-chart-e)",
    "var(--agent-si-chart-f)",
  ];
  const warnings: Array<{ agent: string; error: string }> = useMemo(() => {
    const found: Array<{ agent: string; error: string }> = [];
    for (const row of rows) {
      const errors = readExtra(row, "errors");
      if (Array.isArray(errors)) {
        for (const error of errors) {
          found.push({ agent: row.agent, error: String(error) });
        }
      }
    }
    return found;
  }, [rows]);

  // §3: Used is the input tokens of the role's last call, Window the
  // model's KB context size when known; the percent renders only when
  // both are known. The newest served live row carries them; with no
  // live row everything reads UNKNOWN and no source line renders.
  const newest = rows.length === 0 ? null : (rows[rows.length - 1] ?? null);

  const lastPackages = (ledger ?? []).slice(-3);
  // FXDESIGN8: the last run of the runs key carries the verdict plus the
  // produced files; package rows stay as the per-package list below.
  const lastRun = (runs ?? []).length === 0 ? null : runs?.[(runs?.length ?? 0) - 1] ?? null;
  const lastRunTokens =
    lastRun !== null &&
    typeof lastRun.tokens === "number" &&
    Number.isFinite(lastRun.tokens) &&
    lastRun.tokens >= 0
      ? lastRun.tokens
      : null;
  // FXTELEM: this project's tokens are the sum of the runs key's served
  // per-run tokens (the same numbers the chat Total lines print), never a
  // global sum across projects.
  const projectRunsTotal = (runs ?? []).reduce<number | null>(
    (acc, run) => {
      const value = (run as { tokens?: unknown }).tokens;
      if (
        typeof value === "number" &&
        Number.isFinite(value) &&
        value >= 0
      ) {
        return (acc ?? 0) + value;
      }
      return acc;
    },
    null,
  );

  const tokenIn = readTokenSum(rows, "input");
  const tokenOut = readTokenSum(rows, "output");
  const liveTokenTotal = tokenIn + tokenOut;
  const unknown = t("shell.common.unknown");

  // Token totals read live rows while a run is live, otherwise the
  // project's served totals. No invented zero, no chip.
  const runLive = useMemo(
    () => rows.some((row) => String(row.status).toUpperCase() === "RUNNING"),
    [rows],
  );
  // FXTELEM round 2: the legacy global totals never render as a project
  // number; the project-scoped telemetry models (read_routes passes
  // ?project_id=) carry the project truth, with the runs key as fallback.
  // Served per-model tokens for the idle legend (raw model names, never a
  // locale lookup; UNAVAILABLE rows carry no number and stay out).
  const modelSlices = useMemo(() => {
    const models = telemetry?.models ?? [];
    const slices = [];
    for (const model of models) {
      if (typeof model.tokens === "number" && Number.isFinite(model.tokens)) {
        slices.push({ model: model.model, tokens: model.tokens });
      }
    }
    slices.sort((a, b) => b.tokens - a.tokens);
    return slices;
  }, [telemetry]);
  const modelTotal = modelSlices.reduce((sum, slice) => sum + slice.tokens, 0);
  // FXTELEM round 2: "This project" is the project-scoped telemetry
  // total (the same doc the project Tokens tab reads, so the numbers are
  // one). Fallback to the runs-key sum only when telemetry has no row.
  // The runs-key (chat answers) sum renders as its own quiet line only
  // when it differs from the telemetry total.
  const projectTotal =
    modelTotal > 0 ? modelTotal : (projectRunsTotal ?? null);
  const chatDiffers =
    projectRunsTotal !== null &&
    projectTotal !== null &&
    projectRunsTotal !== projectTotal;
  const tokenTotal = runLive ? liveTokenTotal : (projectTotal ?? liveTokenTotal);
  const tokensKnown =
    liveRows === null
      ? false
      : runLive
        ? rows.some((row) => tokensOfRow(row) > 0)
        : projectTotal !== null;

  const usedCount =
    newest === null ? null : readCount(readExtra(newest, "context"));
  const windowCount =
    newest === null ? null : readCount(readExtra(newest, "window"));
  const percentText =
    usedCount !== null && windowCount !== null && windowCount > 0
      ? `${Math.round((usedCount / windowCount) * 100)}%`
      : unknown;
  const usedText = usedCount !== null ? formatNumber(usedCount) : unknown;
  const windowText = windowCount !== null ? formatNumber(windowCount) : unknown;

  // FXDESIGN8: the last run of the runs key carries the verdict plus the
  // produced files; package rows stay as the per-package list below.
  // (lastRun itself is derived above, beside the token totals.)
  const lastRunVerdicts =
    lastRun === null
      ? []
      : (lastRun.parts ?? [])
          .map((part) => {
            const record = part as Record<string, unknown>;
            const verdict = record["verdict"];
            const partId = record["part_id"];
            if (typeof verdict === "string" && verdict !== "") {
              return typeof partId === "string" && partId !== ""
                ? `${partId}: ${verdict}`
                : verdict;
            }
            return null;
          })
          .filter((text): text is string => text !== null);
  const lastRunFiles = lastRun?.files ?? [];
  const activeTasks = (tasks ?? []).filter(
    (task) => task.status === "RUNNING" || task.status === "QUEUED",
  );
  const reportsHref =
    projectId === null ? "/projects" : `/projects/${projectId}/reports`;

  const watcherSettings = loadWatcherSettings();
  const watcherModel = watcherSettings.model;
  const latestJournal = (journal ?? [])[0];
  const watcherActionId =
    latestJournal === undefined
      ? (watcherStatus?.journal_head ?? DASH)
      : latestJournal.entry_id;
  const watcherActionAt =
    latestJournal === undefined ? "" : latestJournal.timestamp;

  const spent = budget?.spent ?? 0;
  const reserved = budget?.reserved ?? 0;
  const hard = budget?.hard_limit ?? 0;
  const remaining = budget === null ? 0 : Math.max(0, remainingBudget(budget));
  const currency = budget?.currency ?? "";
  // FXTELEM round 4: the budget state rows hold real numbers (spent sums
  // the settled reservations), so spent/reserved/remaining render them;
  // "not known" never hides a served number.
  const spentText = `${formatNumber(spent)}${currency === "" ? "" : ` ${currency}`}`;
  const remainingText = `${formatNumber(remaining)}${currency === "" ? "" : ` ${currency}`}`;
  const budgetTotal =
    budget === null
      ? unknown
      : `${formatNumber(spent)} / ${formatNumber(hard)}${currency === "" ? "" : ` ${currency}`}`;

  const [budgetExpanded, onBudgetToggleInner] = useKitExpanded(
    budgetCollapsed,
    onBudgetToggle,
  );
  // FXTELEM: providers name the connected ids from GET /api/v1/providers;
  // with none served the card reads one quiet line, never Unknown.
  const providersTotal =
    providers === null
      ? unknown
      : providers.length === 0
        ? t("shell.cards.providers.emptyLine")
        : providers.join(", ");
  const testsTotal = testRuns ?? t("shell.cards.tests.emptyLine");
  const localAiTotal =
    localModels === null
      ? unknown
      : localModels.length === 0
        ? t("shell.cards.localai.emptyLine")
        : localModels.join(", ");
  const limitText = `${formatNumber(hard)}${currency === "" ? "" : ` ${currency}`}`;
  const reservedText = `${formatNumber(reserved)}${currency === "" ? "" : ` ${currency}`}`;
  const appsCount = apps?.service_ids.length ?? 0;
  const appsTotal =
    apps === null
      ? unknown
      : `${formatNumber(appsCount)} ${t("shell.cards.apps.connected")}, ${t(apps.paused ? "shell.cards.apps.paused" : "shell.cards.apps.active")}`;

  return (
    <aside
      data-testid="inspector"
      aria-label={t("shell.inspector.live_agents")}
      data-project={projectId ?? ""}
    >
      <div data-testid="inspector-scroll" style={{ overflowY: "auto" }}>
        <section
          data-testid="inspector-card-team"
          aria-label={t("shell.cards.team.title")}
        >
          <h2 className="fx-section-title">
            <Icon name="play" />
            <span>{t("shell.cards.team.title")}</span>
          </h2>
          {warnings.length === 0 ? null : (
            <div data-testid="team-warnings">
              <span>{t("shell.cards.team.warnings")}</span>
              <ul>
                {warnings.map((warning, index) => (
                  <li key={`${warning.agent}-${index}`}>
                    {warning.agent}: {warning.error}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {props.live}
          {liveRows === null || rows.length === 0 ? (
            <p data-testid="team-empty">{t("agents.live.empty")}</p>
          ) : (
            <>
            <ul data-testid="team-rows">
              {(teamMoreOpen
                ? [...teamItems.primary, ...teamItems.secondary]
                : teamItems.primary
              ).map((item) => {
                const { entry, row, testId: rowTestId } = item;
                const fileRef = readRef(readExtra(row, "file"));
                const lastActionRef = readRef(readExtra(row, "last_action"));
                const scopeRef = shortenLiveRef(row.scope);
                const deliverableRef = shortenLiveRef(row.deliverable);
                const place = placementForRow(row);
                // FXDESIGN8 one-liner: role, short model name, status chip,
                // step. The rest rides under the row disclosure. Unevidenced
                // values render nothing: real state or none, never Unknown.
                const roleRaw = readExtra(row, "role");
                const roleKnown =
                  typeof roleRaw === "string" && roleRaw !== "";
                const modelRaw = readExtra(row, "model");
                const modelShort =
                  typeof modelRaw === "string" && modelRaw !== ""
                    ? shortModelName(modelRaw)
                    : null;
                const stepRaw = readExtra(row, "step");
                const stepKnown =
                  typeof stepRaw === "number" &&
                  Number.isFinite(stepRaw) &&
                  stepRaw > 0;
                return (
                  <li
                    key={rowTestId}
                    data-testid={rowTestId}
                    className="fx-team-row"
                  >
                    <details data-testid={`team-detail-${row.agent}`}>
                      <summary
                        data-testid={`team-line-${row.agent}`}
                        className="fx-team-line"
                      >
                        <span className="fx-team-field">{row.agent}</span>
                        {roleKnown ? (
                          <span className="fx-team-field">
                            {readRoleText(roleRaw)}
                          </span>
                        ) : null}
                        {modelShort === null ? null : (
                          <span
                            className="fx-team-field fx-truncate"
                            title={
                              modelShort === String(modelRaw)
                                ? undefined
                                : String(modelRaw)
                            }
                          >
                            {modelShort}
                          </span>
                        )}
                        <span
                          data-testid={`team-status-${row.agent}`}
                          className="fx-status-chip"
                        >
                          {t(statusHumanKey(row.status))}
                        </span>
                        {stepKnown ? (
                          <span className="fx-team-field">
                            {t("shell.cards.team.step")}{": "}
                            {String(stepRaw)}
                          </span>
                        ) : null}
                        {entry.attempts > 1 ? (
                          <span
                            data-testid={`team-attempts-${row.agent}`}
                            className="fx-team-field"
                          >
                            {t("projectView.attempts", {
                              count: entry.attempts,
                            })}
                          </span>
                        ) : null}
                        {place === "UNKNOWN" ? null : (
                          <span
                            data-testid={`team-place-${row.agent}`}
                            className="fx-place-badge"
                          >
                            {t(placementKey(place))}
                          </span>
                        )}
                      </summary>
                      <div className="fx-team-detail">
                        <span className="fx-team-field">
                          {t("agents.row.scope")}{": "}
                          <span
                            className="fx-team-value fx-truncate"
                            title={scopeRef.title}
                          >
                            {scopeRef.text}
                          </span>
                        </span>
                        <span className="fx-team-field">
                          {t("agents.row.deliverable")}{": "}
                          <span
                            className="fx-team-value fx-truncate"
                            title={deliverableRef.title}
                          >
                            {deliverableRef.text}
                          </span>
                        </span>
                        <span className="fx-team-field">
                          {t("settings.roleProfile.roleLabel")}{": "}
                          {roleKnown
                            ? readRoleText(roleRaw)
                            : DASH}
                        </span>
                        <span className="fx-team-field">
                          {t("settings.roleProfile.providerLabel")}{": "}
                          {readText(readExtra(row, "provider"))}
                        </span>
                        <span className="fx-team-field">
                          {t("settings.roleProfile.modelLabel")}{": "}
                          {readText(readExtra(row, "model"))}
                        </span>
                        <span className="fx-team-field">
                          {t("shell.cards.team.step")}{": "}
                          {stepKnown ? String(stepRaw) : DASH}
                        </span>
                        <span className="fx-team-field">
                          {t("shell.cards.team.file")}{": "}
                          <span
                            className="fx-team-value fx-truncate"
                            title={fileRef.title}
                          >
                            {fileRef.text}
                          </span>
                        </span>
                        <span className="fx-team-field">
                          {t("shell.cards.team.lastAction")}{": "}
                          <span
                            className="fx-team-value fx-truncate"
                            title={lastActionRef.title}
                          >
                            {lastActionRef.text}
                          </span>
                        </span>
                        <span className="fx-team-field">
                          {readSilent(readExtra(row, "silent_min"))}
                        </span>
                        <span className="fx-team-field">
                          {t("shell.cards.team.waiting")}{": "}
                          {readWaiting(readExtra(row, "waits"))}
                        </span>
                      </div>
                    </details>
                  </li>
                );
              })}
            </ul>
            {teamItems.secondary.length > 0 && (
              <button
                type="button"
                data-testid="team-show-more"
                className="fx-btn-quiet fx-show-more"
                aria-expanded={teamMoreOpen}
                onClick={() => {
                  setTeamMoreOpen(!teamMoreOpen);
                }}
              >
                <Icon name="expand" />
                <span>{teamMoreLabel}</span>
              </button>
            )}
            </>
          )}
          <Link data-testid="team-open-agents" to="/agents/live">
            {t("shell.cards.team.openAgents")}
          </Link>
        </section>

        <section
          data-testid="inspector-card-context"
          aria-label={t("shell.cards.context.title")}
        >
          <h2 className="fx-section-title">
            <Icon name="chart" />
            <span>{t("shell.cards.context.title")}</span>
          </h2>
          {liveRows === null ? (
            <p data-testid="context-empty">{t("empty.generic")}</p>
          ) : runLive ? (
            // FXTELEM: during a run the meter reads the live token rows:
            // percent plus window (Unknown when unserved), the live source,
            // the input/output bar and one legend with the input/output
            // rows plus the per-role slices. With no live tokens yet there
            // is one quiet line and no empty bar.
            liveTokenTotal > 0 ? (
              <>
                <div data-testid="ctx-top" className="fx-ctx-top">
                  <p data-testid="ctx-percent">
                    {t("shell.cards.context.percentValue", { value: percentText })}
                  </p>
                  <p data-testid="ctx-window">
                    {usedText} / {windowText}
                  </p>
                </div>
                <p data-testid="ctx-source" className="fx-quiet">
                  {t("shell.cards.context.source")}{" "}
                  {t("shell.cards.context.sourceLive")}
                </p>
                <div data-testid="ctx-bar" className="fx-ctx-bar">
                <div
                  data-testid="ctx-bar-input"
                  className="fx-ctx-seg"
                  style={{
                    width: `${fractionOf(tokenIn, tokenTotal) * 100}%`,
                  }}
                />
                <div
                  data-testid="ctx-bar-output"
                  className="fx-ctx-seg"
                  style={{
                    width: `${fractionOf(tokenOut, tokenTotal) * 100}%`,
                  }}
                />
              </div>
                <ul data-testid="ctx-legend" className="fx-legend">
                  <li
                    data-testid="ctx-legend-input"
                    className="fx-legend-row"
                  >
                    <span className="fx-legend-name">
                      {t("shell.cards.context.input")}
                    </span>{" "}
                    <span className="fx-legend-tokens">
                      {formatNumber(tokenIn)}
                    </span>
                  </li>
                  <li
                    data-testid="ctx-legend-output"
                    className="fx-legend-row"
                  >
                    <span className="fx-legend-name">
                      {t("shell.cards.context.output")}
                    </span>{" "}
                    <span className="fx-legend-tokens">
                      {formatNumber(tokenOut)}
                    </span>
                  </li>
                {roleSlices.map((slice, index) => (
                  <li
                    key={slice.key}
                    data-testid={`ctx-legend-role-${slice.key}`}
                    className="fx-legend-row"
                  >
                    <span
                      className="fx-legend-dot"
                      role="img"
                      aria-label={slice.label}
                      title={slice.label}
                      style={{
                        backgroundColor:
                          LEGEND_COLORS[index % LEGEND_COLORS.length] ??
                          "var(--agent-si-chart-a)",
                      }}
                    />
                    <span className="fx-legend-name">{slice.label}</span>
                    <span className="fx-legend-tokens">
                      {formatNumber(slice.tokens)}
                    </span>
                    <span className="fx-legend-pct">
                      {slicePercent(slice)}
                    </span>
                  </li>
                ))}
              </ul>
              </>
            ) : (
              <p
                data-testid="ctx-unknown"
                className="fx-quiet-line"
                title={unknown}
              >
                &mdash;
              </p>
            )
          ) : projectTotal === null ? (
            // Idle with no served totals anywhere: one quiet line, never
            // an invented zero or an empty bar.
            <p
              data-testid="context-empty"
              className="fx-quiet-line"
              title={t("shell.common.unknown")}
            >
              {t("shell.cards.context.noUsage")}
            </p>
          ) : (
            // Idle: every number is named. "This project" is the runs key
            // sum (the chat Total lines add up to the same number), "Last
            // run" the last run's tokens; the per-model legend breaks down
            // the project-scoped telemetry total. No window is served idle,
            // so no percent is rendered.
            <>
              <p data-testid="ctx-used" className="fx-quiet">
                {t("shell.cards.context.projectTotal")}:{" "}
                {formatNumber(projectTotal)}
              </p>
              {lastRunTokens !== null && lastRunTokens !== projectTotal ? (
                <p data-testid="ctx-last-run" className="fx-quiet">
                  {t("shell.cards.context.lastRun")}:{" "}
                  {formatNumber(lastRunTokens)}
                </p>
              ) : null}
              {chatDiffers ? (
                <p data-testid="ctx-chat" className="fx-quiet">
                  {t("shell.cards.context.chatAnswers")}:{" "}
                  {formatNumber(projectRunsTotal ?? 0)}
                </p>
              ) : null}
              {modelTotal > 0 ? (
                <ul data-testid="ctx-legend" className="fx-legend">
                  {modelSlices.map((slice, index) => (
                    <li
                      key={slice.model}
                      data-testid={`ctx-legend-model-${slice.model}`}
                      className="fx-legend-row"
                    >
                      <span
                        className="fx-legend-dot"
                        role="img"
                        aria-label={slice.model}
                        title={slice.model}
                        style={{
                          backgroundColor:
                            LEGEND_COLORS[index % LEGEND_COLORS.length] ??
                            "var(--agent-si-chart-a)",
                        }}
                      />
                      <span className="fx-legend-name">{slice.model}</span>
                      <span className="fx-legend-tokens">
                        {formatNumber(slice.tokens)}
                      </span>
                      <span className="fx-legend-pct">
                        {modelTotal > 0
                          ? `${Math.round((slice.tokens / modelTotal) * 100)}%`
                          : unknown}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
        </section>

        <section
          data-testid="inspector-card-results"
          aria-label={t("shell.cards.results.title")}
        >
          <h2 className="fx-section-title">
            <Icon name="file" />
            <span>{t("shell.cards.results.title")}</span>
          </h2>
          {/* FXTELEM: the last run's verdict plus files read the runs key,
              so a real run shows even when no package rows were recorded.
              Only with neither a run nor packages is the tab honestly empty. */}
          {projectId === null || ledger === null || runs === null ? (
            <p data-testid="results-empty">{t("empty.generic")}</p>
          ) : lastRun === null && lastPackages.length === 0 ? (
            <p data-testid="results-empty">{t("empty.generic")}</p>
          ) : (
            <>
              {nudge === null ? null : (
                <p data-testid="result-nudge" className="fx-quiet">
                  {t("shell.cards.results.next")}: {nudge}
                </p>
              )}
              {/* FXDESIGN8: the last run's verdict plus its files, read from
                  the runs key of the ledger route; served facts only. */}
              {lastRun === null ? null : (
                <>
                <div data-testid="result-last" className="fx-result-row">
                  <Icon name="file" />
                  <span
                    data-testid="result-last-verdict"
                    className="fx-truncate"
                    title={
                      lastRun.summary !== undefined && lastRun.summary !== ""
                        ? lastRun.summary
                        : undefined
                    }
                  >
                    {lastRun.run_id}
                    {lastRun.summary !== undefined && lastRun.summary !== ""
                      ? `: ${lastRun.summary}`
                      : null}
                    {lastRunVerdicts.length === 0
                      ? null
                      : ` (${lastRunVerdicts.join(", ")})`}
                  </span>{" "}
                  <Link
                    data-testid={`result-open-${lastRun.run_id}`}
                    to={reportsHref}
                    className="fx-why-quiet"
                  >
                    {t("shell.cards.results.open")}
                  </Link>
                </div>
                {/* H6: the run record's folder plus its produced files;
                    Open folder shows only where the sidecar can open. */}
                {lastRun.folder ? (
                  <p
                    data-testid="result-last-folder"
                    className="fx-quiet fx-truncate"
                    title={lastRun.folder}
                  >
                    {lastRun.folder}
                  </p>
                ) : null}
                {lastRun.folder && openFolderOk ? (
                  <button
                    type="button"
                    data-testid="result-open-folder"
                    className="fx-btn-quiet"
                    onClick={() => {
                      if (lastRun.folder) {
                        void openResultFolder(lastRun.folder);
                      }
                    }}
                  >
                    {t("shell.cards.results.openFolder")}
                  </button>
                ) : null}
                {openFolderNote !== null ? (
                  <p data-testid="result-open-folder-note" className="fx-quiet">
                    {openFolderNote}
                  </p>
                ) : null}
                </>
              )}
              {lastRunFiles.length === 0 ? null : (
                <ul data-testid="result-last-files" className="fx-bg-list">
                  {lastRunFiles.map((file, index) => (
                    <li
                      key={`${file}-${index}`}
                      data-testid={`result-file-${index}`}
                      className="fx-bg-row"
                    >
                      <Icon name="file" />
                      <span className="fx-truncate" title={file}>
                        {file}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <ul className="fx-result-list">
                {(resultsOpen ? lastPackages : lastPackages.slice(0, 5)).map(
                  (entry) => (
                    <li
                      key={entry.package_id}
                      data-testid={`result-row-${entry.package_id}`}
                      className="fx-result-row"
                    >
                      <Icon name="file" />
                      <span className="fx-truncate">{entry.package_id}</span>
                      <Link
                        data-testid={`result-open-${entry.package_id}`}
                        to={reportsHref}
                        className="fx-why-quiet"
                      >
                        {t("shell.cards.results.open")}
                      </Link>
                    </li>
                  ),
                )}
              </ul>
              {lastPackages.length > 5 ? (
                <button
                  type="button"
                  data-testid="results-show-more"
                  className="fx-btn-quiet fx-show-more"
                  aria-expanded={resultsOpen}
                  onClick={() => {
                    setResultsOpen(!resultsOpen);
                  }}
                >
                  <Icon name="expand" />
                  <span>
                    {resultsOpen
                      ? t("shell.cards.showLess")
                      : t("shell.cards.showMore")}
                  </span>
                </button>
              ) : null}
            </>
          )}
        </section>

        <section
          data-testid="inspector-card-background"
          aria-label={t("shell.cards.background.title")}
        >
          <h2 className="fx-section-title">
            <Icon name="play" />
            <span>{t("shell.cards.background.title")}</span>
            <span data-testid="background-count" className="fx-count">
              {formatNumber(activeTasks.length)}
            </span>
          </h2>
          {projectId === null ||
          tasks === null ||
          activeTasks.length === 0 ? (
            <p data-testid="background-empty">{t("empty.generic")}</p>
          ) : (
            <>
              <ul className="fx-bg-list">
                {(backgroundOpen
                  ? activeTasks
                  : activeTasks.slice(0, 5)
                ).map((task) => (
                  <li
                    key={task.task_id}
                    data-testid={`bg-row-${task.task_id}`}
                    className="fx-bg-row"
                  >
                    <Icon name="play" />
                    <span className="fx-truncate">{task.title}</span>
                    <span className="fx-quiet">
                      {readTaskStatus(task.status)}
                    </span>
                  </li>
                ))}
              </ul>
              {activeTasks.length > 5 ? (
                <button
                  type="button"
                  data-testid="background-show-more"
                  className="fx-btn-quiet fx-show-more"
                  aria-expanded={backgroundOpen}
                  onClick={() => {
                    setBackgroundOpen(!backgroundOpen);
                  }}
                >
                  <Icon name="expand" />
                  <span>
                    {backgroundOpen
                      ? t("shell.cards.showLess")
                      : t("shell.cards.showMore")}
                  </span>
                </button>
              ) : null}
            </>
          )}
        </section>

        <section
          data-testid="inspector-card-watcher"
          aria-label={t("shell.cards.watcher.title")}
        >
          <h2 className="fx-section-title">
            <Icon name="watch" />
            <span>{t("shell.cards.watcher.title")}</span>
          </h2>
          {projectId === null ||
          watcherFailed ||
          watcherStatus === null ? (
            <p data-testid="watcher-empty">{t("empty.generic")}</p>
          ) : (
            <>
              <p data-testid="watcher-state">
                {t("shell.cards.watcher.state")}{": "}
                {watcherStatus.integrity_ok
                  ? t("shell.cards.watcher.ok")
                  : t("shell.cards.watcher.failed")}
              </p>
              <p data-testid="watcher-model">
                {t("watcher.tab.model")}: {watcherModelName(watcherModel)}
                {" \u00b7 "}
                {t("watcher.tab.cloudFallback")}{" "}
                {watcherSettings.cloudFallback
                  ? t("projects.tests.local.on")
                  : t("projects.tests.local.off")}
              </p>
              <p data-testid="watcher-action">
                {t("shell.cards.team.lastAction")}: {watcherActionId}
                {" \u00b7 "}
                {formatDateTime(watcherActionAt)}
              </p>
              <Link data-testid="watcher-open" to="/watcher">
                {t("shell.cards.watcher.open")}
              </Link>
            </>
          )}
        </section>

        {tokensKnown ? (
          <>
            <MetricCard
              cardId="fx-tokens"
              titleKey="shell.cards.tokens.title"
              subtitleKey="shell.cards.tokens.subtitle"
              totalKey="shell.cards.tokens.total"
              totalText={formatNumber(tokenTotal)}
              segments={
                runLive
                  ? [
                      {
                        segmentKey: "shell.cards.context.input",
                        fraction: fractionOf(tokenIn, tokenTotal),
                      },
                      {
                        segmentKey: "shell.cards.context.output",
                        fraction: fractionOf(tokenOut, tokenTotal),
                      },
                    ]
                  : []
              }
              segmentTexts={
                runLive
                  ? {
                      "shell.cards.context.input": formatNumber(tokenIn),
                      "shell.cards.context.output": formatNumber(tokenOut),
                    }
                  : undefined
              }
              collapsed={tokensCollapsed}
              onToggle={onTokensToggle}
            />
            {runLive || modelSlices.length === 0 ? null : (
              <ul data-testid="tokens-extra-kinds" className="fx-legend">
                {modelSlices.map((slice) => (
                  <li key={slice.model} data-testid={`tokens-kind-${slice.model}`}>
                    <span className="fx-legend-name">{slice.model}</span>{" "}
                    <span className="fx-legend-tokens">
                      {formatNumber(slice.tokens)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {/* FXTELEM: idle totals are named: the last run's tokens and
                this project's runs-key sum. The per-model rows above add up
                to the project-scoped telemetry total. */}
            {runLive ? null : (
              <>
                {lastRunTokens !== null ? (
                  <p data-testid="tokens-last-run" className="fx-quiet">
                    {t("shell.cards.context.lastRun")}:{" "}
                    {formatNumber(lastRunTokens)}
                  </p>
                ) : null}
                {projectTotal !== null && projectTotal !== lastRunTokens ? (
                  <p data-testid="tokens-project" className="fx-quiet">
                    {t("shell.cards.context.projectTotal")}:{" "}
                    {formatNumber(projectTotal)}
                  </p>
                ) : null}
                {chatDiffers ? (
                  <p data-testid="tokens-chat" className="fx-quiet">
                    {t("shell.cards.context.chatAnswers")}:{" "}
                    {formatNumber(projectRunsTotal ?? 0)}
                  </p>
                ) : null}
              </>
            )}
          </>
        ) : (
          <>
            <MetricCard
              cardId="fx-tokens"
              titleKey="shell.cards.tokens.title"
              subtitleKey="shell.cards.tokens.subtitle"
              totalKey="shell.cards.tokens.total"
              totalText={unknown}
              segments={[]}
              collapsed={tokensCollapsed}
              onToggle={onTokensToggle}
            />
            <p data-testid="tokens-unknown" className="fx-quiet-line">
              {t("shell.cards.context.noUsage")}
            </p>
          </>
        )}
        <MetricCard
          cardId="fx-tests"
          titleKey="shell.cards.tests.title"
          subtitleKey="shell.cards.tests.subtitle"
          totalKey="shell.cards.tests.total"
          totalText={testsTotal}
          segments={[]}
          collapsed={testsCollapsed}
          onToggle={onTestsToggle}
        />
        {/* FXTELEM: one budget block only: limit, spent, reserved and
            remaining as a single spaced list, never legend plus a repeated
            list, never glued. Spent reads the unknown-price line when no
            served cost number exists. */}
        <section
          data-testid="kit-metric-fx-budget"
          aria-label={t("shell.cards.budget.title")}
          style={{
            backgroundColor: "var(--agent-si-surface)",
            color: "var(--agent-si-ink)",
            borderColor: "var(--agent-si-card-border)",
          }}
        >
          <h2>{t("shell.cards.budget.title")}</h2>
          <button
            type="button"
            data-testid="kit-toggle-fx-budget"
            aria-label={t("ui.card.toggle")}
            aria-expanded={budgetExpanded}
            className="fx-kit-toggle"
            onClick={onBudgetToggleInner}
          />
          <p data-testid="kit-sub-fx-budget">
            {t("shell.cards.budget.subtitle")}
          </p>
          {budgetExpanded ? (
            budget === null ? (
              <p data-testid="budget-unknown" className="fx-quiet-line">
                {unknown}
              </p>
            ) : (
              <ul
                data-testid="budget-facts"
                className="fx-budget-facts"
                style={{
                  display: "flex",
                  gap: "1rem",
                  flexWrap: "wrap",
                  listStyle: "none",
                  padding: 0,
                }}
              >
                <li data-testid="budget-row-limit">
                  {t("projectView.cost.limit")}: {limitText}
                </li>
                <li data-testid="budget-row-spent">
                  {t("shell.cards.budget.spent")}: {spentText}
                </li>
                <li data-testid="budget-row-reserved">
                  {t("shell.cards.budget.reserved")}: {reservedText}
                </li>
                <li data-testid="budget-row-remaining">
                  {t("shell.cards.budget.remaining")}: {remainingText}
                </li>
              </ul>
            )
          ) : (
            <span data-testid="kit-collapsed-line">
              <span>{t("shell.cards.budget.title")}</span>
              <span>{budgetTotal}</span>
            </span>
          )}
        </section>
        <MetricCard
          cardId="fx-providers"
          titleKey="shell.cards.providers.title"
          subtitleKey="shell.cards.providers.subtitle"
          totalKey="shell.cards.providers.total"
          totalText={providersTotal}
          segments={[]}
          collapsed={providersCollapsed}
          onToggle={onProvidersToggle}
        />
        <MetricCard
          cardId="fx-localai"
          titleKey="shell.cards.localai.title"
          subtitleKey="shell.cards.localai.subtitle"
          totalKey="shell.cards.localai.total"
          totalText={localAiTotal}
          segments={[]}
          collapsed={localAiCollapsed}
          onToggle={onLocalAiToggle}
        />
        <MetricCard
          cardId="fx-apps"
          titleKey="shell.cards.apps.title"
          subtitleKey="shell.cards.apps.subtitle"
          totalKey="shell.cards.apps.total"
          totalText={appsTotal}
          segments={[]}
          collapsed={appsCollapsed}
          onToggle={onAppsToggle}
        />
      </div>
    </aside>
  );
}
