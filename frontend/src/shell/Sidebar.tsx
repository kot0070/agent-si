// FXLAYOUT short navigation: exactly four entries with icon + short label
// plus the project list under it (ref session list). Purposes stay in the
// DOM as each link's next sibling (fxpoint1 R2) with a title tooltip, but
// only the selected entry's sentence is visible. Project rows are buttons
// (never anchors, so the four-entry anchor rule holds); the selected row
// carries the soft fill and opens the project overview on click.

import { NavLink, useLocation, useNavigate } from "react-router-dom";
import type { ReactElement } from "react";
import type { SidebarProps } from "../app/iface";
import { useApiClient, useCurrentProject } from "../app/ApiClientProvider";
import { useProjectList } from "../projects/projectList";
import { hasChatUnseen, useUnseenVersion } from "../chat/index";
import { t } from "../locale/index";
import { Icon } from "../ui/icons";
import type { IconName } from "../ui/icons";
import { EmptyState } from "../ui/EmptyState";
import { ErrorPanel } from "../ui/ErrorPanel";
import { LoadingState } from "../ui/LoadingState";

// FXDESIGN3 S5: the rail exposes the active entry through NavLink's
// aria-current="page" plus the fx-nav-active soft-fill token in shell.css.
function railClass({ isActive }: { isActive: boolean }): string | undefined {
  return isActive ? "fx-nav-active" : undefined;
}

interface RailEntry {
  testId: string;
  purposeId: string;
  to: string;
  end: boolean;
  titleKey: string;
  purposeKey: string;
  icon: IconName;
}

export function Sidebar(props: SidebarProps): ReactElement {
  const client = useApiClient();
  const navigate = useNavigate();
  const location = useLocation();
  const current = useCurrentProject();
  const active = props.projectId ?? current.projectId;
  // FXPROJ J1: the one shared project list (refetch on create, delete
  // and route change). Null is loading, never an empty list; a failed
  // load keeps the last good rows and reports failure with a retry.
  const { projects, failure, refresh } = useProjectList();

  const resultsTo =
    active === null ? "/projects" : `/projects/${active}/reports`;

  // Mirrors the NavLink `end` matching above so the visible purpose always
  // follows the selected entry without reading the DOM during render.
  function isEntryActive(entry: RailEntry): boolean {
    if (entry.end) {
      return location.pathname === entry.to;
    }
    return location.pathname.startsWith(entry.to);
  }

  const entries: RailEntry[] = [
    {
      testId: "menu-new-task",
      purposeId: "menu-new-task-purpose",
      to: "/",
      end: true,
      titleKey: "tasks.creator.title",
      purposeKey: "tasks.creator.subtitle",
      icon: "add",
    },
    {
      testId: "menu-projects",
      purposeId: "menu-projects-purpose",
      to: "/projects",
      end: true,
      titleKey: "shell.sidebar.projects",
      purposeKey: "projects.list.subtitle",
      icon: "folder",
    },
    {
      testId: "menu-results",
      purposeId: "menu-results-purpose",
      to: resultsTo,
      end: true,
      titleKey: "projects.reports.title",
      purposeKey: "projects.reports.subtitle",
      icon: "chart",
    },
    {
      testId: "menu-settings",
      purposeId: "menu-settings-purpose",
      to: "/settings",
      end: false,
      titleKey: "shell.sidebar.settings",
      purposeKey: "settings.index.subtitle",
      icon: "settings",
    },
  ];

  function openProject(projectId: string): void {
    // FXCHATHIST Part 2 (H3): opening a project lands on its chat with
    // its history (the Chat tab), not the overview.
    current.select(projectId);
    navigate(`/projects/${projectId}/chat`);
  }

  // H4 quiet dot: re-renders rows when any slice flags unseen activity.
  const unseenTick = useUnseenVersion();
  void unseenTick;

  return (
    <nav data-testid="sidebar" aria-label={t("shell.sidebar.projects")}>
      {entries.map((entry) => (
        <span key={entry.testId} className="fx-rail-row">
          <NavLink
            data-testid={entry.testId}
            to={entry.to}
            end={entry.end}
            className={railClass}
            title={t(entry.purposeKey)}
          >
            <Icon name={entry.icon} />
            <span>{t(entry.titleKey)}</span>
          </NavLink>
          {/* FXDESIGN6: the purpose line reads on the tab's own header;
              the rail keeps it only for the selected entry. */}
          <span
            data-testid={entry.purposeId}
            className="fx-rail-purpose"
            hidden={isEntryActive(entry) ? undefined : true}
          >
            {t(entry.purposeKey)}
          </span>
        </span>
      ))}
      {active === null ? (
        <span data-testid="menu-results-hint">
          {t("shell.sidebar.resultsHint")}
        </span>
      ) : null}
      <div data-testid="sidebar-projects" className="fx-project-list">
        {projects === null ? (
          failure !== null ? (
            <ErrorPanel
              errorKey={failure.errorKey}
              code={failure.code}
              onRetry={refresh}
            />
          ) : (
            <LoadingState loadingKey="ui.loading.more" />
          )
        ) : projects.length === 0 ? (
          <div data-testid="sidebar-projects-empty">
            <EmptyState
              stateKey="projects.list.empty"
              actionKey={null}
              onAction={null}
            />
          </div>
        ) : (
          projects.map((project) => (
            <button
              key={project.project_id}
              type="button"
              data-testid={`sidebar-project-${project.project_id}`}
              className={
                project.project_id === active
                  ? "fx-project-row fx-nav-active"
                  : "fx-project-row"
              }
              aria-current={project.project_id === active ? true : undefined}
              title={project.name}
              onClick={() => {
                openProject(project.project_id);
              }}
            >
              <Icon name="folder" />
              <span className="fx-truncate">{project.name}</span>
              {/* FXCHATHIST Part 2 (H4): quiet dot while this project's
                  chat holds unseen activity; opening the chat clears it. */}
              {hasChatUnseen(client, project.project_id) ? (
                <span
                  data-testid={`project-chat-dot-${project.project_id}`}
                  className="fx-quiet"
                  aria-hidden="true"
                >
                  {"\u2022"}
                </span>
              ) : null}
            </button>
          ))
        )}
      </div>
    </nav>
  );
}
