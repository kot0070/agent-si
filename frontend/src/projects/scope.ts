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
