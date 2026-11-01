// K07NEXT2 M-R-UX-8 + K10AN: the live telemetry summary over the served route.
// Legacy counters come from readTelemetryDoc (k07next2Api); the K10AN project,
// per-model and per-provider sections come from the same live route read here
// (extended form with ?project_id=), never from kept-aside or canned data.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { z } from "zod";
import { requestJson } from "../api/errors";
import { t } from "../locale/index";
import { readTelemetryDoc } from "./k07next2Api";
import type { TelemetryDoc } from "./k07next2Api";

const K10AN_COUNT = z.union([z.number().int(), z.null()]);
const K10AN_VALUE = z.union([z.number(), z.literal("UNAVAILABLE")]);

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
    .object({ tasks: K10AN_COUNT, audits: K10AN_COUNT })
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
    return <span data-testid={props.testid}>UNAVAILABLE</span>;
  }
  return <span data-testid={props.testid}>{props.value}</span>;
}

function K10ANModelTable(props: { rows: K10ANModelRow[] }): ReactElement {
  if (props.rows.length === 0) {
    return (
      <p data-testid="k10an-models-unavailable">UNAVAILABLE</p>
    );
  }
  return (
    <table data-testid="k10an-models">
      <thead>
        <tr>
          <th>Model</th>
          <th>Calls</th>
          <th>Tokens</th>
          <th>Cost</th>
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
      <p data-testid="k10an-providers-unavailable">UNAVAILABLE</p>
    );
  }
  return (
    <table data-testid="k10an-providers">
      <thead>
        <tr>
          <th>Provider</th>
          <th>Calls</th>
          <th>Tokens</th>
          <th>Cost</th>
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

export function TelemetrySummary(props: {
  projectId?: string;
}): ReactElement {
  const [doc, setDoc] = useState<TelemetryDoc | null>(null);
  const [summary, setSummary] = useState<K10ANSummary | null>(null);
  const projectId = props.projectId;
  useEffect(() => {
    let alive = true;
    void readTelemetryDoc()
      .then((next) => {
        if (alive) {
          setDoc(next);
        }
      })
      .catch(() => undefined);
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
  return (
    <section data-testid="k07next2-telemetry">
      <h2>{t("projects.ai_usage.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <dl>
          <dt>{t("telemetry.tokens")}</dt>
          <dd data-testid="k07next2-telemetry-metric-records">
            {doc.metric_records}
          </dd>
          <dt>{t("telemetry.cost")}</dt>
          <dd data-testid="k07next2-telemetry-events">
            {doc.telemetry_events}
          </dd>
        </dl>
      )}
      <section data-testid="k10an-project">
        <h3>Project</h3>
        <dl>
          <dt>Tasks</dt>
          <dd>
            <K10ANValue
              value={summary?.project?.tasks ?? null}
              testid="k10an-project-tasks"
            />
          </dd>
          <dt>Audits</dt>
          <dd>
            <K10ANValue
              value={summary?.project?.audits ?? null}
              testid="k10an-project-audits"
            />
          </dd>
        </dl>
      </section>
      <section data-testid="k10an-model-section">
        <h3>Per-model</h3>
        <K10ANModelTable rows={summary?.models ?? []} />
      </section>
      <section data-testid="k10an-provider-section">
        <h3>Per-provider</h3>
        <K10ANProviderTable rows={summary?.providers ?? []} />
      </section>
    </section>
  );
}
