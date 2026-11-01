// DEMOF11: the KB attach control. Posts source JSON to
// POST /api/v1/kb/attach (served by src/agent_si/backend/kb_routes.py)
// and shows the attached kb_id. Plain fetch only, no app wiring.
import { useState } from "react";
import type { ReactElement } from "react";

export interface KbAttachSource {
  kb_id: string;
  kind: string;
  project_id: string;
  role?: string | null;
  purpose: string;
  read_only?: boolean;
}

export function AttachControl({
  source,
}: {
  source: KbAttachSource;
}): ReactElement {
  const [attached, setAttached] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onAttach(): Promise<void> {
    setError(null);
    try {
      const response = await fetch("/api/v1/kb/attach", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ source }),
      });
      if (!response.ok) {
        throw new Error(`attach failed: ${response.status}`);
      }
      const kbId: unknown = await response.json();
      setAttached(typeof kbId === "string" ? kbId : JSON.stringify(kbId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "attach failed");
    }
  }

  return (
    <section data-testid="kb-attach-control">
      <h2>Attach knowledge base</h2>
      <button
        type="button"
        data-testid="kb-attach-submit"
        onClick={() => void onAttach()}
      >
        Attach KB
      </button>
      {attached !== null ? (
        <p data-testid="kb-attach-result">{attached}</p>
      ) : null}
      {error !== null ? <p data-testid="kb-attach-error">{error}</p> : null}
    </section>
  );
}
