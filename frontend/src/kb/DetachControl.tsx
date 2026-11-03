// FXROLEPICK R11: attached knowledge bases with Detach. Lists every
// attached base (GET /api/v1/kb/list); Detach posts to
// POST /api/v1/kb/detach and reads a plain result. Network is the
// only fake (global fetch).
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { z } from "zod";
import { ApiError, requestJson, requestResponse } from "../api/errors";
import { t } from "../locale/index";

const AttachedBaseSchema = z
  .object({
    kb_id: z.string().min(1),
    kind: z.string().optional(),
    role: z.string().nullable().optional(),
  })
  .passthrough();

export type AttachedBase = z.infer<typeof AttachedBaseSchema>;

const AttachedListSchema = z.array(AttachedBaseSchema);

function plainReason(error: unknown): string {
  if (error instanceof ApiError) {
    const message = error.details?.message;
    if (typeof message === "string" && message.trim() !== "") {
      return message.trim().replace(/^[A-Z][A-Z_0-9]*:\s*/, "");
    }
    return error.code;
  }
  if (error instanceof Error && error.message.trim() !== "") {
    return error.message.trim();
  }
  return t("errors.generic");
}

export function DetachControl(props: {
  projectId: string;
}): ReactElement {
  const [rows, setRows] = useState<AttachedBase[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function load(): Promise<void> {
    setLoadError(null);
    try {
      const list = await requestJson(
        `/api/v1/kb/list?project_id=${encodeURIComponent(props.projectId)}`,
        { method: "GET", kind: "read" },
        AttachedListSchema,
      );
      setRows(list);
    } catch (error) {
      setRows([]);
      setLoadError(plainReason(error));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.projectId]);

  async function onDetach(kbId: string): Promise<void> {
    setResult(null);
    setBusy(kbId);
    try {
      await requestResponse("/api/v1/kb/detach", {
        method: "POST",
        kind: "write",
        body: { kb_id: kbId },
      });
      setRows((prev) => (prev ?? []).filter((row) => row.kb_id !== kbId));
      setResult(t("projects.kbDetach.detached", { kb_id: kbId }));
    } catch (error) {
      setResult(
        t("projects.kbDetach.detachFailed", { reason: plainReason(error) }),
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <section data-testid="kb-detach-control">
      <h2>{t("projects.kbDetach.title")}</h2>
      {rows === null ? (
        <p>{t("ui.loading.more")}</p>
      ) : rows.length === 0 ? (
        <p data-testid="kb-detach-empty">{t("projects.kbDetach.empty")}</p>
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.kb_id} data-testid={`kb-detach-row-${row.kb_id}`}>
              <span>{row.kb_id}</span>
              {typeof row.kind === "string" && row.kind !== "" ? (
                <span> · {row.kind}</span>
              ) : null}
              <button
                type="button"
                data-testid={`kb-detach-${row.kb_id}`}
                disabled={busy !== null}
                onClick={() => {
                  void onDetach(row.kb_id);
                }}
              >
                {t("projects.kbDetach.detach")}
              </button>
            </li>
          ))}
        </ul>
      )}
      {loadError !== null ? (
        <p data-testid="kb-detach-load-error">{loadError}</p>
      ) : null}
      {result !== null ? (
        <p data-testid="kb-detach-result" role="status">
          {result}
        </p>
      ) : null}
    </section>
  );
}
