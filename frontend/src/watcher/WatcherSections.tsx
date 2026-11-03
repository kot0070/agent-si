import { useState } from "react";
import { WatcherAlerts } from "./WatcherAlerts";
import { WatcherApps } from "./WatcherApps";
import { WatcherPresets } from "./WatcherPresets";
import { WatcherRuleCards } from "./WatcherRuleCards";

/** Watcher page extensions (FXWATCHUI): rule cards, presets, alerts,
 * apps and services. One component so the tab wiring stays one line.
 * Nothing here fetches on mount: every network call starts from an
 * explicit button, and presets plus overrides persist locally.
 */
export function WatcherSections(props: { projectId: string }): React.JSX.Element {
  const [presetNonce, setPresetNonce] = useState(0);
  return (
    <div data-testid="watcher-sections">
      <WatcherRuleCards
        projectId={props.projectId}
        refreshNonce={presetNonce}
      />
      <WatcherPresets
        projectId={props.projectId}
        onPresetApplied={() => {
          setPresetNonce((value) => value + 1);
        }}
      />
      <WatcherAlerts projectId={props.projectId} />
      <WatcherApps projectId={props.projectId} />
    </div>
  );
}
