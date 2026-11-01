// FXNAV1: diagnostics index under Settings > Diagnostics. Lists the kept
// developer screens under labels naming what each shows; every entry links
// to its /diagnostics/<name> route (no aliases, no lane names).
import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import { t } from "../locale/index";

const DIAGNOSTICS_ENTRIES = [
  { name: "locale-coverage", labelKey: "diagnostics.localeCoverage" },
  { name: "telemetry-themes", labelKey: "diagnostics.telemetryThemes" },
  { name: "bench-check", labelKey: "diagnostics.benchCheck" },
  { name: "telemetry", labelKey: "diagnostics.telemetry" },
  { name: "bench-history", labelKey: "diagnostics.benchHistory" },
] as const;

export function DiagnosticsSection(): ReactElement {
  return (
    <nav data-testid="diagnostics-section" aria-label={t("diagnostics.title")}>
      {DIAGNOSTICS_ENTRIES.map((entry) => (
        <Link
          key={entry.name}
          data-testid={`diagnostics-link-${entry.name}`}
          to={`/diagnostics/${entry.name}`}
        >
          {t(entry.labelKey)}
        </Link>
      ))}
    </nav>
  );
}
