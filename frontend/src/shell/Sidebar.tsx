// FXLAYOUT short navigation: exactly four entries. New task opens the
// chat empty composer, Projects opens the project list, Results opens the
// current project reports view (or the project list with a one-line hint
// when no project is selected), Settings opens the settings index.

import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import type { SidebarProps } from "../app/iface";
import { useCurrentProject } from "../app/ApiClientProvider";
import { t } from "../locale/index";

export function Sidebar(props: SidebarProps): ReactElement {
  const current = useCurrentProject();
  const active = props.projectId ?? current.projectId;
  const resultsTo =
    active === null ? "/projects" : `/projects/${active}/reports`;

  return (
    <nav data-testid="sidebar" aria-label={t("shell.sidebar.projects")}>
      <Link data-testid="menu-new-task" to="/">
        {t("tasks.creator.title")}
      </Link>
      <Link data-testid="menu-projects" to="/projects">
        {t("shell.sidebar.projects")}
      </Link>
      <Link data-testid="menu-results" to={resultsTo}>
        {t("projects.reports.title")}
      </Link>
      {active === null ? (
        <span data-testid="menu-results-hint">
          {t("shell.sidebar.resultsHint")}
        </span>
      ) : null}
      <Link data-testid="menu-settings" to="/settings">
        {t("shell.sidebar.settings")}
      </Link>
    </nav>
  );
}
