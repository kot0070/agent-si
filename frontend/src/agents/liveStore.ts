// FXDESIGN8 shared agents-live store: one interval per ApiClient, every
// subscriber (TopBar, Inspector, AgentsLive page) reads the same snapshot.
// Idle cadence 3 s, 1 s while a run is live (any RUNNING row), paused while
// the window is hidden. A same-payload tick keeps the cached reference, so
// subscribers do not re-render. Clients exposing `subscribe` (test fakes)
// feed the store through it with no interval of our own.

import { useSyncExternalStore } from "react";
import type { ApiClient, PartRow } from "../api/iface";

export const LIVE_IDLE_MS = 3000;
export const LIVE_ACTIVE_MS = 1000;

export interface LiveSnapshot {
  rows: PartRow[] | null;
  failed: boolean;
}

interface LiveSubscriber {
  subscribe?: (listener: (rows: PartRow[]) => void) => () => void;
}

interface ClientEntry {
  snapshot: LiveSnapshot;
  listeners: Set<() => void>;
  timer: ReturnType<typeof setTimeout> | null;
  inflight: boolean;
  stopExternal: (() => void) | null;
  external: boolean;
}

const entries = new WeakMap<ApiClient, ClientEntry>();

function emptySnapshot(): LiveSnapshot {
  return { rows: null, failed: false };
}

function sameRows(a: PartRow[] | null, b: PartRow[] | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function entryFor(client: ApiClient): ClientEntry {
  let entry = entries.get(client);
  if (entry === undefined) {
    entry = {
      snapshot: emptySnapshot(),
      listeners: new Set(),
      timer: null,
      inflight: false,
      stopExternal: null,
      external: false,
    };
    entries.set(client, entry);
  }
  return entry;
}

function emit(entry: ClientEntry): void {
  for (const notify of [...entry.listeners]) {
    notify();
  }
}

function isRunLive(rows: PartRow[]): boolean {
  return rows.some((row) => String(row.status).toUpperCase() === "RUNNING");
}

function schedule(entry: ClientEntry, client: ApiClient, delay: number): void {
  if (entry.timer !== null) {
    clearTimeout(entry.timer);
  }
  entry.timer = setTimeout(() => {
    entry.timer = null;
    void tick(entry, client);
  }, delay);
}

async function tick(entry: ClientEntry, client: ApiClient): Promise<void> {
  if (entry.listeners.size === 0) {
    return;
  }
  // Paused while the window is hidden: retry on the idle cadence.
  try {
    if (
      typeof document !== "undefined" &&
      typeof document.hidden === "boolean" &&
      document.hidden
    ) {
      schedule(entry, client, LIVE_IDLE_MS);
      return;
    }
  } catch {
    // No document in this probe: poll as usual.
  }
  if (entry.inflight) {
    return;
  }
  entry.inflight = true;
  try {
    const next = await client.listAgentsLive();
    if (!sameRows(entry.snapshot.rows, next)) {
      entry.snapshot = { rows: next, failed: false };
      emit(entry);
    } else if (entry.snapshot.failed) {
      entry.snapshot = { rows: entry.snapshot.rows, failed: false };
      emit(entry);
    }
  } catch {
    const failed = entry.snapshot.failed;
    const rows = entry.snapshot.rows ?? [];
    if (!sameRows(entry.snapshot.rows, rows) || !failed) {
      entry.snapshot = { rows, failed: true };
      emit(entry);
    }
  } finally {
    entry.inflight = false;
  }
  if (entry.listeners.size > 0) {
    const live = isRunLive(entry.snapshot.rows ?? []);
    schedule(entry, client, live ? LIVE_ACTIVE_MS : LIVE_IDLE_MS);
  }
}

function start(entry: ClientEntry, client: ApiClient): void {
  const source = client as unknown as LiveSubscriber;
  if (typeof source.subscribe === "function" && entry.stopExternal === null) {
    entry.external = true;
    try {
      entry.stopExternal = source.subscribe((next) => {
        if (!sameRows(entry.snapshot.rows, next)) {
          entry.snapshot = { rows: [...next], failed: false };
          emit(entry);
        }
      }) ?? null;
    } catch {
      entry.stopExternal = null;
    }
  }
  // The initial load runs for every client; the interval only for clients
  // without their own subscription feed.
  void tick(entry, client);
  if (!entry.external && entry.timer === null) {
    schedule(entry, client, LIVE_IDLE_MS);
  }
}

function stop(entry: ClientEntry): void {
  if (entry.timer !== null) {
    clearTimeout(entry.timer);
    entry.timer = null;
  }
}

/** Subscribe to the shared live snapshot for one client. */
export function subscribeLive(client: ApiClient, notify: () => void): () => void {
  const entry = entryFor(client);
  const first = entry.listeners.size === 0;
  entry.listeners.add(notify);
  if (first) {
    start(entry, client);
  }
  return () => {
    entry.listeners.delete(notify);
    if (entry.listeners.size === 0) {
      stop(entry);
    }
  };
}

/** Read the cached snapshot without subscribing (null until first load). */
export function getLiveSnapshot(client: ApiClient): LiveSnapshot {
  return entryFor(client).snapshot;
}

/** Force an immediate reload (retry buttons); the cadence continues. */
export function refreshLive(client: ApiClient): void {
  const entry = entries.get(client);
  if (entry === undefined || entry.listeners.size === 0) {
    return;
  }
  void tick(entry, client);
}

/** React binding: the shared snapshot for one client. */
export function useLiveRows(client: ApiClient): LiveSnapshot {
  return useSyncExternalStore(
    (notify) => subscribeLive(client, notify),
    () => getLiveSnapshot(client),
  );
}
