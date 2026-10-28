// Lane A ENDPOINTS registry implementation. Values are frozen verbatim
// from frontend/src/api/iface.ts EndpointTable.

import type { EndpointKey, EndpointTable } from "./iface";

export type { EndpointKey };

export const ENDPOINTS: EndpointTable = {
  agentsLive: "/api/v1/agents/live",
  ledger: "/api/v1/runs/ledger",
  nextPackageNudge: "/api/v1/reports/next-package-nudge",
  routingWhy: "/api/v1/routing/decision/{id}/why",
  projects: "/api/v1/projects",
  projectById: "/api/v1/projects/{id}",
  tasks: "/api/v1/tasks",
  taskById: "/api/v1/tasks/{id}",
  chatStream: "/api/v1/chat/stream",
  chatCancel: "/api/v1/chat/cancel",
  budget: "/api/v1/budget",
};

export function expandEndpoint(template: string, id: string): string {
  return template.replace("{id}", encodeURIComponent(id));
}

export function withProject(template: string, projectId: string): string {
  return `${template}?project_id=${encodeURIComponent(projectId)}`;
}

export function withPackage(
  template: string,
  packageId: string,
): string {
  return `${template}?package_id=${encodeURIComponent(packageId)}`;
}
