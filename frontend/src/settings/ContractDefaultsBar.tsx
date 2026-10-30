// OC-K07 (ARCH-720): confirmation bar for the effective agent contract
// defaults of one role. Reads the stored profile over the real server
// path (readRoleProfile: server first, cache fallback); shows CONFIRMED
// with the effective defaults, or the missing shape fields with the
// generic error line. Rendered in the settings project section next to
// the role editor, so defaults are confirmed before the role is used.

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { LoadingState } from "../ui/LoadingState";
import { readRoleProfile } from "./index";
import type { RoleMode, RoleModelProfile } from "./index";
import { confirmStoredProfile } from "./contractDefaults";

export interface ContractDefaultsBarProps {
  projectId: string;
  role: string;
}

function modeLabel(mode: RoleMode): string {
  if (mode === "PINNED") {
    return t("settings.roleProfile.modes.pinned");
  }
  if (mode === "pool") {
    return t("settings.roleProfile.modes.pool");
  }
  return t("settings.roleProfile.modes.auto");
}

export function ContractDefaultsBar(
  props: ContractDefaultsBarProps,
): ReactElement {
  const [profile, setProfile] = useState<RoleModelProfile | undefined | null>(
    null,
  );
  useEffect(() => {
    let alive = true;
    void readRoleProfile(props.projectId, props.role)
      .then((saved) => {
        if (alive) {
          setProfile(saved === undefined ? undefined : saved);
        }
      })
      .catch(() => {
        if (alive) {
          setProfile(undefined);
        }
      });
    return () => {
      alive = false;
    };
  }, [props.projectId, props.role]);
  if (profile === null) {
    return (
      <div data-testid="contract-defaults-bar">
        <LoadingState loadingKey="ui.loading.more" />
      </div>
    );
  }
  const result = confirmStoredProfile(profile);
  if (!result.confirmed || result.defaults === null) {
    return (
      <div data-testid="contract-defaults-bar">
        <span>{t("settings.roleProfile.title")}</span>
        <span data-testid="contract-defaults-missing">
          {t("errors.generic")}
        </span>
        <ul>
          {result.missing.map((field) => (
            <li key={field}>{field}</li>
          ))}
        </ul>
      </div>
    );
  }
  const defaults = result.defaults;
  return (
    <div data-testid="contract-defaults-bar">
      <span>{t("settings.roleProfile.title")}</span>
      <span data-testid="contract-defaults-confirmed">
        {modeLabel(defaults.mode)}
      </span>
      <ul>
        <li>
          {t("settings.roleProfile.providerLabel")}: {defaults.provider ?? "—"}
        </li>
        <li>
          {t("settings.roleProfile.modelLabel")}: {defaults.model ?? "—"}
        </li>
      </ul>
    </div>
  );
}
