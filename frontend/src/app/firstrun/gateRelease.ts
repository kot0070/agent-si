// FXNAV W03: session-scoped first-run gate release. A rail-nav click
// during the guided first run lets the user visit that page for the rest
// of this tab session without marking the run done (/firstrun stays
// resumable). Single source of truth is sessionStorage (cleared by every
// suite's beforeEach, so no cross-test leak); a memory bit covers only
// storageless hosts. No imports: Sidebar and the gate share it without a
// dependency cycle.
const RELEASE_KEY = 'agentsi.firstrun.navRelease';

let memoryRelease = false;

function sessionStore(): Storage | null {
  try {
    const store = window.sessionStorage;
    store.getItem(RELEASE_KEY);
    return store;
  } catch {
    return null;
  }
}

export function releaseFirstRunGateForSession(): void {
  const store = sessionStore();
  if (store !== null) {
    try {
      store.setItem(RELEASE_KEY, '1');
      return;
    } catch {
      // Fall through to the memory bit below.
    }
  }
  memoryRelease = true;
}

export function isFirstRunGateReleased(): boolean {
  const store = sessionStore();
  if (store !== null) {
    try {
      return store.getItem(RELEASE_KEY) === '1';
    } catch {
      return memoryRelease;
    }
  }
  return memoryRelease;
}

export function resetFirstRunGateForTests(): void {
  memoryRelease = false;
  const store = sessionStore();
  if (store !== null) {
    try {
      store.removeItem(RELEASE_KEY);
    } catch {
      // Nothing to reset when storage itself is unavailable.
    }
  }
}
