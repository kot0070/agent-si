// FXLAYOUT short navigation: exactly four entries. New task opens the
// chat empty composer, Projects opens the project list, Results opens the
// current project reports view (or the project list with a one-line hint
// when no project is selected), Settings opens the settings index.

import type { ReactElement } from "react";
import { NavLink } from "react-router-dom";
import type { SidebarProps } from "../app/iface";
import { useCurrentProject } from "../app/ApiClientProvider";
import { t } from "../locale/index";

// FXDESIGN3 S5: the rail exposes the active entry through NavLink's
// aria-current="page" plus the fx-nav-active token style in shell.css.
function railClass({ isActive }: { isActive: boolean }): string | undefined {
  return isActive ? "fx-nav-active" : undefined;
}

export function Sidebar(props: SidebarProps): ReactElement {
  const current = useCurrentProject();
  const active = props.projectId ?? current.projectId;
  const resultsTo =
    active === null ? "/projects" : `/projects/${active}/reports`;

  return (
    <nav data-testid="sidebar" aria-label={t("shell.sidebar.projects")}>
      <NavLink data-testid="menu-new-task" to="/" end className={railClass}>
        {t("tasks.creator.title")}
      </NavLink>
      <span data-testid="menu-new-task-purpose">
        {t("tasks.creator.subtitle")}
      </span>
      <NavLink
        data-testid="menu-projects"
        to="/projects"
        end
        className={railClass}
      >
        {t("shell.sidebar.projects")}
      </NavLink>
      <span data-testid="menu-projects-purpose">
        {t("projects.list.subtitle")}
      </span>
      <NavLink
        data-testid="menu-results"
        to={resultsTo}
        end
        className={railClass}
      >
        {t("projects.reports.title")}
      </NavLink>
      <span data-testid="menu-results-purpose">
        {t("projects.reports.subtitle")}
      </span>
      {active === null ? (
        <span data-testid="menu-results-hint">
          {t("shell.sidebar.resultsHint")}
        </span>
      ) : null}
      <NavLink
        data-testid="menu-settings"
        to="/settings"
        className={railClass}
      >
        {t("shell.sidebar.settings")}
      </NavLink>
      <span data-testid="menu-settings-purpose">
        {t("settings.index.subtitle")}
      </span>
    </nav>
  );
}
