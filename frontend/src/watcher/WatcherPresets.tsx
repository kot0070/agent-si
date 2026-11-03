import { useEffect, useState } from "react";
import { t } from "../locale/index";
import { RULE_CARDS } from "./ruleCards";
import { setCardEnabled } from "./ruleOverrides";
import {
  WATCHER_PRESETS,
  loadWatcherPreset,
  presetCards,
  saveWatcherPreset,
  type WatcherPresetId,
} from "./watcherPresetStore";

/** One-click watcher presets: the current one marked, plain change lines.
 *
 * There is no preset HTTP route, so the choice persists per project in
 * localStorage and switching a preset flips the rule-card on/off flags
 * to the preset's cards (that flip is the wired effect). Fetches
 * nothing, so the tab-level URL pins stay untouched.
 */
export function WatcherPresets(props: {
  projectId: string;
  onPresetApplied?: () => void;
}): React.JSX.Element {
  const [preset, setPreset] = useState<WatcherPresetId>(() =>
    loadWatcherPreset(props.projectId),
  );

  useEffect(() => {
    setPreset(loadWatcherPreset(props.projectId));
  }, [props.projectId]);

  function presetName(id: WatcherPresetId): string {
    if (id === "cautious") {
      return t("watcher.page.presetCautious");
    }
    if (id === "strict") {
      return t("watcher.page.presetStrict");
    }
    return t("watcher.page.presetStandard");
  }

  function presetLine(id: WatcherPresetId): string {
    if (id === "cautious") {
      return t("watcher.page.presetCautiousLine");
    }
    if (id === "strict") {
      return t("watcher.page.presetStrictLine");
    }
    return t("watcher.page.presetStandardLine");
  }

  function apply(next: WatcherPresetId): void {
    saveWatcherPreset(next, props.projectId);
    const wanted = presetCards(next);
    for (const card of RULE_CARDS) {
      setCardEnabled(card.cardId, wanted.includes(card.cardId), props.projectId);
    }
    setPreset(next);
    props.onPresetApplied?.();
  }

  return (
    <section data-testid="watcher-presets">
      <h3 data-testid="watcher-presets-title">{t("watcher.page.presetsTitle")}</h3>
      {WATCHER_PRESETS.map((id) => {
        const current = id === preset;
        return (
          <div key={id}>
            <button
              type="button"
              data-testid={`watcher-preset-${id}`}
              aria-pressed={current}
              onClick={() => {
                apply(id);
              }}
            >
              {presetName(id)}
              {current ? ` (${t("watcher.page.current")})` : ""}
            </button>
            <p data-testid={`watcher-preset-${id}-line`}>{presetLine(id)}</p>
          </div>
        );
      })}
    </section>
  );
}
