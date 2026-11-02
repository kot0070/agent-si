// K07NEXT2 M-R-UX-9: the KB refresh proposal screen over the real provider.
// The capabilityDB settings branch mounts this screen: it shows the model
// KB state from GET /api/v1/kb/status, then the stored refresh proposal,
// and the Update control posts refresh (POST /api/v1/kb/update) plus apply
// (POST /api/v1/kb/proposals/apply), showing the served result.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { formatDateLong } from "../locale/index";
import { EVIDENCE_LOCALE_KEYS } from "../settings/LocalBenchTypes";
import { requestResponse } from "../api/errors";
import { readKbProposalDoc } from "./k07next2Api";
import type { KbProposalDoc } from "./k07next2Api";

const KB_STATUS_ROUTE = "/api/v1/kb/status";
const KB_UPDATE_ROUTE = "/api/v1/kb/update";
const KB_APPLY_ROUTE = "/api/v1/kb/proposals/apply";

async function readKbStatusDoc(): Promise<unknown> {
  const response = await fetch(KB_STATUS_ROUTE);
  if (!response.ok) {
    throw new Error(`kb status request failed: ${response.status}`);
  }
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

async function postKbJson(route: string, body: unknown): Promise<unknown> {
  const response = await requestResponse(route, {
    method: "POST",
    kind: "write",
    body,
  });
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

function proposalIdOf(value: unknown): string | null {
  if (typeof value === "object" && value !== null) {
    const record = value as Record<string, unknown>;
    const candidate = record["proposal_id"];
    if (typeof candidate === "string" && candidate !== "") {
      return candidate;
    }
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// FXDESIGN2: served KB facts render as readable table rows, never raw
// JSON. Nested records flatten to "name: value" pairs joined with "; ",
// so no braces or quotes from JSON.stringify ever reach the card.
// FXDESIGN3 S6: served evidence-enum tokens (UNKNOWN/PROXY/MEASURED) render
// their locale label, never the bare token.
/** FXDESIGN7 item 15: served snake_case facts render human
 * ("kb_version" -> "Version", "updated_at" -> "Updated"); values stay
 * served, ISO timestamps render as locale dates. B1: the served
 * kb/status + proposal + update-result keys all map (overall stays
 * lowercase: fxdesign2 S2 pins "overall" in the kb-status card). */
const HUMAN_FIELD_ALIASES: Record<string, string> = {
  overall: "overall",
  per_provider: "Per provider",
  kb_version: "Version",
  updated_at: "Updated",
  total_changes: "Total changes",
  last_source: "Last source",
  models: "Models",
  last_change_at: "Last change",
  proposals: "Proposals",
  proposal_id: "Proposal",
  applied: "Applied",
  version: "Version",
  cost_state: "Cost",
  metric: "Metric",
  refresh: "Refresh",
  apply: "Apply",
  changes: "Changes",
  source: "Source",
  providers: "Providers",
  reason: "Reason",
  field: "Field",
};

export function humanFieldName(name: string): string {
  return HUMAN_FIELD_ALIASES[name] ?? name;
}

const ISO_STAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

function renderFactValue(value: unknown): string {
  if (typeof value === "string") {
    if (ISO_STAMP.test(value)) {
      return formatDateLong(value);
    }
    const tier = value.toUpperCase() as keyof typeof EVIDENCE_LOCALE_KEYS;
    const labelKey = EVIDENCE_LOCALE_KEYS[tier];
    if (labelKey !== undefined) {
      return t(labelKey);
    }
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return t("shell.common.unknown");
    }
    return value.map((entry) => renderFactValue(entry)).join("; ");
  }
  if (isRecord(value)) {
    const parts = Object.entries(value).map(
      ([name, entry]) => `${humanFieldName(name)}: ${renderFactValue(entry)}`,
    );
    return parts.length === 0 ? t("shell.common.unknown") : parts.join("; ");
  }
  return t("shell.common.unknown");
}

function FactRows(props: { data: unknown }): ReactElement {
  if (isRecord(props.data)) {
    return (
      <>
        {Object.entries(props.data).map(([name, entry]) => (
          <tr key={name}>
            <th scope="row">{humanFieldName(name)}</th>
            <td>{renderFactValue(entry)}</td>
          </tr>
        ))}
      </>
    );
  }
  if (Array.isArray(props.data)) {
    return (
      <>
        {props.data.map((entry, index) => (
          <tr key={index}>
            <td>{renderFactValue(entry)}</td>
          </tr>
        ))}
      </>
    );
  }
  return (
    <tr>
      <td>{renderFactValue(props.data)}</td>
    </tr>
  );
}

export function KbRefreshProposal(): ReactElement {
  const [doc, setDoc] = useState<KbProposalDoc | null>(null);
  const [status, setStatus] = useState<unknown>(null);
  const [result, setResult] = useState<unknown>(null);
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void readKbProposalDoc()
      .then((next) => {
        if (alive) {
          setDoc(next);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    void readKbStatusDoc()
      .then((doc) => {
        if (alive) {
          setStatus(doc);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  async function runUpdate(): Promise<void> {
    if (updating) {
      return;
    }
    setUpdating(true);
    setUpdateError(null);
    try {
      const refreshed = await postKbJson(KB_UPDATE_ROUTE, {
        approved_by_user: true,
      });
      const proposalId = proposalIdOf(refreshed);
      if (proposalId === null) {
        setResult(refreshed);
        return;
      }
      const applied = await postKbJson(KB_APPLY_ROUTE, {
        proposal_id: proposalId,
        approved_by_user: true,
      });
      setResult({ refresh: refreshed, apply: applied });
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : "request failed");
    } finally {
      setUpdating(false);
    }
  }

  return (
    <section data-testid="k07next2-kb-proposal">
      <h2>{t("firstrun.optional.kbs")}</h2>
      {status === null ? null : (
        <div data-testid="kb-status">
          <table>
            <tbody>
              <FactRows data={status} />
            </tbody>
          </table>
        </div>
      )}
      <button
        type="button"
        data-testid="kb-update"
        disabled={updating}
        onClick={() => {
          void runUpdate();
        }}
      >
        {t("settings.capabilityDb.update")}
      </button>
      {updating ? <p>{t("chat.stream.spinner")}</p> : null}
      {result === null ? null : (
        <div data-testid="kb-update-result">
          <table>
            <tbody>
              <FactRows data={result} />
            </tbody>
          </table>
        </div>
      )}
      {updateError === null ? null : (
        <p data-testid="kb-update-error">{updateError}</p>
      )}
      {doc === null ? null : doc.proposals.length === 0 ? (
        <p data-testid="k07next2-kb-proposal-empty">{t("ui.table.empty")}</p>
      ) : (
        <ol>
          {doc.proposals.map((proposal, index) => (
            <li key={index}>
              <table>
                <tbody>
                  <FactRows data={proposal} />
                </tbody>
              </table>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
