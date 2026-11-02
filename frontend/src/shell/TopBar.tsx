// kit BUILD_PLAN:1479 M-R-UX-1 one top bar; pairing as top strip, never overlay chrome
// Lane A top bar: project switcher, always-on Watcher chip, Stop-all
// signal and language switch. Language changes flow through the frozen
// locale surface: setLocale updates the module plus persistence, then a
// window event carries the new locale to App for a full re-render.

import { Link, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import type { PartRow, ProjectRecord } from "../api/iface";
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
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  setLocale,
  t,
} from "../locale/index";
import type { SupportedLocale } from "../locale/index";
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
  const [locale, setLocaleUi] = useState<SupportedLocale>(readStoredLocale);
  const [projects, setProjects] = useState<ProjectRecord[] | null>(null);
  const [stopArmed, setStopArmed] = useState(false);
  const [stopText, setStopText] = useState<string | null>(null);
  const [liveRows, setLiveRows] = useState<PartRow[] | null>(null);
  const [connected, setConnected] = useState<string[] | null>(null);

  // W1: apply the stored locale to the locale module at boot so the
  // chrome matches the language select on first paint.
  useEffect(() => {
    setLocale(readStoredLocale());
  }, []);

  // W2: Escape disarms the inline stop confirm; any route change disarms
  // it too so the armed state never persists across screens.
  useEffect(() => {
    setStopArmed(false);
  }, [location.pathname]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setStopArmed(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  useEffect(() => {
    let alive = true;
    client.listProjects().then(
      (rows) => {
        if (alive) {
          setProjects(rows);
        }
      },
      () => {
        if (alive) {
          setProjects([]);
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [client]);

  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      try {
        const next = await client.listAgentsLive();
        if (alive) {
          setLiveRows(next);
        }
      } catch {
        if (alive) {
          setLiveRows([]);
        }
      }
    }
    void load();
    const timer = setInterval(() => {
      void load();
    }, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [client]);

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
  // FXRC1FIX P4: the mount list predates a first-message project, so the
  // select would show "Select a project" for the new id. Refetch once per
  // unknown id; the fresh options then show the project name.
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
    let alive = true;
    client.listProjects().then(
      (rows) => {
        if (alive) {
          setProjects(rows);
        }
      },
      () => {
        if (alive) {
          setProjects([]);
        }
      },
    );
    return () => {
      alive = false;
    };
  }, [client, effective, effectiveMissing]);

  // Top placement badge truth: the placement of the current live rows;
  // with none running, the default route of the connected providers;
  // hidden when neither is sourced. Never a guess.
  function topPlacement(): Placement | null {
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
  }

  const badge = topPlacement();

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
    if (!stopArmed) {
      setStopArmed(true);
      return;
    }
    setStopArmed(false);
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
        setStopText(
          t("shell.topbar.stop_result", { status: `Stopped ${count}` }),
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
      <span data-testid="topbar-brand">{t("shell.topbar.brand")}</span>
      <button
        type="button"
        data-testid="topbar-panels"
        className="fx-panels-btn"
        aria-label={t("shell.topbar.panels")}
        onClick={togglePanels}
      >
        {t("shell.topbar.panels")}
      </button>
      <span data-testid="k07open10-shell" aria-hidden="true" />
      <div data-testid="pairing-strip">
        <span data-testid="pairing-label">
          <Link data-testid="topbar-watcher" to="/watcher">
            {t("shell.topbar.watcher")}
          </Link>
        </span>{" "}
        {badge === null ? (
          <span data-testid="pairing-badge" hidden />
        ) : (
          <span data-testid="pairing-badge">{t(placementKey(badge))}</span>
        )}
      </div>
      <label>
        {t("shell.topbar.project")}
        <select
          data-testid="topbar-project"
          value={effective ?? ""}
          onChange={(event) => {
            current.select(event.target.value);
          }}
        >
          {effective === null ? (
            <option value="">{t("shell.topbar.projectPlaceholder")}</option>
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
              {t("shell.topbar.projectPlaceholder")}
            </option>
          ) : null}
        </select>
      </label>
      <button
        type="button"
        data-testid="topbar-stop-all"
        onClick={() => {
          void stopAll();
        }}
      >
        {stopArmed ? t("shell.closing.confirm") : t("shell.topbar.stop_all")}
      </button>
      {stopText === null ? null : (
        <>
          <span data-testid="stop-all-result">{stopText}</span>
          <button
            type="button"
            data-testid="stop-all-clear"
            className="fx-btn-quiet"
            aria-label={t("shell.topbar.stop_clear")}
            onClick={() => {
              setStopText(null);
            }}
          >
            {t("shell.topbar.stop_clear")}
          </button>
        </>
      )}
      <label>
        {t("shell.topbar.language")}
        <select
          data-testid="topbar-language"
          aria-label={t("shell.topbar.language")}
          value={locale}
          onChange={(event) => {
            changeLocale(event.target.value === "uk" ? "uk" : "en");
          }}
        >
          <option value="en">en</option>
          <option value="uk">uk</option>
        </select>
      </label>
      <ThemeToggle />
    </header>
  );
}
