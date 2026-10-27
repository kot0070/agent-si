// LeftoverKeyFinder: frozen section 3.8 name for the leftover-key finder.
// Reuses the existing finder component. By default entries load from
// `store.list(APP_NAMESPACE_PREFIX)` (app namespace only, names plus dates).
// When the A1 `GET /api/v1/providers/leftover-keys` delta lands, repoint
// `loadEntries` to fetch there; no other change is needed. Deletion stays
// user-click only, per-entry confirmed behind the session token,
// live-provider-linked entries stay protected, and deletions are
// audit-logged by entry name only.

import { useMemo } from "react";
import { APP_NAMESPACE_PREFIX } from "./types";
import { LeftoverFinder } from "./LeftoverFinder";
import type { SecretStorePort } from "./secretStore";
import type { SecretRef } from "./types";

export type LeftoverKeyFinderProps = {
  store: SecretStorePort;
  sessionToken: string;
  linkedSecretIds: string[];
  refreshKey?: number;
  loadEntries?: () => Promise<SecretRef[]>;
};

export function LeftoverKeyFinder({
  store,
  sessionToken,
  linkedSecretIds,
  refreshKey = 0,
  loadEntries,
}: LeftoverKeyFinderProps) {
  const fallback = useMemo(() => async (): Promise<SecretRef[]> => store.list(APP_NAMESPACE_PREFIX), [store]);
  const load = loadEntries ?? fallback;
  const loader = useMemo<SecretStorePort>(
    () => ({ ...store, list: async (): Promise<SecretRef[]> => load() }),
    [store, load],
  );
  return (
    <LeftoverFinder
      store={loader}
      sessionToken={sessionToken}
      linkedSecretIds={linkedSecretIds}
      refreshKey={refreshKey}
    />
  );
}

export { LeftoverFinder };
