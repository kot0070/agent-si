// Lane A frozen app shell contract. Types plus declare signatures only.

import type { ReactElement, ReactNode } from "react";
import type { ApiClient } from "../api/iface";

export interface RouteTable {
  readonly chat: "/";
  readonly agentsLive: "/agents/live";
  readonly projects: "/projects";
  readonly projectOverview: "/projects/:projectId/overview";
  readonly projectTasks: "/projects/:projectId/tasks";
  readonly projectRuns: "/projects/:projectId/runs";
  readonly projectTime: "/projects/:projectId/time";
  readonly projectAiUsage: "/projects/:projectId/ai-usage";
  readonly projectTokens: "/projects/:projectId/tokens";
  readonly projectCost: "/projects/:projectId/cost";
  readonly projectLocalAi: "/projects/:projectId/local-ai";
  readonly projectCloudAi: "/projects/:projectId/cloud-ai";
  readonly projectModels: "/projects/:projectId/models";
  readonly projectRouting: "/projects/:projectId/routing-decisions";
  readonly projectAudits: "/projects/:projectId/audits";
  readonly projectErrors: "/projects/:projectId/errors";
  readonly projectReports: "/projects/:projectId/reports";
}

export declare const ROUTES: RouteTable;

export interface ApiClientProviderProps {
  client: ApiClient;
  children: ReactNode;
}

export declare function ApiClientProvider(
  props: ApiClientProviderProps,
): ReactElement;

export interface CurrentProject {
  projectId: string | null;
  select(projectId: string): void;
}

export declare function useCurrentProject(): CurrentProject;

export interface TopBarProps {
  projectId: string | null;
}

export declare function TopBar(props: TopBarProps): ReactElement;

export interface SidebarProps {
  projectId: string | null;
}

export declare function Sidebar(props: SidebarProps): ReactElement;

export interface InspectorProps {
  projectId: string | null;
}

export declare function Inspector(props: InspectorProps): ReactElement;

export interface ClosingGuardProps {
  armed: boolean;
  confirmKey: string;
  children: ReactNode;
}

export declare function ClosingGuard(props: ClosingGuardProps): ReactElement;
