// FXPROJ J1: one shared project list with refetch on create, delete and
// route change. Every consumer (Sidebar, ProjectsPage, AppShell chat
// start) reads this store, so a project created after mount (the
// ChatStartBox first-message path) appears without a remount. Loading is
// never an empty list (projects stays null until the first load) and a
// failed load is never an empty list either (the last good rows stay
// visible; the first load reports failure with a retry).

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { useLocation } from "react-router-dom";
import type { ProjectRecord } from "../api/iface";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { useApiClient } from "../app/ApiClientProvider";
export interface ProjectListFailure {
  errorKey: string;
  code: string;
}

export interface ProjectListValue {
  /** Null while the first load is in flight: loading, never empty. */
  projects: ProjectRecord[] | null;
  failure: ProjectListFailure | null;
  refresh: () => void;
}

const ProjectListContext = createContext<ProjectListValue | null>(null);

function toFailure(error: unknown): ProjectListFailure {
  if (error instanceof ApiError) {
    return { errorKey: apiErrorLocaleKey(error.code), code: error.code };
  }
  return { errorKey: "errors.generic", code: "CONTEXT_MISSING" };
}

function useOptionalPathname(): string {
  try {
    return useLocation().pathname;
  } catch {
    return "/";
  }
}

// Local list state: the same load semantics the provider shares. Used
// as the standalone fallback so area tests and embeds that mount
// Sidebar/ProjectsPage without the shell provider keep working with
// their own fetch instead of throwing.
function useProjectListState(
  enabled: boolean,
  onLoad?: (rows: ProjectRecord[]) => void,
): ProjectListValue {
  const client = useApiClient();
  const pathname = useOptionalPathname();
  const [projects, setProjects] = useState<ProjectRecord[] | null>(null);
  const [failure, setFailure] = useState<ProjectListFailure | null>(null);
  const [nonce, setNonce] = useState(0);
  // Latest callback without refetching when the parent re-renders.
  const onLoadRef = useRef(onLoad);
  onLoadRef.current = onLoad;

  const refresh = useCallback(() => {
    setNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let alive = true;
    async function load(): Promise<void> {
      try {
        const next = await client.listProjects();
        if (alive) {
          setProjects(next);
          setFailure(null);
          onLoadRef.current?.(next);
        }
      } catch (error) {
        if (alive) {
          setFailure(toFailure(error));
        }
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [client, pathname, nonce, enabled]);

  return useMemo<ProjectListValue>(
    () => ({ projects, failure, refresh }),
    [projects, failure, refresh],
  );
}

export function ProjectListProvider(props: {
  children: ReactNode;
  /** Same-tick hook on every successful load (first paint selection). */
  onLoad?: (rows: ProjectRecord[]) => void;
}): ReactElement {
  // The provider owns one shared fetch; the pathname dep refetches on
  // route change, refresh() on create/delete.
  const value = useProjectListState(true, props.onLoad);
  return (
    <ProjectListContext.Provider value={value}>
      {props.children}
    </ProjectListContext.Provider>
  );
}

export function useProjectList(): ProjectListValue {
  const shared = useContext(ProjectListContext);
  // Standalone mounts (area tests, embeds) without the shell provider
  // fall back to a local fetch with the same semantics; under the
  // provider the local load stays disabled and costs no request.
  const local = useProjectListState(shared === null);
  return shared ?? local;
}
