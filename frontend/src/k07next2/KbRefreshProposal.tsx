// K07NEXT2 M-R-UX-9: the KB refresh proposal screen over the real provider.
// The capabilityDB settings branch mounts this screen: it shows the model
// KB state from GET /api/v1/kb/status, then the stored refresh proposal,
// and the Update control posts refresh (POST /api/v1/kb/update) plus apply
// (POST /api/v1/kb/proposals/apply), showing the served result.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { requestResponse } from "../api/errors";
import { readKbProposalDoc } from "./k07next2Api";
import type { KbProposalDoc } from "./k07next2Api";

const KB_STATUS_ROUTE = "/api/v1/kb/status";
const KB_UPDATE_ROUTE = "/api/v1/kb/update";
const KB_APPLY_ROUTE = "/api/v1/kb/proposals/apply";

async function readKbStatusText(): Promise<string> {
  const response = await fetch(KB_STATUS_ROUTE);
  if (!response.ok) {
    throw new Error(`kb status request failed: ${response.status}`);
  }
  const body: unknown = await response.json();
  return JSON.stringify(body);
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

export function KbRefreshProposal(): ReactElement {
  const [doc, setDoc] = useState<KbProposalDoc | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
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
    void readKbStatusText()
      .then((text) => {
        if (alive) {
          setStatus(text);
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
        setResult(JSON.stringify(refreshed));
        return;
      }
      const applied = await postKbJson(KB_APPLY_ROUTE, {
        proposal_id: proposalId,
        approved_by_user: true,
      });
      setResult(JSON.stringify({ refresh: refreshed, apply: applied }));
    } catch (error) {
      setUpdateError(error instanceof Error ? error.message : "request failed");
    } finally {
      setUpdating(false);
    }
  }

  return (
    <section data-testid="k07next2-kb-proposal">
      <h2>{t("firstrun.optional.kbs")}</h2>
      {status === null ? null : <p data-testid="kb-status">{status}</p>}
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
        <p data-testid="kb-update-result">{result}</p>
      )}
      {updateError === null ? null : (
        <p data-testid="kb-update-error">{updateError}</p>
      )}
      {doc === null ? null : doc.proposals.length === 0 ? (
        <p data-testid="k07next2-kb-proposal-empty">{t("ui.table.empty")}</p>
      ) : (
        <ol>
          {doc.proposals.map((proposal, index) => (
            <li key={index}>{JSON.stringify(proposal)}</li>
          ))}
        </ol>
      )}
    </section>
  );
}
