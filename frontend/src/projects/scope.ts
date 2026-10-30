// ARCH-686 scope classification SHOULD versus MUST. Pure helper only; the
// served PartRow carries a bare scope string (for example s-1 or scope-1)
// and the server enforces claimed scopes through the overlap guards
// SCOPE_OVERLAP and REJECTED_SCOPE_OVERLAP (see api.error.scope_overlap in
// the locale tables and the agents.row.scope label). A scope string that
// names a concrete claim is therefore enforced and reads MUST: it must not
// overlap another claim. A blank scope claims nothing, so the overlap guard
// cannot fire for it, and reads SHOULD: advisory only. TaskCreate accepts
// any string list and the composer drops blank entries before posting, so
// blank scopes only reach the views through served live rows.

export const SCOPE_KINDS = ["MUST", "SHOULD"] as const;

export type ScopeKind = (typeof SCOPE_KINDS)[number];

export function classifyScope(scope: string): ScopeKind {
  return scope.trim() === "" ? "SHOULD" : "MUST";
}

// ARCH-679: every named menu and view in the console is MUST presence.
// The test ids mirror Sidebar data-testids; the views mirror PROJECT_VIEWS
// in projectsApi (the App route table renders one route per view).
export const NAMED_MENU_TEST_IDS = [
  "menu-chat",
  "menu-agents-live",
  "menu-new-task",
  "menu-projects",
  "menu-tasks",
  "menu-results",
  "menu-settings",
] as const;

// ARCH-686: treating a SHOULD breakdown as MUST presence (or the reverse)
// is a scope breach. The guard below proves it over rendered output: a
// MUST name missing from the rendered set is MUST_PRESENCE_BREACH; a
// MUST name whose render required a SHOULD (derived/extended) breakdown
// is SHOULD_AS_MUST_BREACH. Derived sections stay advisory: they never
// appear in the must set and never gate MUST rendering.
export type PresenceBreachKind =
  | "MUST_PRESENCE_BREACH"
  | "SHOULD_AS_MUST_BREACH";

export interface PresenceBreach {
  kind: PresenceBreachKind;
  name: string;
}

export function checkPresenceBreach(input: {
  must: readonly string[];
  present: readonly string[];
  gatedByShould?: readonly string[];
}): PresenceBreach[] {
  const present = new Set(input.present);
  const gated = new Set(input.gatedByShould ?? []);
  const out: PresenceBreach[] = [];
  for (const name of input.must) {
    if (!present.has(name)) {
      out.push({ kind: "MUST_PRESENCE_BREACH", name });
    } else if (gated.has(name)) {
      out.push({ kind: "SHOULD_AS_MUST_BREACH", name });
    }
  }
  return out;
}
