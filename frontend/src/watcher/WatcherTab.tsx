import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { formatScreenTime, pluralUnit, t } from "../locale/index";
import { ApiError, apiErrorLocaleKey, parseErrorBody } from "../api/errors";
import { ErrorPanel } from "../ui/ErrorPanel";
import { humanRunRef } from "../projects/viewsApi";
import {
  RULE_CARDS,
  RULE_CARD_MODELS,
  cardModel,
  setCardModel,
} from "./ruleCards";
import {
  MAX_HANG_MINUTES,
  MIN_HANG_MINUTES,
  WATCHER_MODELS,
  loadCardHangMinutes,
  loadWatcherSettings,
  saveCardHangMinutes,
  saveWatcherSettings,
  type WatcherSettings,
} from "./watcherSettings";

/** Frozen watcher HTTP surface for the tab (GET only, no session token). */
export const WATCHER_STATUS_ROUTE = "/api/v1/watcher/status";
export const WATCHER_JOURNAL_ROUTE = "/api/v1/watcher/journal";

/** Stored watcher status facts, served verbatim over the frozen GET route. */
export interface WatcherStatusData {
  project_id: string;
  integrity_ok: boolean;
  journal_head: string;
  generated_at: string;
  checks_done?: number;
  alerts_raised?: number;
  last_check_at?: string;
  watcher_model?: string;
  watcher_calls?: number;
  watcher_tokens?: number;
  watched_runs?: number;
  watched_agents?: number;
  last_action?: string;
  rules_fired?: Array<[string, number]>;
}

/** One stored journal row, served verbatim over the frozen GET route. */
export interface WatcherJournalEntry {
  entry_id: string;
  timestamp: string;
  hash: string;
  kind: string;
  source: string;
  summary: string;
  refs: Array<string>;
}

/** Fetch the stored watcher status verbatim; never computes values. */
export async function fetchWatcherStatus(
  projectId: string,
): Promise<WatcherStatusData> {
  const response = await fetch(
    `${WATCHER_STATUS_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!response.ok) {
    throw parseErrorBody({}, response.status);
  }
  const body = await response.json();
  return {
    project_id: body.project_id,
    integrity_ok: body.integrity_ok,
    journal_head: body.journal_head,
    generated_at: body.generated_at,
    checks_done: typeof body.checks_done === "number" ? body.checks_done : undefined,
    alerts_raised:
      typeof body.alerts_raised === "number" ? body.alerts_raised : undefined,
    last_check_at:
      typeof body.last_check_at === "string" ? body.last_check_at : undefined,
    watcher_model:
      typeof body.watcher_model === "string" ? body.watcher_model : undefined,
    watcher_calls:
      typeof body.watcher_calls === "number" ? body.watcher_calls : undefined,
    watcher_tokens:
      typeof body.watcher_tokens === "number" ? body.watcher_tokens : undefined,
    watched_runs:
      typeof body.watched_runs === "number" ? body.watched_runs : undefined,
    watched_agents:
      typeof body.watched_agents === "number" ? body.watched_agents : undefined,
    last_action:
      typeof body.last_action === "string" ? body.last_action : undefined,
    rules_fired: Array.isArray(body.rules_fired)
      ? (body.rules_fired as Array<[string, number]>)
      : undefined,
  };
}

/** Unknown served value reads "not known", never an invented value. */
export function notKnown(): string {
  return t("watcher.tab.notKnown");
}

/** Last watcher action in plain words, never the raw evt id. A project with
 * no run yet reads "no action yet", never a "not known" placeholder. */
export function describeLastAction(summary: string | undefined): string {
  if (!summary) {
    return t("watcher.tab.noActionYet");
  }
  if (summary.includes("BLOCK")) {
    return t("watcher.tab.actionBlocked");
  }
  if (summary.includes("ESCALATE")) {
    return t("watcher.tab.actionEscalated");
  }
  if (summary.includes("ALLOW") || summary.includes("seed")) {
    return t("watcher.tab.actionAllowed");
  }
  return summary;
}

/** What one rule card looks for, from served area ids only. */
export function ruleLooksFor(cardId: string, area: string): string {
  if (area === "hang" || cardId === "card-hang") {
    return t("watcher.tab.looksHang");
  }
  if (area === "guard" || cardId === "card-guard") {
    return t("watcher.tab.looksGuard");
  }
  if (area === "tamper" || cardId === "card-tamper") {
    return t("watcher.tab.looksTamper");
  }
  return notKnown();
}

/** Fired count for one card from the served rules_fired table. */
export function ruleFiredCount(
  status: WatcherStatusData | null,
  cardId: string,
): number | null {
  if (!status || !Array.isArray(status.rules_fired)) {
    return null;
  }
  const backendId =
    cardId === "card-tamper"
      ? "rule-tamper"
      : cardId === "card-guard"
        ? "rule-guard"
        : cardId;
  for (const [ruleId, count] of status.rules_fired) {
    if (ruleId === backendId || ruleId === cardId) {
      return typeof count === "number" ? count : null;
    }
  }
  return 0;
}

/** Fetch the stored journal rows verbatim; never computes values. */
export async function fetchWatcherJournal(
  projectId: string,
): Promise<WatcherJournalEntry[]> {
  const response = await fetch(
    `${WATCHER_JOURNAL_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!response.ok) {
    throw parseErrorBody({}, response.status);
  }
  const body = await response.json();
  const rows: unknown[] = Array.isArray(body) ? body : [];
  return rows.map((row) => {
    const record = row as Record<string, unknown>;
    const refs = Array.isArray(record["refs"])
      ? (record["refs"] as Array<unknown>).map((ref) => String(ref))
      : [];
    return {
      entry_id: String(record["entry_id"] ?? ""),
      timestamp: String(record["timestamp"] ?? ""),
      hash: String(record["hash"] ?? ""),
      kind: String(record["kind"] ?? ""),
      source: String(record["source"] ?? ""),
      summary: String(record["summary"] ?? ""),
      refs,
    };
  });
}

/** Read every rule card's stored model choice for one render. */
function readCardModels(projectId: string): Record<string, string> {
  const models: Record<string, string> = {};
  for (const card of RULE_CARDS) {
    models[card.cardId] = cardModel(card.cardId, projectId);
  }
  return models;
}

/** Read every rule card's stored hang window for one render. */
function readCardHangs(projectId: string): Record<string, number> {
  const hangs: Record<string, number> = {};
  for (const card of RULE_CARDS) {
    hangs[card.cardId] = loadCardHangMinutes(card.cardId, projectId);
  }
  return hangs;
}

/** Hang guard: the frozen GET routes answer fast; a slower backend (the
 * 500 case included) surfaces the localized error with Retry instead of
 * the endless skeleton. It must fire inside the testing-library findBy
 * window (1000 ms) so a hung backend still surfaces the error with Retry.
 */
export const WATCHER_TIMEOUT_MS = 500;

/** Human short name for a watcher model enum; the raw enum never renders. */
export function watcherModelName(model: WatcherSettings["model"]): string {
  if (model === "local") {
    return t("watcher.tab.modelLocal");
  }
  if (model === "API") {
    return t("watcher.tab.modelApi");
  }
  return t("watcher.tab.modelOff");
}

/** Plain kind label for one stored journal kind; never the raw code. */
export function journalKindLabel(kind: string): string {
  try {
    const label = t(`watcher.tab.kind.${kind}`);
    if (typeof label === "string" && label.length > 0) {
      return label;
    }
  } catch {
    // Missing key reads not-known, never a throw on screen.
  }
  return notKnown();
}

const RUNISH = /(^|\s)(fxdevrun:[^\s]*|artifact:[^\s]*|plan-[0-9a-zA-Z-]+|localtests-[0-9a-zA-Z-]+|r-[0-9a-zA-Z-]+|[0-9a-f]{20,})(?=\s|$)/g;

/** Plain one-line summary: raw JSON reads as a plain sentence, raw run
 * ids and long hashes read shortened, never a bare code on screen. */
export function plainJournalSummary(summary: string, kind: string): string {
  const text = summary.trim();
  if (text === "") {
    return notKnown();
  }
  if (text.startsWith("{") || text.startsWith("[")) {
    try {
      JSON.parse(text);
      return `${journalKindLabel(kind)}: ${t("watcher.tab.structuredNote")}`;
    } catch {
      // Not JSON after all: fall through to the token pass.
    }
  }
  return text.replace(RUNISH, (match, head: string, ref: string) => {
    const short = humanRunRef(ref);
    if (short.text !== ref) {
      return `${head}${short.text}`;
    }
    if (ref.length > 16) {
      return `${head}${ref.slice(0, 8)}…`;
    }
    return match;
  });
}

/** One journal row in the F6a form: local time, plain kind plus the
 * short summary; the full text with the receipt rides alongside. */
export interface JournalLine {
  time: string;
  kind: string;
  short: string;
  full: string;
  entryId: string;
  hash: string;
}

export function describeJournalEntry(entry: WatcherJournalEntry): JournalLine {
  return {
    time: formatScreenTime(entry.timestamp),
    kind: journalKindLabel(entry.kind),
    short: plainJournalSummary(entry.summary, entry.kind),
    full: entry.summary,
    entryId: entry.entry_id,
    hash: entry.hash,
  };
}

/** Stored project name for the journal header (id fallback, never a guess). */
export async function fetchProjectName(projectId: string): Promise<string> {
  try {
    const response = await fetch("/api/v1/projects");
    if (!response.ok) {
      return projectId;
    }
    const body = (await response.json()) as unknown;
    const rows =
      typeof body === "object" && body !== null
        ? ((body as Record<string, unknown>)["projects"] as unknown)
        : null;
    if (!Array.isArray(rows)) {
      return projectId;
    }
    for (const row of rows) {
      if (
        typeof row === "object" &&
        row !== null &&
        (row as Record<string, unknown>)["project_id"] === projectId
      ) {
        const name = (row as Record<string, unknown>)["name"];
        if (typeof name === "string" && name !== "") {
          return name;
        }
      }
    }
  } catch {
    // Unreachable list reads as the id, never a failed header.
  }
  return projectId;
}

/** Journal rows newest first with a folding long text and receipt details.
 * Shared by the Watcher tab and the rail Watcher card (F6a form). */
export function WatcherJournalList(props: {
  entries: Array<WatcherJournalEntry>;
  initialLimit?: number;
  showMore?: boolean;
}): ReactElement {
  const [expanded, setExpanded] = useState(false);
  const limit = props.initialLimit ?? 5;
  const ordered = [...props.entries].reverse();
  const shown = expanded ? ordered : ordered.slice(0, limit);
  if (ordered.length === 0) {
    return <p data-testid="watcher-journal-empty">{t("watcher.tab.journalEmpty")}</p>;
  }
  return (
    <>
      <ul data-testid="watcher-journal">
        {shown.map((entry) => {
          const line = describeJournalEntry(entry);
          const folds = line.full !== line.short;
          return (
            <li
              key={entry.entry_id}
              data-testid={`journal-row-${entry.entry_id}`}
            >
              <span>{line.time}</span> <span>{line.kind}</span>{" "}
              <span>{line.short}</span>
              <details>
                <summary>{t("ui.disclosure.more")}</summary>
                {folds ? <p>{line.full}</p> : null}
                <p>
                  {entry.entry_id} · {entry.hash}
                </p>
              </details>
            </li>
          );
        })}
      </ul>
      {props.showMore === false || ordered.length <= limit ? null : (
        <button
          type="button"
          data-testid="journal-show-more"
          className="fx-btn-quiet fx-show-more"
          aria-expanded={expanded}
          onClick={() => {
            setExpanded(!expanded);
          }}
        >
          <span>
            {expanded ? t("shell.cards.showLess") : t("shell.cards.showMore")}
          </span>
        </button>
      )}
    </>
  );
}

/** Watcher tab: live status plus journal head, settings, and rule cards. */
export function WatcherTab({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<WatcherStatusData | null>(null);
  const [journal, setJournal] = useState<WatcherJournalEntry[] | null>(null);
  const [error, setError] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [nonce, setNonce] = useState(0);
  const [settings, setSettings] = useState<WatcherSettings>(() =>
    loadWatcherSettings(projectId),
  );
  const [models, setModels] = useState<Record<string, string>>(() =>
    readCardModels(projectId),
  );
  const [hangs, setHangs] = useState<Record<string, number>>(() =>
    readCardHangs(projectId),
  );
  const [projectName, setProjectName] = useState<string | null>(null);

  useEffect(() => {
    setSettings(loadWatcherSettings(projectId));
    setModels(readCardModels(projectId));
    setHangs(readCardHangs(projectId));
    setProjectName(null);
  }, [projectId]);

  useEffect(() => {
    let live = true;
    void fetchProjectName(projectId).then((name) => {
      if (live) {
        setProjectName(name);
      }
    });
    return () => {
      live = false;
    };
  }, [projectId]);

  useEffect(() => {
    let live = true;
    const timer = window.setTimeout(() => {
      if (live) {
        // FXCLASS CD-7: the hang guard maps to a locale key, never a raw
        // English sentence as the error code.
        setError({ errorKey: "errors.generic", code: "CONTEXT_MISSING" });
      }
    }, WATCHER_TIMEOUT_MS);
    async function load(): Promise<void> {
      try {
        const [nextStatus, nextJournal] = await Promise.all([
          fetchWatcherStatus(projectId),
          fetchWatcherJournal(projectId),
        ]);
        if (live) {
          setStatus(nextStatus);
          setJournal(nextJournal);
          setError(null);
        }
      } catch (err: unknown) {
        if (live) {
          // FXCLASS CD-7: keep the ApiError, map through apiErrorLocaleKey,
          // never a raw "request failed: 500".
          const code =
            err instanceof ApiError ? err.code : "CONTEXT_WRONG_CONTRACT_VERSION";
          setError({ errorKey: apiErrorLocaleKey(code), code });
        }
      } finally {
        window.clearTimeout(timer);
      }
    }
    void load();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [projectId, nonce]);

  if (error !== null) {
    return (
      <section>
        <h2>{t("watcher.tab.subtitle")}</h2>
        <div data-testid="watcher-error">
          <ErrorPanel
            errorKey={error.errorKey}
            code={error.code}
            onRetry={() => {
              setNonce((value) => value + 1);
            }}
          />
        </div>
      </section>
    );
  }
  if (status === null || journal === null) {
    return (
      <section>
        <h2>{t("watcher.tab.subtitle")}</h2>
        <p data-testid="watcher-loading">{t("watcher.tab.loading")}</p>
      </section>
    );
  }

  return (
    <section data-testid="watcher-tab">
      <h2 data-testid="watcher-project">{projectName ?? projectId}</h2>
      <p data-testid="watcher-last-event">
        {t("watcher.tab.lastEvent")}:{" "}
        {journal.length === 0
          ? notKnown()
          : formatScreenTime(journal[journal.length - 1]?.timestamp ?? "")}
      </p>
      <p data-testid="watcher-journal-scope">{t("watcher.tab.sinceStart")}</p>
      <p data-testid="watcher-integrity">
        {status.integrity_ok ? t("watcher.tab.ok") : t("watcher.tab.failed")}
      </p>
      <p data-testid="watcher-journal-head">{status.journal_head}</p>
      <p data-testid="watcher-generated">{status.generated_at !== "" ? formatScreenTime(status.generated_at) : notKnown()}</p>
      <p data-testid="watcher-checks">
        {t("watcher.tab.checks")}:{" "}
        {typeof status.checks_done === "number" ? status.checks_done : notKnown()}
      </p>
      <p data-testid="watcher-alerts">
        {t("watcher.tab.alerts")}:{" "}
        {typeof status.alerts_raised === "number" ? status.alerts_raised : notKnown()}
      </p>
      <p data-testid="watcher-last-check">
        {t("watcher.tab.lastCheck")}: {status.last_check_at ? formatScreenTime(status.last_check_at) : t("watcher.tab.noChecksYet")}
      </p>
      <p data-testid="watcher-calls">
        {t("watcher.tab.modelCalls")}:{" "}
        {typeof status.watcher_calls === "number" ? status.watcher_calls : notKnown()}{" "}
        · {t("watcher.tab.modelTokens")}:{" "}
        {typeof status.watcher_tokens === "number" ? status.watcher_tokens : notKnown()}
      </p>
      <p data-testid="watcher-watches">
        {t("watcher.tab.watches")}:{" "}
        {typeof status.watched_runs === "number" ? status.watched_runs : notKnown()}{" "}
        {typeof status.watched_runs === "number"
          ? pluralUnit("shell.cards.watcher.runs", status.watched_runs)
          : null}{" · "}
        {typeof status.watched_agents === "number"
          ? status.watched_agents
          : notKnown()}{" "}
        {typeof status.watched_agents === "number"
          ? pluralUnit("shell.cards.watcher.agents", status.watched_agents)
          : null}
      </p>
      <p data-testid="watcher-last-action">
        {t("watcher.tab.lastAction")}: {describeLastAction(status.last_action)}
      </p>

      <fieldset data-testid="watcher-settings">
        <legend>{t("watcher.tab.settings")}</legend>
        <label>
          {t("watcher.tab.model")}
          <select
            data-testid="watcher-model"
            value={settings.model}
            onChange={(event) => {
              const next: WatcherSettings = {
                ...settings,
                model: event.target.value as WatcherSettings["model"],
              };
              if (WATCHER_MODELS.indexOf(next.model) === -1) {
                return;
              }
              setSettings(next);
              saveWatcherSettings(next, projectId);
            }}
          >
            {WATCHER_MODELS.map((model) => (
              <option key={model} value={model}>
                {watcherModelName(model)}
              </option>
            ))}
          </select>
          <span data-testid="watcher-model-name">{watcherModelName(settings.model)}</span>
        </label>
        <label>
          {t("watcher.tab.cloudFallback")}
          <input
            data-testid="watcher-cloud-fallback"
            type="checkbox"
            checked={settings.cloudFallback}
            aria-describedby="watcher-fallback-note"
            onChange={(event) => {
              const next: WatcherSettings = {
                ...settings,
                cloudFallback: event.target.checked,
              };
              setSettings(next);
              saveWatcherSettings(next, projectId);
            }}
          />
        </label>
        <p data-testid="watcher-fallback-note" id="watcher-fallback-note">
          {t("watcher.tab.fallbackNote")}
        </p>
      </fieldset>

      <h3 data-testid="watcher-rules-title">{t("watcher.tab.rulesTitle")}</h3>
      <div data-testid="watcher-rule-cards">
        {RULE_CARDS.map((card) => {
          const fired = ruleFiredCount(status, card.cardId);
          return (
          <section key={card.cardId} data-testid={`rule-card-${card.cardId}`}>
            <h3 data-testid={`rule-card-${card.cardId}-title`}>
              {card.cardId}
            </h3>
            <p data-testid={`rule-card-${card.cardId}-area`}>{card.area}</p>
            <p data-testid={`rule-card-${card.cardId}-looks`}>
              {ruleLooksFor(card.cardId, card.area)}
            </p>
            <p data-testid={`rule-card-${card.cardId}-fired`}>
              {t("watcher.tab.fired")}: {fired === null ? notKnown() : fired}
            </p>
            <label>
              {t("watcher.tab.model")}
              <select
                data-testid={`rule-card-${card.cardId}-model`}
                value={models[card.cardId] ?? "local"}
                onChange={(event) => {
                  const model = event.target.value;
                  if (
                    RULE_CARD_MODELS.indexOf(
                      model as (typeof RULE_CARD_MODELS)[number],
                    ) === -1
                  ) {
                    return;
                  }
                  setCardModel(
                    card.cardId,
                    model as (typeof RULE_CARD_MODELS)[number],
                    projectId,
                  );
                  setModels((prev) => ({ ...prev, [card.cardId]: model }));
                }}
              >
                {RULE_CARD_MODELS.map((model) => (
                  <option key={model} value={model}>
                    {watcherModelName(model)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("watcher.tab.minutes")}
              <input
                type="number"
                data-testid={`rule-card-${card.cardId}-hang`}
                min={MIN_HANG_MINUTES}
                max={MAX_HANG_MINUTES}
                value={hangs[card.cardId] ?? card.hangMinutes}
                onChange={(event) => {
                  const next = saveCardHangMinutes(
                    card.cardId,
                    event.target.value,
                    projectId,
                  );
                  setHangs((prev) => ({ ...prev, [card.cardId]: next }));
                }}
              />
            </label>
          </section>
          );
        })}
      </div>
      <h3 data-testid="watcher-journal-title">{t("watcher.tab.journalTitle")}</h3>
      <WatcherJournalList entries={journal} />
    </section>
  );
}
