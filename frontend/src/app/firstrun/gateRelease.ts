// FXNAV W03: session-scoped first-run gate release. A rail-nav click
// during the guided first run lets the user visit that page for the rest
// of this session without marking the run done (/firstrun stays
// resumable). Module state (never localStorage): a reload re-arms the
// guided flow, so a truly-first open is always guided. No imports:
// Sidebar and the gate share it without a dependency cycle.
let released = false;

export function releaseFirstRunGateForSession(): void {
  released = true;
}

export function isFirstRunGateReleased(): boolean {
  return released;
}

export function resetFirstRunGateForTests(): void {
  released = false;
}
