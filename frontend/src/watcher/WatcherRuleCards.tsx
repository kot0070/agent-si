import { useEffect, useState } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { formatScreenTime, t } from "../locale/index";
import { ErrorPanel } from "../ui/ErrorPanel";
import { RULE_CARDS, type RuleCardSpec } from "./ruleCards";
import {
  SIGNAL_TARGETS,
  WATCHER_POWERS,
  cardPower,
  cardSignal,
  isCardEnabled,
  isStrongPower,
  isWatcherEnabled,
  setCardEnabled,
  setCardPower,
  setCardSignal,
  setWatcherEnabled,
  type SignalTarget,
  type WatcherPower,
} from "./ruleOverrides";
import {
  backendRuleForCard,
  postEvaluateRule,
  verdictLocaleKey,
  type RuleEvaluationData,
} from "./watcherOps";

interface CardView {
  enabled: boolean;
  power: WatcherPower;
  whom: SignalTarget;
}

function readCardView(cardId: string, projectId: string): CardView {
  return {
    enabled: isCardEnabled(cardId, projectId),
    power: cardPower(cardId, projectId),
    whom: cardSignal(cardId, projectId),
  };
}

/** Plain WHEN line for one card: the served area text plus its window. */
export function cardWhenLine(card: RuleCardSpec): string {
  if (card.cardId === "card-hang" || card.area === "hang") {
    return `${t("watcher.tab.looksHang")} (${card.hangMinutes} min)`;
  }
  if (card.cardId === "card-guard" || card.area === "guard") {
    return t("watcher.tab.looksGuard");
  }
  return t("watcher.tab.looksTamper");
}

/** Standard script name for one area (backend rules.allowed_actions
 * formula scripts/<area>_check.py); null where no backend rule exists. */
export function cardScriptName(cardId: string, area: string): string | null {
  if (backendRuleForCard(cardId) === null) {
    return null;
  }
  return `scripts/${area}_check.py`;
}

function powerLabel(power: WatcherPower): string {
  if (power === "restart-once") {
    return t("watcher.page.powerRestart");
  }
  if (power === "pause") {
    return t("watcher.page.powerPause");
  }
  if (power === "stop") {
    return t("watcher.page.powerStop");
  }
  return t("watcher.page.powerObserve");
}

function whomLabel(whom: SignalTarget): string {
  if (whom === "manager") {
    return t("watcher.page.whomManager");
  }
  if (whom === "user") {
    return t("watcher.page.whomUser");
  }
  return t("watcher.page.whomDirector");
}

/** Rule cards (W1): WHEN, WHICH script, ALLOWED POWER, WHOM to signal,
 * on/off without code. Strong powers need a one-shot approval before
 * the Evaluate POST fires; the hang card has no backend rule, so it
 * renders a read-only note and no Evaluate control. Fetches nothing on
 * mount (evaluation fires only from the button), so the tab-level URL
 * pins stay untouched.
 */
export function WatcherRuleCards(props: {
  projectId: string;
  refreshNonce?: number;
}): React.JSX.Element {
  const [projectOn, setProjectOn] = useState<boolean>(() =>
    isWatcherEnabled(props.projectId),
  );
  const [views, setViews] = useState<Record<string, CardView>>(() =>
    Object.fromEntries(
      RULE_CARDS.map((card) => [
        card.cardId,
        readCardView(card.cardId, props.projectId),
      ]),
    ),
  );
  const [approved, setApproved] = useState<Record<string, boolean>>({});
  const [results, setResults] = useState<
    Record<string, RuleEvaluationData | null>
  >({});
  const [errors, setErrors] = useState<
    Record<string, { errorKey: string; code: string } | null>
  >({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setProjectOn(isWatcherEnabled(props.projectId));
    setViews(
      Object.fromEntries(
        RULE_CARDS.map((card) => [
          card.cardId,
          readCardView(card.cardId, props.projectId),
        ]),
      ),
    );
    setApproved({});
    setResults({});
    setErrors({});
    setBusy({});
  }, [props.projectId, props.refreshNonce]);

  function refresh(): void {
    setProjectOn(isWatcherEnabled(props.projectId));
    setViews(
      Object.fromEntries(
        RULE_CARDS.map((card) => [
          card.cardId,
          readCardView(card.cardId, props.projectId),
        ]),
      ),
    );
  }

  async function evaluate(cardId: string, ruleId: string): Promise<void> {
    setBusy((prev) => ({ ...prev, [cardId]: true }));
    setErrors((prev) => ({ ...prev, [cardId]: null }));
    try {
      const result = await postEvaluateRule(props.projectId, ruleId);
      setResults((prev) => ({ ...prev, [cardId]: result }));
      // One-shot approval: a strong power needs a fresh approval per check.
      setApproved((prev) => ({ ...prev, [cardId]: false }));
    } catch (err: unknown) {
      const code = err instanceof ApiError ? err.code : "CONTEXT_MISSING";
      setErrors((prev) => ({
        ...prev,
        [cardId]: { errorKey: apiErrorLocaleKey(code), code },
      }));
    } finally {
      setBusy((prev) => ({ ...prev, [cardId]: false }));
    }
  }

  return (
    <section data-testid="watcher-fxrules">
      <h3 data-testid="watcher-fxrules-title">
        {t("watcher.page.rulesTitle")}
      </h3>
      <label>
        {t("watcher.page.projectOn")}
        <input
          data-testid="watcher-project-enabled"
          type="checkbox"
          checked={projectOn}
          onChange={(event) => {
            setWatcherEnabled(event.target.checked, props.projectId);
            setProjectOn(event.target.checked);
          }}
        />
      </label>
      {RULE_CARDS.map((card) => {
        const view = views[card.cardId] ?? {
          enabled: true,
          power: "observe" as WatcherPower,
          whom: "director" as SignalTarget,
        };
        const strong = isStrongPower(view.power);
        const ruleId = backendRuleForCard(card.cardId);
        const script = cardScriptName(card.cardId, card.area);
        const canEvaluate =
          projectOn &&
          view.enabled &&
          ruleId !== null &&
          (!strong || approved[card.cardId] === true) &&
          busy[card.cardId] !== true;
        const result = results[card.cardId] ?? null;
        const error = errors[card.cardId] ?? null;
        return (
          <section
            key={card.cardId}
            data-testid={`watchcard-${card.cardId}`}
          >
            <h4 data-testid={`watchcard-${card.cardId}-title`}>
              {card.cardId}
            </h4>
            <dl>
              <dt>{t("watcher.page.when")}</dt>
              <dd data-testid={`watchcard-${card.cardId}-when`}>
                {cardWhenLine(card)}
              </dd>
              <dt>{t("watcher.page.which")}</dt>
              <dd data-testid={`watchcard-${card.cardId}-script`}>
                {script ?? t("watcher.tab.notKnown")}
              </dd>
              <dt>{t("watcher.page.power")}</dt>
              <dd>
                <select
                  data-testid={`watchcard-${card.cardId}-power`}
                  value={view.power}
                  onChange={(event) => {
                    const next = event.target.value as WatcherPower;
                    if (!WATCHER_POWERS.includes(next)) {
                      return;
                    }
                    setCardPower(card.cardId, next, props.projectId);
                    setViews((prev) => ({
                      ...prev,
                      [card.cardId]: {
                        ...(prev[card.cardId] ?? view),
                        power: next,
                      },
                    }));
                    setApproved((prev) => ({ ...prev, [card.cardId]: false }));
                  }}
                >
                  {WATCHER_POWERS.map((power) => (
                    <option key={power} value={power}>
                      {powerLabel(power)}
                    </option>
                  ))}
                </select>
              </dd>
              <dt>{t("watcher.page.whom")}</dt>
              <dd>
                <select
                  data-testid={`watchcard-${card.cardId}-whom`}
                  value={view.whom}
                  onChange={(event) => {
                    const next = event.target.value as SignalTarget;
                    if (!SIGNAL_TARGETS.includes(next)) {
                      return;
                    }
                    setCardSignal(card.cardId, next, props.projectId);
                    setViews((prev) => ({
                      ...prev,
                      [card.cardId]: {
                        ...(prev[card.cardId] ?? view),
                        whom: next,
                      },
                    }));
                  }}
                >
                  {SIGNAL_TARGETS.map((target) => (
                    <option key={target} value={target}>
                      {whomLabel(target)}
                    </option>
                  ))}
                </select>
              </dd>
              <dt>
                {view.enabled ? t("watcher.page.on") : t("watcher.page.off")}
              </dt>
              <dd>
                <input
                  data-testid={`watchcard-${card.cardId}-enabled`}
                  type="checkbox"
                  checked={view.enabled}
                  aria-label={card.cardId}
                  onChange={(event) => {
                    setCardEnabled(
                      card.cardId,
                      event.target.checked,
                      props.projectId,
                    );
                    refresh();
                  }}
                />
              </dd>
            </dl>
            {strong ? (
              <p data-testid={`watchcard-${card.cardId}-approval-note`}>
                {t("watcher.page.approvalNote")}
              </p>
            ) : null}
            {strong && view.enabled ? (
              <label>
                {t("watcher.page.approveOne")}
                <input
                  data-testid={`watchcard-${card.cardId}-approve`}
                  type="checkbox"
                  checked={approved[card.cardId] === true}
                  onChange={(event) => {
                    setApproved((prev) => ({
                      ...prev,
                      [card.cardId]: event.target.checked,
                    }));
                  }}
                />
              </label>
            ) : null}
            {ruleId !== null ? (
              <>
                <button
                  type="button"
                  data-testid={`watchcard-${card.cardId}-evaluate`}
                  disabled={!canEvaluate}
                  onClick={() => {
                    void evaluate(card.cardId, ruleId);
                  }}
                >
                  {t("watcher.page.evaluate")}
                </button>
                {!view.enabled || !projectOn ? (
                  <p data-testid={`watchcard-${card.cardId}-off-note`}>
                    {t("watcher.page.evaluateOffNote")}
                  </p>
                ) : null}
              </>
            ) : (
              <p data-testid={`watchcard-${card.cardId}-no-backend`}>
                {t("watcher.page.noBackendNote")}
              </p>
            )}
            {result !== null ? (
              <p data-testid={`watchcard-${card.cardId}-result`}>
                {t(verdictLocaleKey(result.verdict))} ·{" "}
                {t("watcher.page.journalRow")}: {result.journal_entry_id} ·{" "}
                {result.decided_at !== ""
                  ? formatScreenTime(result.decided_at)
                  : t("watcher.tab.notKnown")}
              </p>
            ) : null}
            {error !== null ? (
              <div data-testid={`watchcard-${card.cardId}-error`}>
                <ErrorPanel
                  errorKey={error.errorKey}
                  code={error.code}
                  onRetry={() => {
                    if (ruleId !== null) {
                      void evaluate(card.cardId, ruleId);
                    }
                  }}
                />
              </div>
            ) : null}
          </section>
        );
      })}
    </section>
  );
}
