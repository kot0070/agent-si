// kit BUILD_PLAN:1479 M-R-UX-1 one top bar; pairing as top strip, never overlay chrome
// Lane A top bar: project switcher, always-on Watcher chip, Stop-all
// signal and language switch. Language changes flow through the frozen
// locale surface: setLocale updates the module plus persistence, then a
// window event carries the new locale to App for a full re-render.

import { useLocation, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";
import type { PartRow } from "../api/iface";
import { ApiError, requestResponse } from "../api/errors";
import type { TopBarProps } from "../app/iface";
import { useApiClient, useCurrentProject } from "../app/ApiClientProvider";
import {
  placementForProviderId,
  placementForRow,
  placementKey,
} from "../agents/agentsApi";
import type { Placement } from "../agents/agentsApi";
import { listConnectedProviders } from "../settings/ProvidersPage/connectApi";
import { useLiveRows } from "../agents/liveStore";
import { useProjectList } from "../projects/projectList";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  formatNumber,
  pluralUnit,
  setLocale,
  t,
} from "../locale/index";
import type { SupportedLocale } from "../locale/index";
import {
  INSPECTOR_TOGGLE_EVENT,
  inspectorEventOpen,
  readInspectorOpen,
  toggleInspector,
} from "./inspectorDrawer";
import { ThemeToggle } from "./ThemeToggle";

export const TOPBAR_LOCALE_EVENT = "agentsi:locale-changed";

export const TOPBAR_STOP_EVENT = "agentsi:stop-all";

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

export const PANELS_TOGGLE_EVENT = "agentsi:toggle-panels";

export function togglePanels(): void {
  try {
    const shell = document.querySelector('[data-testid="app-shell"]');
    if (shell !== null) {
      shell.classList.toggle("fx-panels-open");
    }
    window.dispatchEvent(new Event(PANELS_TOGGLE_EVENT));
  } catch {
    // No document in this probe: the panels stay as rendered.
  }
}

export function TopBar(props: TopBarProps): ReactElement {
  const client = useApiClient();
  const current = useCurrentProject();
  const location = useLocation();
  const navigate = useNavigate();
  const [locale, setLocaleUi] = useState<SupportedLocale>(readStoredLocale);
  // J8: the one project-name source is the shared project list (the same
  // store Sidebar and ProjectsPage read); the top bar keeps no own copy.
  const { projects, refresh: refreshProjects } = useProjectList();
  // FXFACTS F12: one click stops at once, no confirmation dialog. The
  // quiet status line names what was stopped and fades on its own.
  const [stopText, setStopText] = useState<string | null>(null);
  // FXFACTS F8: drawer toggle mirrors the shell class through the shared
  // drawer event, so aria-expanded never lies.
  const [inspectorOpen, setInspectorOpen] = useState<boolean>(() =>
    readInspectorOpen(),
  );
  // FXDESIGN8: the shared agents-live store owns the single poller;
  // the top bar only subscribes.
  const live = useLiveRows(client);
  const liveRows = live.rows;
  const [connected, setConnected] = useState<string[] | null>(null);

  // W1: apply the stored locale to the locale module at boot so the
  // chrome matches the language select on first paint.
  useEffect(() => {
    setLocale(readStoredLocale());
  }, []);

  useEffect(() => {
    function onInspectorToggle(event: Event): void {
      setInspectorOpen(inspectorEventOpen(event));
    }
    window.addEventListener(INSPECTOR_TOGGLE_EVENT, onInspectorToggle);
    return () => {
      window.removeEventListener(INSPECTOR_TOGGLE_EVENT, onInspectorToggle);
    };
  }, []);

  // FXFACTS F12/F15: the quiet stop status fades on its own; no extra
  // button. The timer restarts with every new status.
  const stopFadeRef = useRef<number | null>(null);
  useEffect(() => {
    if (stopText === null) {
      return;
    }
    if (stopFadeRef.current !== null) {
      window.clearTimeout(stopFadeRef.current);
    }
    stopFadeRef.current = window.setTimeout(() => {
      setStopText(null);
    }, 6000);
    return () => {
      if (stopFadeRef.current !== null) {
        window.clearTimeout(stopFadeRef.current);
        stopFadeRef.current = null;
      }
    };
  }, [stopText]);

  // W2: any route change clears the stop status line.
  useEffect(() => {
    setStopText(null);
  }, [location.pathname]);

  useEffect(() => {
    let alive = true;
    void listConnectedProviders().then((ids) => {
      if (alive) {
        setConnected(ids);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  const effective = props.projectId ?? current.projectId;
  const options = projects ?? [];
  // J8: an empty served list is "No project yet" in the top bar, never
  // the "Select a project" placeholder (kept for loading and choice).
  const emptyNoProject =
    effective === null && projects !== null && projects.length === 0;
  const nullOptionText = emptyNoProject
    ? t("shell.topbar.noProject")
    : t("shell.topbar.projectPlaceholder");
  // U11: the truncated project value keeps its full name as a tooltip.
  const effectiveName =
    effective === null
      ? nullOptionText
      : (options.find((project) => project.project_id === effective)?.name ??
        nullOptionText);
  // FXRC1FIX P4: the mount list predates a first-message project, so the
  // select would show the placeholder for the new id. Refresh the shared
  // list once per unknown id; the fresh options then show the name.
  const refetchedRef = useRef<string | null>(null);
  const effectiveMissing =
    effective !== null &&
    projects !== null &&
    !options.some((project) => project.project_id === effective);
  useEffect(() => {
    if (!effectiveMissing || effective === null) {
      return undefined;
    }
    if (refetchedRef.current === effective) {
      return undefined;
    }
    refetchedRef.current = effective;
    refreshProjects();
    return undefined;
  }, [effective, effectiveMissing, refreshProjects]);

  // FXLAST (advisor decision on FXREL-5 vs FXTABS T10): quiet style
  // while nothing runs, red only with a live run; the button is
  // disabled with a reason tooltip when idle, enabled while a run is
  // active.
  const hasLiveRun =
    (liveRows ?? []).some((row) => row.status === "RUNNING") ||
    liveRows === null;
  // Top placement badge truth: the placement of the current live rows;
  // with none running, the default route of the connected providers;
  // hidden when neither is sourced. Never a guess. Memoised: the shared
  // tick replaces state only on change, and this skips the rescan anyway.
  const badge = useMemo<Placement | null>(() => {
    const running = (liveRows ?? []).filter(
      (row) => row.status === "RUNNING",
    );
    if (running.length > 0) {
      const known = new Set<Placement>();
      for (const row of running) {
        const placement = placementForRow(row);
        if (placement !== "UNKNOWN") {
          known.add(placement);
        }
      }
      if (known.size === 0) {
        return null;
      }
      if (known.size === 1) {
        return [...known][0] ?? null;
      }
      return "SPLIT";
    }
    if (connected === null || liveRows === null) {
      return null;
    }
    if (connected.length === 0) {
      return null;
    }
    const route = new Set<Placement>();
    for (const id of connected) {
      route.add(placementForProviderId(id));
    }
    if (route.size === 1) {
      return [...route][0] ?? null;
    }
    return "SPLIT";
  }, [liveRows, connected]);

  function changeLocale(next: SupportedLocale): void {
    if (next === locale) {
      return;
    }
    setLocale(next);
    setLocaleUi(next);
    window.dispatchEvent(
      new CustomEvent<SupportedLocale>(TOPBAR_LOCALE_EVENT, { detail: next }),
    );
  }

  async function stopAll(): Promise<void> {
    window.dispatchEvent(new Event(TOPBAR_STOP_EVENT));
    // The stop button acts as the user, in both branches.
    const body =
      effective === null
        ? { actor: "user" }
        : { project_id: effective, actor: "user" };
    try {
      const response = await requestResponse("/api/v1/stop-all", {
        method: "POST",
        kind: "write",
        body,
      });
      let receipt: {
        accepted?: unknown;
        stopped_count?: unknown;
        reason?: unknown;
      } = {};
      try {
        receipt = (await response.json()) as typeof receipt;
      } catch {
        receipt = {};
      }
      if (receipt.accepted === true) {
        const count =
          typeof receipt.stopped_count === "number"
            ? receipt.stopped_count
            : 0;
        // FXFACTS F12/F15: one quiet locale status line, no extra button.
        setStopText(
          t("shell.topbar.stoppedLine", {
            count: formatNumber(count),
            unit: pluralUnit("shell.topbar.stoppedAgents", count),
          }),
        );
      } else {
        const reason =
          typeof receipt.reason === "string" && receipt.reason !== ""
            ? receipt.reason
            : "stop refused";
        setStopText(
          t("shell.topbar.stop_result", { status: `Refused: ${reason}` }),
        );
      }
    } catch (error) {
      if (error instanceof ApiError) {
        setStopText(
          t("shell.topbar.stop_result", {
            status: `Refused: ${error.code}`,
          }),
        );
      } else {
        setStopText(
          t("shell.topbar.stop_result", { status: "Refused: stop failed" }),
        );
      }
    }
  }

  return (
    <header data-testid="topbar" className="fx-topbar">
      <span data-testid="topbar-brand">
        <svg
          width="16"
          height="16"
          viewBox="0 0 256 256"
          aria-hidden="true"
          focusable="false"
          style={{
            display: "inline-block",
            width: 16,
            height: 16,
            flex: "none",
            verticalAlign: "-3px",
            marginRight: 6,
          }}
        >
          <rect x="8" y="8" width="240" height="240" rx="54" fill="#161b22" />
          <rect x="46" y="46" width="164" height="164" rx="38" fill="#0d1117" />
          <g
            fill="none"
            stroke="#2f81f7"
            strokeWidth="24"
            strokeLinecap="round"
          >
            <path d="M 148 62 C 120 62 98 76 98 102 C 98 130 148 120 148 148 C 148 170 128 182 102 182 C 92 182 84 178 78 172" />
            <path d="M 178 62 L 178 182" />
          </g>
          <rect x="104" y="196" width="48" height="10" rx="5" fill="#2f81f7" />
        </svg>
        {t("shell.topbar.brand")}
      </span>
      <button
        type="button"
        data-testid="topbar-panels"
        className="fx-panels-btn"
        aria-label={t("shell.topbar.panels")}
        onClick={togglePanels}
      >
        {t("shell.topbar.panels")}
      </button>
      <button
        type="button"
        data-testid="inspector-toggle"
        className="fx-inspector-btn"
        aria-label={t("shell.topbar.inspector")}
        aria-expanded={inspectorOpen}
        aria-controls="inspector"
        onClick={toggleInspector}
      >
        {t("shell.topbar.inspector")}
      </button>
      <span data-testid="k07open10-shell" aria-hidden="true" />
      {/* FXDESIGN6: the project name reads as the ref title dropdown. The
          visible label text is visually hidden (aria-label carries it) so
          long uk names never wrap the strip. */}
      <label className="fx-topbar-project">
        <span className="fx-vh">{t("shell.topbar.project")}</span>
        <select
          data-testid="topbar-project"
          className="fx-topbar-control"
          /* FXDESIGN5 S3/S7: explicit accessible name on the project
             dropdown (the visible label text stays unchanged). */
          aria-label={t("shell.topbar.project")}
          title={effectiveName}
          value={effective ?? ""}
          onChange={(event) => {
            // FXCHATHIST Part 2 (H3): switching projects opens that
            // project's chat with its history (the root chat route
            // renders the selected project).
            if (event.target.value !== "") {
              current.select(event.target.value);
              navigate("/");
            }
          }}
        >
          {effective === null ? (
            <option value="">{nullOptionText}</option>
          ) : null}
          {options.map((project) => (
            <option
              key={project.project_id}
              value={project.project_id}
              title={project.project_id}
            >
              {project.name}
            </option>
          ))}
          {effective !== null &&
          !options.some((project) => project.project_id === effective) ? (
            <option value={effective} title={effective}>
              {nullOptionText}
            </option>
          ) : null}
        </select>
      </label>
      <div data-testid="topbar-right" className="fx-topbar-right">
        <div data-testid="pairing-strip">
          {/* FXFACTS F15: the watcher word lives in the rail Watcher card
              only; the top bar keeps the placement badge. */}
          {badge === null ? (
            <span data-testid="pairing-badge" hidden />
          ) : (
            <span data-testid="pairing-badge">{t(placementKey(badge))}</span>
          )}
        </div>
        <button
          type="button"
          data-testid="topbar-stop-all"
          className={hasLiveRun ? "fx-stop-danger" : "fx-btn-quiet"}
          disabled={!hasLiveRun}
          title={
            hasLiveRun ? undefined : t("shell.topbar.stop_all_idle")
          }
          onClick={() => {
            void stopAll();
          }}
        >
          {t("shell.topbar.stop_all")}
        </button>
      {stopText === null ? null : (
        <span data-testid="stop-all-result" className="fx-fade-note">
          {stopText}
        </span>
      )}
        <label className="fx-topbar-language">
          <span className="fx-vh">{t("shell.topbar.language")}</span>
          <select
            data-testid="topbar-language"
            className="fx-topbar-control"
            aria-label={t("shell.topbar.language")}
            title={locale}
            value={locale}
            onChange={(event) => {
              changeLocale(event.target.value === "uk" ? "uk" : "en");
            }}
          >
            <option value="en">{t("shell.topbar.langEn")}</option>
            <option value="uk">{t("shell.topbar.langUk")}</option>
          </select>
        </label>
        <ThemeToggle />
      </div>
    </header>
  );
}
