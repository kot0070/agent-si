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
import { dedupeLiveRows, humanRunRef, readLiveExtras } from "../projects/viewsApi";
import { readProjectTelemetry } from "../k07next2/k07next2Api";
import type { ProjectTelemetry } from "../k07next2/k07next2Api";
import { ApiError, requestResponse } from "../api/errors";
import { formatNumber, pluralUnit, t, useLocale } from "../locale/index";
import { formatScreenTime } from "../locale/index";
import { resolveStatusHuman, shortenLiveRef } from "../agents/agentsApi";
import {
  placementForRow,
  placementKey,
  statusHumanKey,
} from "../agents/agentsApi";
import { Icon } from "../ui/icons";
import { Spinner } from "../ui/Spinner";
import { remainingBudget } from "../projects/projectsApi";
import { MetricCard } from "../ui/MetricCard";
import { fetchAppsCard } from "../watcher/AppsCard";
import type { AppsCardData } from "../watcher/AppsCard";
import { backoffForFailures, isHiddenTick, onVisible } from "../api/polling";
import {
  describeLastAction,
  fetchWatcherJournal,
  fetchWatcherStatus,
  WatcherJournalList,
} from "../watcher/WatcherTab";
import { RULE_CARDS } from "../watcher/ruleCards";
import { loadCardHangMinutes } from "../watcher/watcherSettings";
import { WATCHER_JOURNAL_ROUTE } from "../watcher/WatcherTab";
import type {
  WatcherJournalEntry,
  WatcherStatusData,
} from "../watcher/WatcherTab";
import { useCollapsedCard } from "./collapsed";
import { RailHead } from "./RailCard";
import {
  INSPECTOR_TOGGLE_EVENT,
  inspectorEventOpen,
  readInspectorOpen,
  setInspectorOpen,
} from "./inspectorDrawer";

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

// FXLOOK D5: served human status for a live row (uk/en pair wins,
// else the status code maps through tasks.status.*).
function readStatusHuman(row: PartRow): unknown {
  return (row as unknown as Record<string, unknown>).status_human;
}

// FXLOOK D5: a human name for a served agent id when no role rides the
// row (raw ids never reach the summary line).
function prettifyAgentId(agent: string): string {
  const words = agent.split(/[-_]+/).filter((part) => part !== "");
  if (words.length === 0) {
    return agent;
  }
  return words
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
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
  const { locale } = useLocale();
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
  const [moreCollapsed, onMoreToggle] = useCollapsedCard("fx-more", true);
  // FXFACTS F8: drawer open state mirrors the shell class through the
  // shared drawer event; Esc closes the drawer.
  const [drawerOpen, setDrawerOpen] = useState<boolean>(() =>
    readInspectorOpen(),
  );
  useEffect(() => {
    function onDrawerToggle(event: Event): void {
      setDrawerOpen(inspectorEventOpen(event));
    }
    window.addEventListener(INSPECTOR_TOGGLE_EVENT, onDrawerToggle);
    return () => {
      window.removeEventListener(INSPECTOR_TOGGLE_EVENT, onDrawerToggle);
    };
  }, []);
  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setInspectorOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [drawerOpen]);
  // FXFACTS F10: big cards collapse like metric cards. Fresh profile:
  // Team now open, the others closed; a live run keeps Team now open.
  const [teamCollapsed, onTeamToggle] = useCollapsedCard("fx-team", false);
  const [resultsCollapsed, onResultsToggle] = useCollapsedCard(
    "fx-results",
    true,
  );
  const [backgroundCollapsed, onBackgroundToggle] = useCollapsedCard(
    "fx-background",
    true,
  );
  const [watcherCollapsed, onWatcherToggle] = useCollapsedCard(
    "fx-watcher",
    true,
  );
  const [contextCollapsed, onContextToggle] = useCollapsedCard(
    "fx-context",
    true,
  );

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
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function loadProject(target: string): Promise<boolean> {
      let ok = true;
      try {
        // FXDESIGN8: one ledger-route round trip serves both the package
        // rows and the runs key (last run verdict/tokens/files).
        const { rows, runs: runRows } = await readLedgerWithRuns(target);
        if (!alive) {
          return true;
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
        ok = false;
        // FXCARDS C2: a failed refresh keeps last good values for the same
        // project; only a project change clears (the projectId null branch).
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
        // FXCARDS C2: keep last good telemetry on a failed refresh.
      }
      try {
        const next = await client.listTasks(target);
        if (alive) {
          setTasks(next);
        }
      } catch {
        // FXCARDS C2: keep last good tasks on a failed refresh.
      }
      try {
        const next = await client.readBudget(target);
        if (alive) {
          setBudget(next);
        }
      } catch {
        // FXCARDS C2: keep last good budget on a failed refresh.
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
        // FXCARDS C2: keep last good watcher/app rows on a failed refresh.
      }
      try {
        const card = await fetchAppsCard(target);
        if (alive) {
          setApps(card);
          setAppsFailed(false);
        }
      } catch {
        // FXCARDS C2: keep last good apps card on a failed refresh.
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
        // FXCARDS C2: keep last good providers on a failed refresh.
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
        // FXCARDS C2: keep last good test runs on a failed refresh.
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
        // FXCARDS C2: keep last good local models on a failed refresh.
      }
      return ok;
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
    const target: string = projectId;
    void loadProject(target);
    // FXCLASS P5: skip the tick when hidden, one fresh read on
    // visibilitychange, back off 3-6-12-30 s on failure, reset on success.
    function chain(): void {
      if (timer !== null) {
        clearTimeout(timer);
      }
      const delay =
        failures === 0 ? PROJECT_POLL_MS : backoffForFailures(failures);
      timer = setTimeout(() => {
        timer = null;
        if (!alive) {
          return;
        }
        if (isHiddenTick()) {
          chain();
          return;
        }
        void loadProject(target).then((ok) => {
          if (!alive) {
            return;
          }
          failures = ok ? 0 : failures + 1;
          chain();
        });
      }, delay);
    }
    chain();
    const stopVisible = onVisible(() => {
      if (alive && !isHiddenTick()) {
        void loadProject(target).then((ok) => {
          if (alive) {
            failures = ok ? 0 : failures + 1;
          }
        });
      }
    });
    return () => {
      alive = false;
      if (timer !== null) {
        clearTimeout(timer);
      }
      stopVisible();
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
  // FXCARDS C1: the served runs key is newest-first (records.py sorts
  // reverse=True and serves as-is), so runs[0] is the latest run.
  const latestTeamRunId =
    (runs ?? []).length === 0 ? null : (runs?.[0]?.run_id ?? null);
  function teamRunRank(runId: string | null): number {
    // Latest run and unattributed rows stay visible; older listed runs
    // sort behind Show more, newest run first (lower runs index first).
    if (runId === null || runId === latestTeamRunId) {
      return Number.MAX_SAFE_INTEGER;
    }
    const at = (runs ?? []).findIndex((run) => run.run_id === runId);
    // A run id with no served row sorts after every listed older run.
    return at < 0 ? Number.MAX_SAFE_INTEGER - 1 : at;
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
          left.runRank - right.runRank ||
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
  // FXCARDS C1: served runs are newest-first, so the last run is
  // runs[0], never runs[length-1] (length-1 is the oldest run).
  const lastRun = (runs ?? []).length === 0 ? null : (runs?.[0] ?? null);
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
  // FXFACTS F10: the Results closed value is the run title (or verdict
  // word); the raw id rides tooltips and details only.
  const lastRunTitle =
    lastRun !== null &&
    typeof lastRun.title === "string" &&
    lastRun.title.trim() !== ""
      ? lastRun.title.trim()
      : null;
  const lastRunFiles = lastRun?.files ?? [];
  const activeTasks = (tasks ?? []).filter(
    (task) => task.status === "RUNNING" || task.status === "QUEUED",
  );
  const reportsHref =
    projectId === null ? "/projects" : `/projects/${projectId}/reports`;

  const latestJournal =
    journal === null || journal.length === 0
      ? undefined
      : journal[journal.length - 1];
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

  // FXFACTS F10: every card opens through its own collapsed flag; Team now
  // stays open on a fresh profile and while a run is live; with no
  // project every card stays closed.
  const teamOpen = projectId !== null && (runLive || !teamCollapsed);
  const resultsCardOpen = !resultsCollapsed;
  const backgroundCardOpen = !backgroundCollapsed;
  const watcherOpen = !watcherCollapsed;
  const contextOpen = tokensKnown && !contextCollapsed;
  const budgetOpen = budget !== null && !budgetCollapsed;
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
  // FXTABS J7: metric cards with served data render before empty ones
  // (flex order below); an empty card collapses to one line. Numbers are
  // untouched: only order plus the collapsed flag change here.
  const tokensHasData = tokensKnown;
  const testsHasData = testRuns !== null;
  const budgetHasData = budget !== null;
  const providersHasData = (providers ?? []).length > 0;
  const localAiHasData = (localModels ?? []).length > 0;
  const appsHasData = appsCount > 0;
  // FXFACTS F10: token extras render only with the open card; the More
  // summary counts the metric cards holding data.
  const tokensOpen = tokensKnown && tokensHasData && !tokensCollapsed;
  const moreDataCount = [
    tokensHasData,
    testsHasData,
    providersHasData,
    localAiHasData,
    appsHasData,
  ].filter((has) => has).length;
  const moreOpen = !moreCollapsed;

  return (
    <aside
      data-testid="inspector"
      id="inspector"
      data-open={drawerOpen ? "true" : "false"}
      className={drawerOpen ? undefined : "fx-drawer-hidden"}
      aria-label={t("shell.inspector.live_agents")}
      data-project={projectId ?? ""}
    >
      <button
        type="button"
        data-testid="inspector-close"
        className="fx-inspector-close"
        aria-label={t("shell.topbar.inspectorClose")}
        onClick={() => {
          setInspectorOpen(false);
        }}
      >
        {t("shell.topbar.inspectorClose")}
      </button>
      <div data-testid="inspector-scroll" style={{ overflowY: "auto" }}>
        <section
          data-testid="inspector-card-team"
          aria-label={t("shell.cards.team.title")}
        >
          <RailHead
            testId={rows.length === 0 ? undefined : "rail-toggle-team"}
            icon="play"
            title={t("shell.cards.team.title")}
            value={rows.length === 0 ? <>&mdash;</> : formatNumber(rows.length)}
            expanded={teamOpen}
            onToggle={() => onTeamToggle(!teamOpen)}
            staticRow={rows.length === 0}
          />
          {teamOpen && rows.length > 0 ? (
          <>
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
                // FXLOOK D5 one-liner: role plus live status ("Director,
                // Running"), the status chip, step. The raw agent id and
                // the full model id ride the tooltip + disclosure below.
                // Unevidenced values render nothing: real state or none,
                // never Unknown.
                const roleRaw = readExtra(row, "role");
                const roleKnown =
                  typeof roleRaw === "string" && roleRaw !== "";
                const modelRaw = readExtra(row, "model");
                const modelShort =
                  typeof modelRaw === "string" && modelRaw !== ""
                    ? shortModelName(modelRaw)
                    : null;
                // FXLOOK D5: the full model id rides the summary
                // tooltip (title) and the details row below.
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
                      {/* FXFACTS F14: one line (role, short model,
                          status, middle dots in CSS); the rest opens. */}
                      <summary
                        data-testid={`team-line-${row.agent}`}
                        className="fx-team-line"
                        // FXLOOK D5 + FXFACTS F14: the summary reads human —
                        // role plus live status and the short model; never
                        // the raw agent id or the full model id (the full
                        // model rides the tooltip).
                        title={
                          typeof modelRaw === "string" && modelRaw !== ""
                            ? modelRaw
                            : undefined
                        }
                      >
                        <span className="fx-team-field">
                          {roleKnown
                            ? readRoleText(roleRaw)
                            : prettifyAgentId(row.agent)}
                          {", "}
                          {resolveStatusHuman(
                            readStatusHuman(row),
                            row.status,
                            locale,
                          )}
                        </span>
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
                          className="fx-team-field"
                        >
                          {t(statusHumanKey(row.status))}
                        </span>
                        {item.running ? <Spinner /> : null}
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
                        {/* FXLOOK D5: the raw agent id lives here in the
                            details, never in the summary line above. */}
                        <span className="fx-team-field">
                          {t("agents.row.agent")}{": "}
                          <span className="fx-team-value">{row.agent}</span>
                        </span>
                        <span className="fx-team-field">
                          <span
                            className="fx-team-value fx-truncate"
                            title={row.agent}
                          >
                            {row.agent}
                          </span>
                        </span>
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
          </>
          ) : null}
        </section>

        <section
          data-testid="inspector-card-context"
          aria-label={t("shell.cards.context.title")}
        >
          <RailHead
            testId={tokensKnown ? "rail-toggle-context" : undefined}
            icon="chart"
            title={t("shell.cards.context.title")}
            value={
              tokensKnown ? formatNumber(tokenTotal) : <>&mdash;</>
            }
            expanded={contextOpen}
            onToggle={() => onContextToggle(!contextOpen)}
            staticRow={!tokensKnown}
          />
          {contextOpen ? (
          <>
          {liveRows === null ? (
            <p data-testid="context-empty">{t("empty.generic")}</p>
          ) : runLive ? (
            // FXTELEM: during a run the meter reads the live token rows:
            // percent plus window (Unknown when unserved), the live source,
            // the input/output bar and one legend with the input/output
            // rows plus the per-role slices. With no live tokens yet there
            // is one quiet line and no empty bar.
            liveTokenTotal > 0 ? (
              // FXTABS T9: used of window when the window is served; just
              // the used count when it is not. No percent is rendered off
              // an unknown window.
              <>
                <div data-testid="ctx-top" className="fx-ctx-top">
                  {windowCount !== null && windowCount > 0 ? (
                    <>
                      <p data-testid="ctx-percent">
                        {t("shell.cards.context.percentValue", { value: percentText })}
                      </p>
                      <p data-testid="ctx-window">
                        {usedText} / {windowText}
                      </p>
                    </>
                  ) : (
                    <p data-testid="ctx-window">{usedText}</p>
                  )}
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
              {/* FXFACTS F10: idle figures read as dl rows. */}
              <dl data-testid="ctx-facts">
              <div data-testid="ctx-used">
                <dt>{t("shell.cards.context.projectTotal")}</dt>
                <dd>{formatNumber(projectTotal)}</dd>
              </div>
              {lastRunTokens !== null && lastRunTokens !== projectTotal ? (
                <div data-testid="ctx-last-run">
                  <dt>{t("shell.cards.context.lastRun")}</dt>
                  <dd>{formatNumber(lastRunTokens)}</dd>
                </div>
              ) : null}
              {chatDiffers ? (
                <div data-testid="ctx-chat">
                  <dt>{t("shell.cards.context.chatAnswers")}</dt>
                  <dd>{formatNumber(projectRunsTotal ?? 0)}</dd>
                </div>
              ) : null}
              </dl>
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
          </>
          ) : null}
        </section>

        <section
          data-testid="inspector-card-results"
          aria-label={t("shell.cards.results.title")}
        >
          <RailHead
            testId={
              lastRun === null && lastPackages.length === 0
                ? undefined
                : "rail-toggle-results"
            }
            icon="file"
            title={t("shell.cards.results.title")}
            value={
              lastRun === null && lastPackages.length === 0 ? (
                <>&mdash;</>
              ) : (
                lastRunTitle ??
                (lastRun === null
                  ? formatNumber(lastPackages.length)
                  : lastRun.success === true
                    ? t("projectView.runs.done")
                    : lastRun.success === false
                      ? t("projectView.runs.failed")
                      : (<>&mdash;</>))
              )
            }
            expanded={resultsCardOpen}
            onToggle={() => onResultsToggle(!resultsCardOpen)}
            staticRow={lastRun === null && lastPackages.length === 0}
          />
          {resultsCardOpen &&
          !(lastRun === null && lastPackages.length === 0) ? (
          <>
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
                  the runs key of the ledger route; served facts only.
                  FXZERO R2: the task title (or a short human name) is
                  the primary text; the raw run id rides the details
                  (tooltip) only, never as visible text. */}
              {lastRun === null ? null : (
                <>
                <div data-testid="result-last" className="fx-result-row">
                  <Icon name="file" />
                  <span
                    data-testid="result-last-verdict"
                    className="fx-truncate"
                    title={
                      lastRun.summary !== undefined && lastRun.summary !== ""
                        ? `${lastRun.run_id}: ${lastRun.summary}`
                        : lastRun.run_id
                    }
                  >
                    {typeof lastRun.title === "string" &&
                    lastRun.title.trim() !== ""
                      ? lastRun.title
                      : t("shell.cards.results.latestRun")}
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
                      <span
                        className="fx-truncate"
                        title={humanRunRef(entry.package_id).title}
                      >
                        {humanRunRef(entry.package_id).text}
                      </span>
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
          </>
          ) : null}
        </section>

        <section
          data-testid="inspector-card-background"
          aria-label={t("shell.cards.background.title")}
        >
          <RailHead
            testId={
              activeTasks.length === 0 ? undefined : "rail-toggle-background"
            }
            icon="play"
            title={t("shell.cards.background.title")}
            value={
              activeTasks.length === 0 ? (
                <>&mdash;</>
              ) : (
                <span data-testid="background-count">
                  {formatNumber(activeTasks.length)}
                </span>
              )
            }
            expanded={backgroundCardOpen}
            onToggle={() => onBackgroundToggle(!backgroundCardOpen)}
            staticRow={activeTasks.length === 0}
          />
          {backgroundCardOpen && activeTasks.length > 0 ? (
          <>
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
          </>
          ) : null}
        </section>

        <section
          data-testid="inspector-card-watcher"
          aria-label={t("shell.cards.watcher.title")}
        >
          <RailHead
            testId={
              projectId === null || watcherFailed || watcherStatus === null
                ? undefined
                : "rail-toggle-watcher"
            }
            icon="watch"
            title={t("shell.cards.watcher.title")}
            value={
              watcherStatus === null || watcherFailed ? (
                <>&mdash;</>
              ) : watcherStatus.integrity_ok ? (
                t("shell.cards.watcher.online")
              ) : (
                t("shell.cards.watcher.offline")
              )
            }
            expanded={watcherOpen}
            onToggle={() => onWatcherToggle(!watcherOpen)}
            staticRow={
              projectId === null || watcherFailed || watcherStatus === null
            }
          />
          {watcherOpen &&
          !(projectId === null || watcherFailed || watcherStatus === null) ? (
          <>
          {projectId === null ||
          watcherFailed ||
          watcherStatus === null ? (
            <p data-testid="watcher-empty">{t("empty.generic")}</p>
          ) : (
            <>
              {/* FXFACTS F10: the open body is a dl holding only figures
                  the one-line summary lacks. */}
              <dl data-testid="watcher-facts">
              <div data-testid="watcher-state">
                <dt>{t("shell.cards.watcher.state")}</dt>
                <dd>
                {watcherStatus.integrity_ok
                  ? t("shell.cards.watcher.ok")
                  : t("shell.cards.watcher.failed")}
                </dd>
              </div>
              <div data-testid="watcher-watches">
                <dt>{t("shell.cards.watcher.watches")}</dt>
                <dd>
                {typeof watcherStatus.watched_runs === "number"
                  ? `${formatNumber(watcherStatus.watched_runs)} ${pluralUnit("shell.cards.watcher.runs", watcherStatus.watched_runs)}`
                  : t("watcher.tab.notKnown")}{" · "}
                {typeof watcherStatus.watched_agents === "number"
                  ? `${formatNumber(watcherStatus.watched_agents)} ${pluralUnit("shell.cards.watcher.agents", watcherStatus.watched_agents)}`
                  : t("watcher.tab.notKnown")}
                </dd>
              </div>
              <div data-testid="watcher-checks">
                <dt>{t("shell.cards.watcher.checks")}</dt>
                <dd>
                {typeof watcherStatus.checks_done === "number"
                  ? formatNumber(watcherStatus.checks_done)
                  : t("watcher.tab.notKnown")}{" "}
                · {t("shell.cards.watcher.alerts")}{": "}
                {typeof watcherStatus.alerts_raised === "number"
                  ? formatNumber(watcherStatus.alerts_raised)
                  : t("watcher.tab.notKnown")}{" "}
                · {t("shell.cards.watcher.lastCheck")}{": "}
                {watcherStatus.last_check_at
                  ? formatScreenTime(watcherStatus.last_check_at)
                  : t("watcher.tab.noChecksYet")}
                </dd>
              </div>
              {/* FXFACTS F13: model names the served answering model with
                  a link to where it is set; check minutes read the same
                  stored settings as the Watcher tab inputs. */}
              <div data-testid="watcher-model">
                <dt>{t("watcher.tab.model")}</dt>
                <dd>
                {typeof watcherStatus.watcher_calls === "number" &&
                watcherStatus.watcher_calls > 0 &&
                typeof watcherStatus.watcher_model === "string" &&
                watcherStatus.watcher_model !== ""
                  ? watcherStatus.watcher_model
                  : t("watcher.tab.notUsedYet")}
                {" \u00b7 "}
                {t("shell.cards.watcher.calls")}{": "}
                {typeof watcherStatus.watcher_calls === "number"
                  ? formatNumber(watcherStatus.watcher_calls)
                  : t("watcher.tab.notKnown")}{" "}
                ·{" "}
                {typeof watcherStatus.watcher_tokens === "number"
                  ? formatNumber(watcherStatus.watcher_tokens)
                  : t("watcher.tab.notKnown")}{" "}
                tokens
                {" · "}
                <Link
                  data-testid="watcher-model-settings"
                  to="/watcher"
                  className="fx-why-quiet"
                >
                  {t("watcher.tab.settings")}
                </Link>
                </dd>
              </div>
              <div data-testid="rail-watcher-minutes">
                <dt>{t("watcher.tab.minutes")}</dt>
                <dd>
                  {RULE_CARDS.map((card) => (
                    <span
                      key={card.cardId}
                      data-testid={`rail-watcher-minutes-${card.cardId}`}
                    >
                      {t(`watcher.tab.area.${card.area}`)}:{" "}
                      {t("watcher.tab.minutesValue", {
                        count: formatNumber(
                          loadCardHangMinutes(card.cardId, projectId),
                        ),
                      })}
                      {" · "}
                    </span>
                  ))}
                </dd>
              </div>
              {/* FXTABS T9: the last action reads as plain words plus the
                  local time; the raw journal id rides the tooltip only. */}
              <div
                data-testid="watcher-action"
                title={watcherActionId === DASH ? undefined : watcherActionId}
              >
                <dt>{t("shell.cards.team.lastAction")}</dt>
                <dd>
                {describeLastAction(watcherStatus.last_action)}
                {watcherActionAt === "" ? null : (
                  <>
                    {" \u00b7 "}
                    {formatScreenTime(watcherActionAt)}
                  </>
                )}
                </dd>
              </div>
              </dl>
              {/* FXFACTS F13: the last journal rows in the F6a form. */}
              <WatcherJournalList
                entries={(journal ?? []).slice(-3)}
                initialLimit={3}
                showMore={false}
              />
              <Link data-testid="watcher-open" to="/watcher">
                {t("shell.cards.watcher.open")}
              </Link>
            </>
          )}
          </>
          ) : null}
        </section>

        {/* FXTABS J7: metric cards with data render first (flex order);
            empty ones collapse to one line. Team above never collapses.
            FXFACTS F10: Tokens, Tests, Providers, Local LLM and Apps live
            inside one quiet More disclosure at the bottom, closed by
            default; their cards and testids exist when it is open. */}
        <div style={{ order: budgetHasData ? 0 : 1 }}>
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
          <RailHead
            testId={budget === null ? undefined : "kit-toggle-fx-budget"}
            icon="settings"
            title={t("shell.cards.budget.title")}
            hint={t("shell.cards.budget.subtitle")}
            value={
              budget === null ? <>&mdash;</> : budgetTotal
            }
            expanded={budgetOpen}
            onToggle={() => onBudgetToggle(!budgetOpen)}
            lineTestId={budgetOpen ? undefined : "kit-collapsed-line"}
            staticRow={budget === null}
          />
          {budgetOpen ? (
            budget === null ? (
              <p data-testid="budget-unknown" className="fx-quiet-line">
                {unknown}
              </p>
            ) : (
              <>
              <p data-testid="kit-sub-fx-budget">
                {t("shell.cards.budget.subtitle")}
              </p>
              {/* FXFACTS F10: the open body is a dl holding only figures
                  the one-line summary lacks. */}
              <dl
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
                <div data-testid="budget-row-limit">
                  <dt>{t("projectView.cost.limit")}</dt>
                  <dd>{limitText}</dd>
                </div>
                <div data-testid="budget-row-spent">
                  <dt>{t("shell.cards.budget.spent")}</dt>
                  <dd>{spentText}</dd>
                </div>
                <div data-testid="budget-row-reserved">
                  <dt>{t("shell.cards.budget.reserved")}</dt>
                  <dd>{reservedText}</dd>
                </div>
                <div data-testid="budget-row-remaining">
                  <dt>{t("shell.cards.budget.remaining")}</dt>
                  <dd>{remainingText}</dd>
                </div>
              </dl>
              </>
            )
          ) : null}
        </section>
        </div>
        <div data-testid="rail-more">
        <RailHead
          testId="rail-more-toggle"
          icon="add"
          title={t("shell.cards.more.title")}
          value={`${formatNumber(moreDataCount)} / 5`}
          expanded={moreOpen}
          onToggle={() => onMoreToggle(!moreOpen)}
        />
        {moreOpen ? (
        <>
        <div style={{ order: tokensHasData ? 0 : 1 }}>
        {tokensKnown ? (
          <>
            <MetricCard
              cardId="fx-tokens"
              icon="chart"
              titleKey="shell.cards.tokens.title"
              subtitleKey="shell.cards.tokens.subtitle"
              totalKey="shell.cards.tokens.total"
              totalText={formatNumber(tokenTotal)}
              hasData={tokensHasData}
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
              collapsed={tokensCollapsed || !tokensHasData}
              onToggle={onTokensToggle}
            />
            {tokensOpen && !runLive && modelSlices.length > 0 ? (
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
            ) : null}
            {/* FXTELEM: idle totals are named: the last run's tokens and
                this project's runs-key sum. The per-model rows above add up
                to the project-scoped telemetry total. */}
            {runLive || !tokensOpen ? null : (
              <dl data-testid="tokens-facts">
                {lastRunTokens !== null ? (
                  <div data-testid="tokens-last-run">
                    <dt>{t("shell.cards.context.lastRun")}</dt>
                    <dd>{formatNumber(lastRunTokens)}</dd>
                  </div>
                ) : null}
                {projectTotal !== null && projectTotal !== lastRunTokens ? (
                  <div data-testid="tokens-project">
                    <dt>{t("shell.cards.context.projectTotal")}</dt>
                    <dd>{formatNumber(projectTotal)}</dd>
                  </div>
                ) : null}
                {chatDiffers ? (
                  <div data-testid="tokens-chat">
                    <dt>{t("shell.cards.context.chatAnswers")}</dt>
                    <dd>{formatNumber(projectRunsTotal ?? 0)}</dd>
                  </div>
                ) : null}
              </dl>
            )}
          </>
        ) : (
          <>
            <MetricCard
              cardId="fx-tokens"
              icon="chart"
              titleKey="shell.cards.tokens.title"
              subtitleKey="shell.cards.tokens.subtitle"
              totalKey="shell.cards.tokens.total"
              totalText={unknown}
              segments={[]}
              collapsed={tokensCollapsed || !tokensHasData}
              onToggle={onTokensToggle}
              hasData={false}
            />
            <p data-testid="tokens-unknown" className="fx-quiet-line">
              {t("shell.cards.context.noUsage")}
            </p>
          </>
        )}
        </div>
        <div style={{ order: testsHasData ? 0 : 1 }}>
        <MetricCard
          cardId="fx-tests"
          icon="file"
          titleKey="shell.cards.tests.title"
          subtitleKey="shell.cards.tests.subtitle"
          totalKey="shell.cards.tests.total"
          totalText={testsTotal}
          closedValue={t("shell.cards.tests.planOne")}
          segments={[]}
          collapsed={testsCollapsed || !testsHasData}
          onToggle={onTestsToggle}
          hasData={testsHasData}
        />
        </div>
        <div style={{ order: providersHasData ? 0 : 1 }}>
        <MetricCard
          cardId="fx-providers"
          titleKey="shell.cards.providers.title"
          subtitleKey="shell.cards.providers.subtitle"
          totalKey="shell.cards.providers.total"
          totalText={providersTotal}
          segments={[]}
          collapsed={providersCollapsed || !providersHasData}
          onToggle={onProvidersToggle}
          icon="play"
          hasData={providersHasData}
        />
        </div>
        <div style={{ order: localAiHasData ? 0 : 1 }}>
        <MetricCard
          cardId="fx-localai"
          titleKey="shell.cards.localai.title"
          subtitleKey="shell.cards.localai.subtitle"
          totalKey="shell.cards.localai.total"
          totalText={localAiTotal}
          segments={[]}
          collapsed={localAiCollapsed || !localAiHasData}
          onToggle={onLocalAiToggle}
          icon="mic"
          hasData={localAiHasData}
        />
        </div>
        <div style={{ order: appsHasData ? 0 : 1 }}>
        <MetricCard
          cardId="fx-apps"
          titleKey="shell.cards.apps.title"
          subtitleKey="shell.cards.apps.subtitle"
          totalKey="shell.cards.apps.total"
          totalText={appsTotal}
          segments={[]}
          collapsed={appsCollapsed || !appsHasData}
          onToggle={onAppsToggle}
          icon="folder"
          hasData={appsHasData}
        />
        </div>
        </>
        ) : null}
        </div>
      </div>
    </aside>
  );
}
