// K07NEXT2 M-R-UX-8 + K10AN: the live telemetry summary over the served route.
// R7: real tokens and cost from the ledger (never record counts), by
// model and by provider from the same doc. A section with no served
// data is hidden, never an unavailable paragraph.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { z } from "zod";
import { requestJson } from "../api/errors";
import { t } from "../locale/index";

const K10AN_COUNT = z.union([z.number().int(), z.null()]);
const K10AN_VALUE = z.union([z.number(), z.literal("UNAVAILABLE")]);
const K10AN_OPT_VALUE = z.union([z.number(), z.literal("UNAVAILABLE"), z.null()]);

const K10AN_MODEL_ROW_SCHEMA = z.object({
  model: z.string(),
  calls: z.number().int(),
  tokens: K10AN_VALUE,
  cost: K10AN_VALUE,
});

const K10AN_PROVIDER_ROW_SCHEMA = z.object({
  provider: z.string(),
  calls: z.number().int(),
  tokens: K10AN_VALUE,
  cost: K10AN_VALUE,
});

const K10AN_SUMMARY_SCHEMA = z.object({
  project: z
    .object({
      tasks: K10AN_COUNT,
      audits: K10AN_COUNT,
      tokens: K10AN_OPT_VALUE.optional(),
    })
    .optional(),
  models: z.array(K10AN_MODEL_ROW_SCHEMA).optional(),
  providers: z.array(K10AN_PROVIDER_ROW_SCHEMA).optional(),
  unavailable: z.array(z.string()).optional(),
});

type K10ANModelRow = z.infer<typeof K10AN_MODEL_ROW_SCHEMA>;
type K10ANProviderRow = z.infer<typeof K10AN_PROVIDER_ROW_SCHEMA>;
type K10ANSummary = z.infer<typeof K10AN_SUMMARY_SCHEMA>;

function K10ANValue(props: {
  value: number | "UNAVAILABLE" | null | undefined;
  testid: string;
}): ReactElement {
  if (props.value === null || props.value === undefined) {
    return <span data-testid={props.testid}>{t("telemetry.unavailable")}</span>;
  }
  return <span data-testid={props.testid}>{props.value}</span>;
}

function K10ANModelTable(props: { rows: K10ANModelRow[] }): ReactElement {
  if (props.rows.length === 0) {
    return (
      <p data-testid="k10an-models-unavailable">{t("telemetry.unavailable")}</p>
    );
  }
  return (
    <table data-testid="k10an-models">
      <thead>
        <tr>
          <th>{t("telemetry.model")}</th>
          <th>{t("telemetry.calls")}</th>
          <th>{t("telemetry.tokens")}</th>
          <th>{t("telemetry.cost")}</th>
        </tr>
      </thead>
      <tbody>
        {props.rows.map((row) => (
          <tr key={row.model}>
            <td>{row.model}</td>
            <td>{row.calls}</td>
            <td>
              <K10ANValue
                value={row.tokens}
                testid={`k10an-model-tokens-${row.model}`}
              />
            </td>
            <td>
              <K10ANValue
                value={row.cost}
                testid={`k10an-model-cost-${row.model}`}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function K10ANProviderTable(props: { rows: K10ANProviderRow[] }): ReactElement {
  if (props.rows.length === 0) {
    return (
      <p data-testid="k10an-providers-unavailable">{t("telemetry.unavailable")}</p>
    );
  }
  return (
    <table data-testid="k10an-providers">
      <thead>
        <tr>
          <th>{t("telemetry.provider")}</th>
          <th>{t("telemetry.calls")}</th>
          <th>{t("telemetry.tokens")}</th>
          <th>{t("telemetry.cost")}</th>
        </tr>
      </thead>
      <tbody>
        {props.rows.map((row) => (
          <tr key={row.provider}>
            <td>{row.provider}</td>
            <td>{row.calls}</td>
            <td>
              <K10ANValue
                value={row.tokens}
                testid={`k10an-provider-tokens-${row.provider}`}
              />
            </td>
            <td>
              <K10ANValue
                value={row.cost}
                testid={`k10an-provider-cost-${row.provider}`}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function servedNumber(
  value: number | "UNAVAILABLE" | null | undefined,
): number | null {
  return typeof value === "number" ? value : null;
}

/** Rows carrying at least one evidenced number; call-only rows stay out. */
function evidencedRows<T extends { tokens: number | "UNAVAILABLE"; cost: number | "UNAVAILABLE" }>(
  rows: T[],
): T[] {
  return rows.filter(
    (row) =>
      servedNumber(row.tokens) !== null || servedNumber(row.cost) !== null,
  );
}

export function TelemetrySummary(props: {
  projectId?: string;
}): ReactElement {
  const [summary, setSummary] = useState<K10ANSummary | null>(null);
  const projectId = props.projectId;
  useEffect(() => {
    let alive = true;
    const path = projectId
      ? `/api/v1/analytics/telemetry?project_id=${encodeURIComponent(projectId)}`
      : "/api/v1/analytics/telemetry";
    void requestJson(path, { method: "GET", kind: "read" }, K10AN_SUMMARY_SCHEMA)
      .then((next) => {
        if (alive) {
          setSummary(next);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [projectId]);
  const tokensTotal = servedNumber(summary?.project?.tokens ?? null);
  const modelRows = evidencedRows(summary?.models ?? []);
  const providerRows = evidencedRows(summary?.providers ?? []);
  const costSources = modelRows.length > 0 ? modelRows : providerRows;
  const costValues = costSources
    .map((row) => servedNumber(row.cost))
    .filter((value): value is number => value !== null);
  const costTotal = costValues.length > 0
    ? costValues.reduce((left, right) => left + right, 0)
    : null;
  return (
    <section data-testid="k07next2-telemetry">
      <h2>{t("projects.ai_usage.title")}</h2>
      {tokensTotal === null && costTotal === null ? null : (
        <dl data-testid="k10an-totals">
          {tokensTotal === null ? null : (
            <>
              <dt>{t("telemetry.tokens")}</dt>
              <dd data-testid="k10an-tokens-total">{tokensTotal}</dd>
            </>
          )}
          {costTotal === null ? null : (
            <>
              <dt>{t("telemetry.cost")}</dt>
              <dd data-testid="k10an-cost-total">{costTotal}</dd>
            </>
          )}
        </dl>
      )}
      {modelRows.length === 0 ? null : (
        <section data-testid="k10an-model-section">
          <h3>{t("telemetry.perModel")}</h3>
          <K10ANModelTable rows={modelRows} />
        </section>
      )}
      {providerRows.length === 0 ? null : (
        <section data-testid="k10an-provider-section">
          <h3>{t("telemetry.perProvider")}</h3>
          <K10ANProviderTable rows={providerRows} />
        </section>
      )}
    </section>
  );
}
