// Lane A ApiClientProvider: react context for the ApiClient plus the
// current-project selection. Placed here so area tests mount without app
// imports; App re-exports in wave 3. Prop shapes mirror
// frontend/src/app/iface.ts.

import { createContext, useContext, useMemo, useState } from "react";
import type { ReactElement } from "react";
import type { ApiClient } from "../api/iface";
import type {
  ApiClientProviderProps,
  CurrentProject,
} from "./iface";

export type { ApiClientProviderProps, CurrentProject };

const ApiClientContext = createContext<ApiClient | null>(null);

interface CurrentProjectState {
  projectId: string | null;
  select: (projectId: string) => void;
}

const CurrentProjectContext = createContext<CurrentProjectState | null>(null);

export function ApiClientProvider(props: ApiClientProviderProps): ReactElement {
  const [projectId, setProjectId] = useState<string | null>(null);
  const selection = useMemo<CurrentProjectState>(
    () => ({
      projectId,
      select: (next: string) => {
        setProjectId(next);
      },
    }),
    [projectId],
  );
  return (
    <ApiClientContext.Provider value={props.client}>
      <CurrentProjectContext.Provider value={selection}>
        {props.children}
      </CurrentProjectContext.Provider>
    </ApiClientContext.Provider>
  );
}

export function useApiClient(): ApiClient {
  const client = useContext(ApiClientContext);
  if (client === null) {
    throw new Error("ApiClientProvider is missing above useApiClient");
  }
  return client;
}

export function useCurrentProject(): CurrentProject {
  const selection = useContext(CurrentProjectContext);
  if (selection === null) {
    throw new Error("ApiClientProvider is missing above useCurrentProject");
  }
  return { projectId: selection.projectId, select: selection.select };
}
