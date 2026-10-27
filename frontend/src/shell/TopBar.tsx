// Lane A top bar: project switcher, always-on Watcher chip, Stop-all
// signal and language switch. Language changes flow through the frozen
// locale surface: setLocale updates the module plus persistence, then a
// window event carries the new locale to App for a full re-render.

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import type { ProjectRecord } from "../api/iface";
import type { TopBarProps } from "../app/iface";
import { useApiClient, useCurrentProject } from "../app/ApiClientProvider";
import {
  DEFAULT_LOCALE,
  LOCALE_STORAGE_KEY,
  setLocale,
  t,
} from "../locale/index";
import type { SupportedLocale } from "../locale/index";

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

export function TopBar(props: TopBarProps): ReactElement {
  const client = useApiClient();
  const current = useCurrentProject();
  const [locale, setLocaleUi] = useState<SupportedLocale>(readStoredLocale);
  const [projects, setProjects] = useState<ProjectRecord[] | null>(null);

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

  const effective = props.projectId ?? current.projectId;
  const options = projects ?? [];

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

  function stopAll(): void {
    window.dispatchEvent(new Event(TOPBAR_STOP_EVENT));
  }

  return (
    <header data-testid="topbar">
      <div data-testid="pairing-strip">
        <span>{t("shell.topbar.watcher")}</span>
        <span>
          {effective === null
            ? t("agents.badge.cloud")
            : t("agents.badge.local")}
        </span>
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
          {options.map((project) => (
            <option key={project.project_id} value={project.project_id}>
              {project.name}
            </option>
          ))}
          {effective !== null &&
          !options.some((project) => project.project_id === effective) ? (
            <option value={effective}>{effective}</option>
          ) : null}
        </select>
      </label>
      <span data-testid="topbar-watcher">{t("shell.topbar.watcher")}</span>
      <button type="button" data-testid="topbar-stop-all" onClick={stopAll}>
        {t("shell.topbar.stop_all")}
      </button>
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
    </header>
  );
}
