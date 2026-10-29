// Lane bounded retry plus in-flight sharing for idempotent GET reads.
// 4xx failures are never retried (single fetch); other failures try at
// most 3 attempts with backoff delay; concurrent identical reads (same
// key) share one in-flight fetch. Writes and streams stay single-shot.

import { ApiError } from "./errors";

const MAX_ATTEMPTS = 3;

function retryDelayMs(attempt: number): Promise<void> {
  const waitMs = 10 * 2 ** (attempt - 1);
  return new Promise((resolve) => {
    setTimeout(resolve, waitMs);
  });
}

const inflightReads = new Map<string, Promise<unknown>>();

export async function readWithSharedRetry<T>(
  key: string,
  fetchOnce: () => Promise<T>,
): Promise<T> {
  const shared = inflightReads.get(key);
  if (shared !== undefined) {
    return shared as Promise<T>;
  }
  const task = (async (): Promise<T> => {
    for (let attempt = 1; ; attempt += 1) {
      try {
        return await fetchOnce();
      } catch (error) {
        if (
          error instanceof ApiError &&
          error.status >= 400 &&
          error.status < 500
        ) {
          throw error;
        }
        if (attempt >= MAX_ATTEMPTS) {
          throw error;
        }
        await retryDelayMs(attempt);
      }
    }
  })();
  inflightReads.set(key, task);
  try {
    return await task;
  } finally {
    if (inflightReads.get(key) === task) {
      inflightReads.delete(key);
    }
  }
}
