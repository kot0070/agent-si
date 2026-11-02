// DEMOF11: the KB attach control. Posts source JSON to
// POST /api/v1/kb/attach (served by src/agent_si/backend/kb_routes.py)
// and lists every attached kb_id from the served answers. Mounted with a
// full source (an attach button for that source) or with a project id
// (the control renders kb id, kind and purpose inputs in the project
// context and posts the assembled source for that project).
import { useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { requestResponse } from "../api/errors";

export interface KbAttachSource {
  kb_id: string;
  kind: string;
  project_id: string;
  role?: string | null;
  purpose: string;
  read_only?: boolean;
}

const KB_KINDS = ["LOCAL_CAPABILITY", "DEV_ROLE", "DEV_SHARED"];

export function AttachControl(props: {
  source?: KbAttachSource;
  projectId?: string;
}): ReactElement {
  const [kbId, setKbId] = useState(props.source?.kb_id ?? "");
  const [kind, setKind] = useState(props.source?.kind ?? "DEV_ROLE");
  const [purpose, setPurpose] = useState(props.source?.purpose ?? "");
  const [attached, setAttached] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const projectId = props.source?.project_id ?? props.projectId ?? "";

  async function onAttach(): Promise<void> {
    setError(null);
    const source: KbAttachSource = props.source ?? {
      kb_id: kbId.trim(),
      kind,
      project_id: projectId,
      role: null,
      purpose: purpose.trim(),
    };
    try {
      const response = await requestResponse("/api/v1/kb/attach", {
        method: "POST",
        kind: "write",
        body: { source },
      });
      const kbIdAnswer: unknown = await response.json();
      const id =
        typeof kbIdAnswer === "string"
          ? kbIdAnswer
          : JSON.stringify(kbIdAnswer);
      setAttached((prev) => [...prev, id]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "attach failed");
    }
  }

  return (
    <section data-testid="kb-attach-control">
      <h2>{t("projects.kbAttach.title")}</h2>
      {props.source === undefined ? (
        <>
          <label>
            {t("projects.kbAttach.kbId")}
            <input
              data-testid="kb-attach-kb-id"
              type="text"
              value={kbId}
              onChange={(event) => {
                setKbId(event.target.value);
              }}
            />
          </label>
          <label>
            {t("projects.kbAttach.kind")}
            <select
              data-testid="kb-attach-kind"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value);
              }}
            >
              {KB_KINDS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("projects.kbAttach.purpose")}
            <input
              data-testid="kb-attach-purpose"
              type="text"
              value={purpose}
              onChange={(event) => {
                setPurpose(event.target.value);
              }}
            />
          </label>
        </>
      ) : null}
      <button
        type="button"
        data-testid="kb-attach-submit"
        onClick={() => void onAttach()}
      >
        {t("projects.kbAttach.submit")}
      </button>
      {attached.length === 0 ? null : (
        <ul data-testid="kb-attach-list">
          {attached.map((id, index) => (
            <li key={`${id}-${index}`} data-testid="kb-attach-result">
              {id}
            </li>
          ))}
        </ul>
      )}
      {error !== null ? <p data-testid="kb-attach-error">{error}</p> : null}
    </section>
  );
}
