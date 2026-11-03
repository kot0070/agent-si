// K07NEXT2 M-R-UX-9: the KB refresh proposal screen over the real provider.
// The capabilityDB settings branch mounts this screen: it shows the model
// KB state from GET /api/v1/kb/status, the staged update preview from
// POST /api/v1/kb/update, file uploads via POST /api/v1/kb/file-proposal,
// online checks via POST /api/v1/kb/check-online, and the explicit apply
// (POST /api/v1/kb/proposals/apply) plus reject
// (POST /api/v1/kb/proposals/reject), showing the served result.
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";
import { t } from "../locale/index";
import { formatDateLong } from "../locale/index";
import { EVIDENCE_LOCALE_KEYS } from "../settings/LocalBenchTypes";
import { ApiError } from "../api/errors";
import { apiErrorLocaleKey } from "../api/errors";
import { requestResponse } from "../api/errors";
import { readKbProposalDoc } from "./k07next2Api";
import type { KbProposalDoc } from "./k07next2Api";

const KB_STATUS_ROUTE = "/api/v1/kb/status";
const KB_UPDATE_ROUTE = "/api/v1/kb/update";
const KB_APPLY_ROUTE = "/api/v1/kb/proposals/apply";
const KB_REJECT_ROUTE = "/api/v1/kb/proposals/reject";
const KB_FILE_ROUTE = "/api/v1/kb/file-proposal";
const KB_CHECK_ONLINE_ROUTE = "/api/v1/kb/check-online";

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

function proposalsOf(value: unknown): Array<Record<string, unknown>> {
  if (typeof value === "object" && value !== null) {
    const record = value as Record<string, unknown>;
    const candidate = record["proposals"];
    if (Array.isArray(candidate)) {
      return candidate.filter(
        (entry): entry is Record<string, unknown> =>
          typeof entry === "object" && entry !== null,
      );
    }
  }
  return [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function messageOf(value: unknown): string | null {
  const record = asRecord(value);
  if (record === null) {
    return null;
  }
  const candidate = record["message"];
  return typeof candidate === "string" && candidate !== "" ? candidate : null;
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (
      typeof error.details?.message === "string" &&
      error.details.message !== ""
    ) {
      return error.details.message;
    }
    try {
      return t(apiErrorLocaleKey(error.code));
    } catch {
      return t("errors.generic");
    }
  }
  if (error instanceof Error && error.message !== "") {
    return error.message;
  }
  try {
    return t("errors.generic");
  } catch {
    return "Something went wrong. Try again.";
  }
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

interface PerModelCount {
  provider_id: string;
  model_id: string;
  fields: number;
}

interface FieldChange {
  provider_id?: string;
  model_id?: string;
  field?: string;
  old?: unknown;
  new?: unknown;
  source?: string;
  retrieved_at?: string;
}

function perModelOf(preview: Record<string, unknown>): PerModelCount[] {
  const raw = preview["per_model"];
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: PerModelCount[] = [];
  for (const entry of raw) {
    const record = asRecord(entry);
    if (record === null) {
      continue;
    }
    const provider = record["provider_id"];
    const model = record["model_id"];
    const fields = record["fields"];
    if (typeof model !== "string" || typeof fields !== "number") {
      continue;
    }
    out.push({
      provider_id: typeof provider === "string" ? provider : "",
      model_id: model,
      fields,
    });
  }
  return out;
}

function changesOf(preview: Record<string, unknown>): FieldChange[] {
  const raw = preview["changes"];
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter(
    (entry): entry is FieldChange =>
      asRecord(entry) !== null &&
      typeof (entry as Record<string, unknown>)["field"] === "string",
  );
}

function sourceLinkOf(source: unknown): ReactElement {
  if (typeof source !== "string" || source === "") {
    return <span>{t("shell.common.unknown")}</span>;
  }
  if (!source.startsWith("https://")) {
    return <span>{source}</span>;
  }
  let host = source;
  try {
    host = new URL(source).host;
  } catch {
    host = source;
  }
  return (
    <a href={source} target="_blank" rel="noreferrer">
      {host}
    </a>
  );
}

function ChangeList(props: { preview: Record<string, unknown> }): ReactElement {
  const changes = changesOf(props.preview);
  if (changes.length === 0) {
    return <></>;
  }
  return (
    <details>
      <summary>
        {t("settings.capabilityDb.changes")} ({changes.length})
      </summary>
      <ul>
        {changes.map((change, index) => (
          <li key={index}>
            {String(change.field)}: {renderFactValue(change.old)}{" "}
            {t("settings.capabilityDb.changeTo")}{" "}
            {renderFactValue(change.new)}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function KbRefreshProposal(): ReactElement {
  const [doc, setDoc] = useState<KbProposalDoc | null>(null);
  const [status, setStatus] = useState<unknown>(null);
  const [result, setResult] = useState<unknown>(null);
  const [previews, setPreviews] = useState<Record<string, unknown>[]>([]);
  const [onlineProviders, setOnlineProviders] = useState<
    Record<string, unknown>[]
  >([]);
  const [onlineSkipped, setOnlineSkipped] = useState<
    Record<string, unknown>[]
  >([]);
  const [updating, setUpdating] = useState(false);
  const [busyKind, setBusyKind] = useState<string | null>(null);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

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

  async function refreshStatus(): Promise<void> {
    try {
      const next = await readKbStatusDoc();
      setStatus(next);
    } catch {
      // A status re-read never hides the served result.
    }
  }

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

  function statusOverall(): Record<string, unknown> {
    const record = asRecord(status);
    if (record === null) {
      return {};
    }
    const overall = asRecord(record["overall"]);
    if (overall !== null) {
      return overall;
    }
    return record;
  }

  function statusProviders(): Record<string, unknown> {
    const record = asRecord(status);
    if (record === null) {
      return {};
    }
    const providers = asRecord(record["per_provider"]);
    if (providers !== null) {
      return providers;
    }
    const flat = record["providers"];
    return asRecord(flat) ?? {};
  }

  function statusVersion(): string | null {
    const overall = statusOverall();
    const version = overall["kb_version"];
    return typeof version === "number" || typeof version === "string"
      ? String(version)
      : null;
  }

  function statusUpdated(): string | null {
    const overall = statusOverall();
    for (const key of ["updated_at", "last_update", "last_change_at"]) {
      const value = overall[key];
      if (typeof value === "string" && value !== "") {
        return value;
      }
    }
    return null;
  }

  function markUpToDate(): void {
    setResult({ up_to_date: true });
    setPreviews([]);
  }

  function resultIsUpToDate(): boolean {
    return asRecord(result)?.["up_to_date"] === true;
  }

  async function applyPreview(
    preview: Record<string, unknown>,
  ): Promise<Record<string, unknown> | null> {
    const proposalId = proposalIdOf(preview);
    if (proposalId === null) {
      return null;
    }
    return (await postKbJson(KB_APPLY_ROUTE, {
      proposal_id: proposalId,
      approved_by_user: true,
    })) as Record<string, unknown>;
  }

  function collectSentences(
    applied: Array<Record<string, unknown> | null>,
    staged: Record<string, unknown>[],
  ): { sentences: string[]; proposalIds: string[]; sources: unknown[] } {
    const sentences: string[] = [];
    const proposalIds: string[] = [];
    const sources: unknown[] = [];
    const seen = new Set<string>();
    for (const preview of staged) {
      for (const row of perModelOf(preview)) {
        const key = `${row.provider_id}/${row.model_id}`;
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        sentences.push(
          t("settings.capabilityDb.updatedFields", {
            count: row.fields,
            model: row.model_id,
          }),
        );
      }
      const source = preview["source"];
      if (typeof source === "string" && !sources.includes(source)) {
        sources.push(source);
      }
    }
    for (const outcome of applied) {
      const record = asRecord(outcome);
      if (record === null) {
        continue;
      }
      const proposalId = proposalIdOf(record);
      if (proposalId !== null && !proposalIds.includes(proposalId)) {
        proposalIds.push(proposalId);
      }
      for (const row of perModelOf(record)) {
        const key = `${row.provider_id}/${row.model_id}`;
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        sentences.push(
          t("settings.capabilityDb.updatedFields", {
            count: row.fields,
            model: row.model_id,
          }),
        );
      }
    }
    return { sentences, proposalIds, sources };
  }

  async function runUpdate(): Promise<void> {
    if (updating) {
      return;
    }
    setUpdating(true);
    setBusyKind("update");
    setUpdateError(null);
    try {
      const refreshed = await postKbJson(KB_UPDATE_ROUTE, {
        approved_by_user: true,
      });
      const staged = proposalsOf(refreshed);
      const legacyId = proposalIdOf(refreshed);
      if (staged.length === 0 && legacyId === null) {
        const record = asRecord(refreshed);
        if (record !== null && record["up_to_date"] === true) {
          markUpToDate();
          await refreshStatus();
          return;
        }
        setResult(refreshed);
        await refreshStatus();
        return;
      }
      if (staged.length === 0 && legacyId !== null) {
        const applied = await postKbJson(KB_APPLY_ROUTE, {
          proposal_id: legacyId,
          approved_by_user: true,
        });
        setResult({ refresh: refreshed, apply: applied });
        setPreviews([]);
        await refreshStatus();
        return;
      }
      const applied: Array<Record<string, unknown> | null> = [];
      for (const preview of staged) {
        applied.push(await applyPreview(preview));
      }
      const collected = collectSentences(applied, staged);
      setResult({
        staged: true,
        sentences: collected.sentences,
        proposalIds: collected.proposalIds,
        sources: collected.sources,
        message: messageOf(refreshed),
        applied,
      });
      setPreviews([]);
      await refreshStatus();
    } catch (error) {
      setUpdateError(errorText(error));
    } finally {
      setUpdating(false);
      setBusyKind(null);
    }
  }

  async function runCheckOnline(): Promise<void> {
    if (updating) {
      return;
    }
    setUpdating(true);
    setBusyKind("check");
    setUpdateError(null);
    try {
      const answer = asRecord(
        await postKbJson(KB_CHECK_ONLINE_ROUTE, {}),
      );
      if (answer === null) {
        return;
      }
      const staged = proposalsOf(answer);
      const providers = answer["providers"];
      setOnlineProviders(Array.isArray(providers) ? providers : []);
      const skipped = answer["skipped"];
      setOnlineSkipped(Array.isArray(skipped) ? skipped : []);
      if (staged.length === 0) {
        if (answer["up_to_date"] === true) {
          markUpToDate();
        }
        return;
      }
      setPreviews(staged);
      setResult(null);
    } catch (error) {
      setUpdateError(errorText(error));
    } finally {
      setUpdating(false);
      setBusyKind(null);
    }
  }

  function onPickFile(): void {
    fileInput.current?.click();
  }

  async function onFileChosen(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const picked = event.target.files?.[0];
    event.target.value = "";
    if (picked === undefined || updating) {
      return;
    }
    setUpdating(true);
    setBusyKind("file");
    setUpdateError(null);
    try {
      const rawText = await picked.text();
      const answer = asRecord(
        await postKbJson(KB_FILE_ROUTE, {
          file_name: picked.name,
          raw_text: rawText,
        }),
      );
      if (answer === null) {
        return;
      }
      if (answer["up_to_date"] === true) {
        setFileName(picked.name);
        markUpToDate();
        return;
      }
      const staged = asRecord(answer);
      if (staged !== null && proposalIdOf(staged) !== null) {
        setFileName(picked.name);
        setPreviews([staged]);
        setResult(null);
      }
    } catch (error) {
      setUpdateError(errorText(error));
    } finally {
      setUpdating(false);
      setBusyKind(null);
    }
  }

  async function applyStagedPreview(
    preview: Record<string, unknown>,
  ): Promise<void> {
    if (updating) {
      return;
    }
    setUpdating(true);
    setBusyKind("apply");
    setUpdateError(null);
    try {
      const applied = await applyPreview(preview);
      const collected = collectSentences(
        [asRecord(applied)],
        [preview],
      );
      setResult({
        staged: true,
        sentences: collected.sentences,
        proposalIds: collected.proposalIds,
        sources: collected.sources,
        message: messageOf(applied),
        applied: [applied],
      });
      setPreviews((current) =>
        current.filter((entry) => entry !== preview),
      );
      await refreshStatus();
    } catch (error) {
      setUpdateError(errorText(error));
    } finally {
      setUpdating(false);
      setBusyKind(null);
    }
  }

  async function rejectStagedPreview(
    preview: Record<string, unknown>,
  ): Promise<void> {
    const proposalId = proposalIdOf(preview);
    if (proposalId === null || updating) {
      return;
    }
    setUpdating(true);
    setBusyKind("reject");
    setUpdateError(null);
    try {
      await postKbJson(KB_REJECT_ROUTE, { proposal_id: proposalId });
      setPreviews((current) =>
        current.filter((entry) => entry !== preview),
      );
    } catch (error) {
      setUpdateError(errorText(error));
    } finally {
      setUpdating(false);
      setBusyKind(null);
    }
  }

  function renderStatusHeader(): ReactElement | null {
    if (status === null) {
      return null;
    }
    const version = statusVersion();
    const updated = statusUpdated();
    const providers = statusProviders();
    const providerIds = Object.keys(providers);
    return (
      <div data-testid="kb-status-line">
        {version === null ? null : (
          <p>
            {t("settings.capabilityDb.versionLine", { version })}
            {updated === null || !ISO_STAMP.test(updated)
              ? null
              : `, ${t("settings.capabilityDb.updatedLine", {
                  time: formatDateLong(updated),
                })}`}
          </p>
        )}
        {providerIds.length === 0 ? null : (
          <ul>
            {providerIds.map((provider) => (
              <li key={provider}>
                {provider}: {renderFactValue(providers[provider])}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  function renderResult(): ReactElement | null {
    if (result === null) {
      return null;
    }
    if (resultIsUpToDate()) {
      return (
        <div data-testid="kb-update-result">
          <p>{t("settings.capabilityDb.upToDate")}</p>
        </div>
      );
    }
    const record = asRecord(result);
    if (record === null) {
      return null;
    }
    const sentences = record["sentences"];
    const proposalIds = record["proposalIds"];
    const sources = record["sources"];
    if (Array.isArray(sentences) && sentences.length > 0) {
      return (
        <div data-testid="kb-update-result">
          {sentences.map((sentence, index) => (
            <p key={index}>{String(sentence)}</p>
          ))}
          {Array.isArray(proposalIds) && proposalIds.length > 0 ? (
            <p>
              {t("settings.capabilityDb.proposalsLine")}:{" "}
              {proposalIds.map(String).join("; ")}
            </p>
          ) : null}
          {Array.isArray(sources) && sources.length > 0 ? (
            <p>
              {t("settings.capabilityDb.sourcesLine")}:{" "}
              {sources.map((source, index) => (
                <span key={index}>
                  {index === 0 ? null : "; "}
                  {sourceLinkOf(source)}
                </span>
              ))}
            </p>
          ) : null}
        </div>
      );
    }
    return (
      <div data-testid="kb-update-result">
        <table>
          <tbody>
            <FactRows data={result} />
          </tbody>
        </table>
      </div>
    );
  }

  function renderPreviews(): ReactElement | null {
    if (previews.length === 0) {
      return null;
    }
    return (
      <div data-testid="kb-preview">
        {previews.map((preview, index) => (
          <div key={index} data-testid="kb-preview-row">
            <p>
              {perModelOf(preview)
                .map((row) =>
                  t("settings.capabilityDb.updatedFields", {
                    count: row.fields,
                    model: row.model_id,
                  }),
                )
                .join("; ")}
            </p>
            <p>
              {t("settings.capabilityDb.sourcesLine")}:{" "}
              {sourceLinkOf(preview["source"])}
              {typeof preview["retrieved_at"] === "string" &&
              preview["retrieved_at"] !== ""
                ? `, ${preview["retrieved_at"]}`
                : null}
            </p>
            <ChangeList preview={preview} />
            <button
              type="button"
              data-testid="kb-preview-apply"
              disabled={updating}
              onClick={() => {
                void applyStagedPreview(preview);
              }}
            >
              {t("settings.capabilityDb.apply")}
            </button>{" "}
            <button
              type="button"
              data-testid="kb-preview-reject"
              disabled={updating}
              onClick={() => {
                void rejectStagedPreview(preview);
              }}
            >
              {t("settings.capabilityDb.reject")}
            </button>
          </div>
        ))}
      </div>
    );
  }

  function renderOnline(): ReactElement | null {
    if (onlineProviders.length === 0 && onlineSkipped.length === 0) {
      return null;
    }
    return (
      <div data-testid="kb-online">
        <ul>
          {onlineProviders.map((entry, index) => {
            const record = asRecord(entry) ?? {};
            const provider =
              typeof record["provider_id"] === "string"
                ? record["provider_id"]
                : "";
            const model =
              typeof record["model_id"] === "string"
                ? String(record["model_id"])
                : "";
            const stale = record["stale"] === true;
            return (
              <li key={index}>
                {provider}/{model}:{" "}
                {stale
                  ? t("settings.capabilityDb.stale")
                  : t("settings.capabilityDb.fresh")}
              </li>
            );
          })}
        </ul>
        {onlineSkipped.length === 0 ? null : (
          <ul>
            {onlineSkipped.map((entry, index) => {
              const record = asRecord(entry) ?? {};
              return (
                <li key={index}>
                  {t("settings.capabilityDb.skipped")}:{" "}
                  {renderFactValue(record["source"])};{" "}
                  {renderFactValue(record["reason"])}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    );
  }

  const emptyPreviews = previews.length === 0 && result === null;

  return (
    <section data-testid="k07next2-kb-proposal">
      <h2>{t("firstrun.optional.kbs")}</h2>
      {status === null ? null : (
        <div data-testid="kb-status">
          {renderStatusHeader()}
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
      </button>{" "}
      <button
        type="button"
        data-testid="kb-check-online"
        disabled={updating}
        onClick={() => {
          void runCheckOnline();
        }}
      >
        {t("settings.capabilityDb.checkOnline")}
      </button>{" "}
      <button
        type="button"
        data-testid="kb-from-file"
        disabled={updating}
        onClick={onPickFile}
      >
        {t("settings.capabilityDb.fromFile")}
      </button>
      <input
        ref={fileInput}
        type="file"
        accept=".json,application/json"
        data-testid="kb-file-input"
        hidden
        onChange={(event) => {
          void onFileChosen(event);
        }}
      />
      {fileName === null ? null : <p data-testid="kb-file-name">{fileName}</p>}
      {updating ? (
        <p>
          <span
            data-testid="kb-busy"
            role="status"
            aria-label={t("chat.stream.spinner")}
            className="fx-spin"
          />
          <span>{t("chat.stream.spinner")}</span>
          {busyKind === null ? null : (
            <span> ({t(`settings.capabilityDb.busy.${busyKind}`)})</span>
          )}
        </p>
      ) : null}
      {renderResult()}
      {renderPreviews()}
      {renderOnline()}
      {updateError === null ? null : (
        <p data-testid="kb-update-error">{updateError}</p>
      )}
      {emptyPreviews && doc !== null && doc.proposals.length === 0 ? (
        <p data-testid="k07next2-kb-proposal-empty">{t("ui.table.empty")}</p>
      ) : null}
      {doc === null
        ? null
        : doc.proposals.length === 0
          ? null
          : (
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
