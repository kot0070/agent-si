// SPEC-5A observability verifier view: the served routing evidence for one
// stored decision (assignments, evidence snapshot and reason). Every string
// shown is served record data; with no stored WHY the view stays honestly
// empty until served rows land.

import type { ReactElement } from "react";
import type { RoutingWhy } from "../../api/iface";
import { EmptyState } from "../../ui/EmptyState";

export interface VerifierViewProps {
  why: RoutingWhy | null;
}

export function VerifierView(props: VerifierViewProps): ReactElement {
  if (props.why === null) {
    return (
      <EmptyState stateKey="ui.table.empty" actionKey={null} onAction={null} />
    );
  }
  return (
    <div data-testid="observe-verifier">
      <span data-testid="verifier-decision">
        {props.why.decision.decision_id}
      </span>
      <span data-testid="verifier-snapshot">
        {props.why.snapshot.snapshot_ref} {props.why.snapshot.captured_at}
      </span>
      <span data-testid="verifier-reason">{props.why.reason.fit_basis}</span>
      {props.why.assignments.map((assignment, index) => (
        <div key={index} data-testid={`verifier-assignment-${index}`}>
          <span>
            {assignment.provider_id}/{assignment.model} {assignment.role}
          </span>
        </div>
      ))}
    </div>
  );
}
