// Lane A DataTable component: titled collapsible table; cell text is
// record data, headers and title resolve through t().

import type { ReactElement } from "react";
import type { DataTableProps } from "./iface";
import { t } from "../locale/index";
import { useKitExpanded } from "./Card";

export function DataTable(props: DataTableProps): ReactElement {
  const title = t(props.titleKey);
  const [expanded, toggle] = useKitExpanded(props.collapsed, props.onToggle);
  return (
    <section
      data-testid={`kit-table-${props.cardId}`}
      aria-label={title}
      style={{
        backgroundColor: "var(--agent-si-surface)",
        color: "var(--agent-si-ink)",
        borderColor: "var(--agent-si-card-border)",
      }}
    >
      <span>{title}</span>
      <button
        type="button"
        data-testid={`kit-toggle-${props.cardId}`}
        aria-label={title}
        onClick={toggle}
      >
        {title}
      </button>
      {expanded ? (
        <table>
          <thead>
            <tr>
              {props.columns.map((column) => (
                <th key={column.key}>{t(column.headerKey)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row, index) => (
              <tr key={`${props.cardId}-row-${index}`}>
                {props.columns.map((column) => (
                  <td key={column.key}>{row[column.key] ?? ""}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <span data-testid="kit-collapsed-line">{title}</span>
      )}
    </section>
  );
}
