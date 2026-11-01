// Lane A short navigation: chat-first entries plus project areas. The
// sidebar links to screens only; per-part rows stay inside the agents and
// project views and never appear here.

import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import type { SidebarProps } from "../app/iface";
import { useCurrentProject } from "../app/ApiClientProvider";
import { t } from "../locale/index";

export function Sidebar(props: SidebarProps): ReactElement {
  const current = useCurrentProject();
  const active = props.projectId ?? current.projectId;
  const tasksTo = active === null ? "/projects" : `/projects/${active}/tasks`;
  const resultsTo =
    active === null ? "/projects" : `/projects/${active}/reports`;

  return (
    <nav data-testid="sidebar" aria-label={t("shell.sidebar.projects")}>
      <Link data-testid="menu-chat" to="/">
        {t("shell.sidebar.chat")}
      </Link>
      <Link data-testid="menu-agents-live" to="/agents/live">
        {t("shell.sidebar.agents_live")}
      </Link>
      <Link data-testid="menu-projects" to="/projects">
        {t("shell.sidebar.projects")}
      </Link>
      <Link data-testid="menu-tasks" to={tasksTo}>
        {t("shell.sidebar.tasks")}
      </Link>
      <Link data-testid="menu-results" to={resultsTo}>
        {t("projects.reports.title")}
      </Link>
      <Link data-testid="menu-watcher" to="/watcher">
        {t("shell.topbar.watcher")}
      </Link>
      <Link data-testid="menu-settings" to="/settings">
        {t("settings.general.title")}
      </Link>
    </nav>
  );
}
