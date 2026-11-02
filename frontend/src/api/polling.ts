// FXCLASS P5: one shared visible-poll helper for an 8 GB laptop.
// Skip the tick when the tab is hidden, do one fresh read when it
// becomes visible again, back off 3-6-12-30 s on failure, reset on
// success. No other logic lives here; pollers keep their own fetch.
export const POLL_BACKOFF_MS = [3000, 6000, 12000, 30000] as const;

/** Backoff delay for a consecutive-failure count (0 failures = 3 s). */
export function backoffForFailures(failures: number): number {
  if (!Number.isFinite(failures) || failures <= 0) {
    return POLL_BACKOFF_MS[0];
  }
  const index = Math.min(
    Math.floor(failures),
    POLL_BACKOFF_MS.length - 1,
  );
  return POLL_BACKOFF_MS[index];
}

/** True when the tab is hidden: the tick must be skipped. */
export function isHiddenTick(): boolean {
  try {
    return (
      typeof document !== "undefined" &&
      typeof document.hidden === "boolean" &&
      document.hidden
    );
  } catch {
    return false;
  }
}

/** Run onVisible once when the tab becomes visible again. */
export function onVisible(onVisibleFn: () => void): () => void {
  if (typeof document === "undefined") {
    return () => undefined;
  }
  const handler = (): void => {
    if (!document.hidden) {
      onVisibleFn();
    }
  };
  document.addEventListener("visibilitychange", handler);
  return () => {
    document.removeEventListener("visibilitychange", handler);
  };
}
