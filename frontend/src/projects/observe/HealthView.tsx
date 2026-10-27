// SPEC-5A observability health view: served ledger rows plus the served
// budget state. Every number shown traces to a served record cell through
// the owned pure helpers sumLedger and remainingBudget; nothing is
// estimated. With no ledger rows the view stays honestly empty until served
// rows land.

import type { ReactElement } from "react";
import type { BudgetState, LedgerRow } from "../../api/iface";
import { t } from "../../locale/index";
import { EmptyState } from "../../ui/EmptyState";
import { remainingBudget, sumLedger } from "../projectsApi";

export interface HealthViewProps {
  ledger: LedgerRow[];
  budget: BudgetState;
}

export function HealthView(props: HealthViewProps): ReactElement {
  if (props.ledger.length === 0) {
    return (
      <EmptyState stateKey="ui.table.empty" actionKey={null} onAction={null} />
    );
  }
  const sums = sumLedger(props.ledger);
  return (
    <div data-testid="observe-health">
      <span>{t("projects.time.title")}</span>
      {props.ledger.map((row) => (
        <div key={row.package_id} data-testid={`health-row-${row.package_id}`}>
          <span>{row.package_id}</span>
          <span>{row.agents}</span>
          <span>{row.wall_time_s}</span>
        </div>
      ))}
      <span data-testid="health-agents-total">{sums.agents}</span>
      <span data-testid="health-wall-total">{sums.wall}</span>
      <span data-testid="health-spent">{props.budget.spent}</span>
      <span data-testid="health-remaining">
        {remainingBudget(props.budget)}
      </span>
    </div>
  );
}
