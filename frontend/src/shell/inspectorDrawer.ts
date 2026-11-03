// FXFACTS F8: rail overlay drawer below 1200 px. One DOM class on the
// app shell plus one event bus; TopBar owns the labelled toggle, the
// Inspector aside owns data-open, Esc and the close control. Both sides
// sync through INSPECTOR_TOGGLE_EVENT so aria-expanded never lies.

export const INSPECTOR_TOGGLE_EVENT = "agentsi:toggle-inspector";

export const INSPECTOR_OPEN_CLASS = "fx-inspector-open";

function shellRoot(): Element | null {
  try {
    return document.querySelector('[data-testid="app-shell"]');
  } catch {
    return null;
  }
}

/** Set the drawer open state: shell class plus a sync event for both sides. */
export function setInspectorOpen(open: boolean): void {
  try {
    const shell = shellRoot();
    if (shell !== null) {
      shell.classList.toggle(INSPECTOR_OPEN_CLASS, open);
    }
    window.dispatchEvent(
      new CustomEvent<boolean>(INSPECTOR_TOGGLE_EVENT, { detail: open }),
    );
  } catch {
    // No document in this probe: the drawer stays as rendered.
  }
}

/** Read the drawer open state from the shell class (single source). */
export function readInspectorOpen(): boolean {
  try {
    const shell = shellRoot();
    return shell !== null && shell.classList.contains(INSPECTOR_OPEN_CLASS);
  } catch {
    return false;
  }
}

/** Toggle the drawer from its current shell-class state. */
export function toggleInspector(): void {
  setInspectorOpen(!readInspectorOpen());
}

/** Detail of INSPECTOR_TOGGLE_EVENT: the open state to sync to. */
export function inspectorEventOpen(event: Event): boolean {
  return (
    event instanceof CustomEvent && (event as CustomEvent<boolean>).detail === true
  );
}
