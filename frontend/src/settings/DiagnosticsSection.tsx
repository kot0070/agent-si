// FXNAV1: diagnostics index under Settings > Diagnostics. Lists the kept
// developer screens under labels naming what each shows; every entry links
// to its /diagnostics/<name> route (no aliases, no lane names).
// FXLOG: one log-folder line below the index: the sidecar about route
// names the data-dir log folder, and the button reveals it through
// POST /api/v1/sidecar/open-logs (path stays when reveal fails).
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import { requestResponse } from "../api/errors";
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
    <>
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
      <DiagnosticsLogFiles />
    </>
  );
}

export function DiagnosticsLogFiles(): ReactElement {
  const [logDir, setLogDir] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch("/api/v1/sidecar/about");
        if (!response.ok) {
          return;
        }
        const data: unknown = await response.json();
        if (cancelled) {
          return;
        }
        if (typeof data === "object" && data !== null
          && typeof (data as Record<string, unknown>)["logs_dir"] === "string") {
          setLogDir((data as Record<string, string>)["logs_dir"]);
        }
      } catch {
        // No about route (plain backend dev server): line stays hidden.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  if (logDir === null) {
    return <></>;
  }
  return (
    <p data-testid="diagnostics-log-files">
      {t("diagnostics.logFiles", { path: logDir })}{" "}
      <button
        type="button"
        data-testid="diagnostics-open-logs"
        onClick={() => {
          void (async () => {
            try {
              await requestResponse("/api/v1/sidecar/open-logs", {
                method: "POST",
                kind: "write",
              });
            } catch {
              // Reveal unavailable here: the path above stays the answer.
            }
          })();
        }}
      >
        {t("diagnostics.openLogs")}
      </button>
    </p>
  );
}
