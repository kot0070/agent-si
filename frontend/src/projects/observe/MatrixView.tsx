// SPEC-5A observability matrix view: the served agents-live rows bucketed
// with the documented placement rule from agentsApi. The rule itself lives
// in countPlacements and splitRowsByPlacement and is reused here, never
// restated. Every number shown is an exact served row count; every string
// is a locale lookup or served record data. With no rows the view stays
// honestly empty until served rows land.

import type { ReactElement } from "react";
import type { PartRow } from "../../api/iface";
import { EmptyState } from "../../ui/EmptyState";
import { PLACEMENTS, countPlacements } from "../../agents/agentsApi";
import { splitRowsByPlacement } from "../projectsApi";

export interface MatrixViewProps {
  rows: PartRow[];
}

export function MatrixView(props: MatrixViewProps): ReactElement {
  if (props.rows.length === 0) {
    return (
      <EmptyState
        stateKey="agents.live.empty"
        actionKey={null}
        onAction={null}
      />
    );
  }
  const counts = countPlacements(props.rows);
  const buckets = splitRowsByPlacement(props.rows);
  return (
    <div data-testid="observe-matrix">
      <div>
        {PLACEMENTS.map((placement) => (
          <span key={placement} data-testid={`matrix-count-${placement}`}>
            {counts[placement]}
          </span>
        ))}
      </div>
      {PLACEMENTS.map((placement) =>
        buckets[placement].map((row) => (
          <div key={row.agent} data-testid={`matrix-row-${row.agent}`}>
            <span>{row.agent}</span>
            <span>{row.scope}</span>
            <span>{row.status}</span>
          </div>
        )),
      )}
    </div>
  );
}
