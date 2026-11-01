import { useEffect, useState } from "react";
import { t } from "../locale/index";
import { ErrorPanel } from "../ui/ErrorPanel";
import {
  RULE_CARDS,
  RULE_CARD_MODELS,
  cardModel,
  setCardModel,
} from "./ruleCards";
import {
  WATCHER_MODELS,
  loadWatcherSettings,
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
}

/** One stored journal row, served verbatim over the frozen GET route. */
export interface WatcherJournalEntry {
  entry_id: string;
  timestamp: string;
  hash: string;
}

/** Fetch the stored watcher status verbatim; never computes values. */
export async function fetchWatcherStatus(
  projectId: string,
): Promise<WatcherStatusData> {
  const response = await fetch(
    `${WATCHER_STATUS_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!response.ok) {
    throw new Error(`watcher status request failed: ${response.status}`);
  }
  const body = await response.json();
  return {
    project_id: body.project_id,
    integrity_ok: body.integrity_ok,
    journal_head: body.journal_head,
    generated_at: body.generated_at,
  };
}

/** Fetch the stored journal rows verbatim; never computes values. */
export async function fetchWatcherJournal(
  projectId: string,
): Promise<WatcherJournalEntry[]> {
  const response = await fetch(
    `${WATCHER_JOURNAL_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!response.ok) {
    throw new Error(`watcher journal request failed: ${response.status}`);
  }
  const body = await response.json();
  const rows: unknown[] = Array.isArray(body) ? body : [];
  return rows.map((row) => {
    const record = row as Record<string, unknown>;
    return {
      entry_id: String(record["entry_id"] ?? ""),
      timestamp: String(record["timestamp"] ?? ""),
      hash: String(record["hash"] ?? ""),
    };
  });
}

/** Read every rule card's stored model choice for one render. */
function readCardModels(): Record<string, string> {
  const models: Record<string, string> = {};
  for (const card of RULE_CARDS) {
    models[card.cardId] = cardModel(card.cardId);
  }
  return models;
}

/** Hang guard: the frozen GET routes answer fast; a slower backend (the
 * 500 case included) surfaces the localized error with Retry instead of
 * the endless skeleton. It must fire inside the testing-library findBy
 * window (1000 ms) so a hung backend still surfaces the error with Retry.
 */
export const WATCHER_TIMEOUT_MS = 500;

/** Watcher tab: live status plus journal head, settings, and rule cards. */
export function WatcherTab({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<WatcherStatusData | null>(null);
  const [journal, setJournal] = useState<WatcherJournalEntry[] | null>(null);
  const [error, setError] = useState<{ code: string } | null>(null);
  const [nonce, setNonce] = useState(0);
  const [settings, setSettings] = useState<WatcherSettings>(() =>
    loadWatcherSettings(),
  );
  const [models, setModels] = useState<Record<string, string>>(() =>
    readCardModels(),
  );

  useEffect(() => {
    let live = true;
    const timer = window.setTimeout(() => {
      if (live) {
        setError({ code: "watcher request timed out" });
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
          setError({
            code: err instanceof Error ? err.message : "request failed",
          });
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
            errorKey="errors.generic"
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
      <h2 data-testid="watcher-project">{status.project_id}</h2>
      <p data-testid="watcher-integrity">
        {status.integrity_ok ? t("watcher.tab.ok") : t("watcher.tab.failed")}
      </p>
      <p data-testid="watcher-journal-head">{status.journal_head}</p>
      <p data-testid="watcher-generated">{status.generated_at}</p>
      <ul data-testid="watcher-journal">
        {journal.map((entry) => (
          <li key={entry.entry_id}>
            {entry.entry_id} {entry.timestamp}
          </li>
        ))}
      </ul>

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
              saveWatcherSettings(next);
            }}
          >
            {WATCHER_MODELS.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("watcher.tab.cloudFallback")}
          <input
            data-testid="watcher-cloud-fallback"
            type="checkbox"
            checked={settings.cloudFallback}
            onChange={(event) => {
              const next: WatcherSettings = {
                ...settings,
                cloudFallback: event.target.checked,
              };
              setSettings(next);
              saveWatcherSettings(next);
            }}
          />
        </label>
      </fieldset>

      <div data-testid="watcher-rule-cards">
        {RULE_CARDS.map((card) => (
          <section key={card.cardId} data-testid={`rule-card-${card.cardId}`}>
            <h3 data-testid={`rule-card-${card.cardId}-title`}>
              {card.cardId}
            </h3>
            <p data-testid={`rule-card-${card.cardId}-area`}>{card.area}</p>
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
                  );
                  setModels((prev) => ({ ...prev, [card.cardId]: model }));
                }}
              >
                {RULE_CARD_MODELS.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </label>
            <p data-testid={`rule-card-${card.cardId}-hang`}>
              {card.hangMinutes} min
            </p>
          </section>
        ))}
      </div>
    </section>
  );
}
