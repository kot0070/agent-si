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
      <Link data-testid="menu-new-task" to={tasksTo}>
        {t("tasks.creator.title")}
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
      <Link data-testid="menu-settings" to="/settings">
        {t("settings.general.title")}
      </Link>
      <Link data-testid="menu-k07next-locale-coverage" to="/k07next/locale-coverage">
        {t("settings.general.title")}
      </Link>
      <Link data-testid="menu-k07next-telemetry-themes" to="/k07next/telemetry-themes">
        {t("settings.appearance.title")}
      </Link>
      <Link data-testid="menu-k07next2-bench-check" to="/k07next2/bench-check">
        {t("settings.localbench.title")}
      </Link>
      <Link data-testid="menu-k07next2-telemetry" to="/k07next2/telemetry">
        {t("projects.ai_usage.title")}
      </Link>
      <Link data-testid="menu-k07next3-bench-history" to="/k07next3/bench-history">
        {t("projects.runs.title")}
      </Link>
      <Link data-testid="menu-k07next3-tests-view" to="/k07next3/tests-view">
        {t("settings.localAi.title")}
      </Link>
      <Link data-testid="menu-k07next4-session-token" to="/k07next4/session-token">
        {t("chat.composer.send")}
      </Link>
      <Link data-testid="menu-k07next4-page-shell" to="/k07next4/page-shell">
        {t("shell.sidebar.projects")}
      </Link>
    </nav>
  );
}
