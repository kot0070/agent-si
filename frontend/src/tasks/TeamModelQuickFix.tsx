// Lane A TeamModelQuickFix: the quick-fix card for the team model binding
// (PINNED provider plus model per the K02 team card NEW side C1). Shows the
// stored binding as record data, applies it through onApply, dismisses
// through onDismiss. Every visible string resolves through the locale.
// Production caller: wave-3 App project-models route
// (CODER-5-Vale frontend/src/app/App.tsx); owned test mounts this card.

import { useState } from "react";
import type { ReactElement } from "react";
import type { RoleMode } from "../api/iface";
import { t } from "../locale/index";
import { Card } from "../ui/Card";

export interface TeamModelBinding {
  providerId: string;
  model: string;
}

export interface TeamModelQuickFixProps {
  projectId: string;
  providerId: string;
  model: string;
  mode?: RoleMode;
  onApply(binding: TeamModelBinding): void;
  onDismiss?(): void;
}

const MODE_KEYS: Record<RoleMode, string> = {
  PINNED: "settings.roleProfile.modes.pinned",
  pool: "settings.roleProfile.modes.pool",
  AUTO: "settings.roleProfile.modes.auto",
};

export function TeamModelQuickFix(props: TeamModelQuickFixProps): ReactElement {
  const [collapsed, setCollapsed] = useState(false);
  const mode: RoleMode = props.mode ?? "PINNED";
  return (
    <Card
      cardId={`team-quickfix-${props.projectId}`}
      titleKey="settings.roleProfile.title"
      collapsed={collapsed}
      onToggle={(expanded) => {
        setCollapsed(!expanded);
      }}
    >
      <div data-testid="team-quickfix">
        <span data-testid="quickfix-provider-label">
          {t("settings.roleProfile.providerLabel")}
        </span>
        <span data-testid="quickfix-provider">{props.providerId}</span>
        <span data-testid="quickfix-model-label">
          {t("settings.roleProfile.modelLabel")}
        </span>
        <span data-testid="quickfix-model">{props.model}</span>
        <span data-testid="quickfix-mode">{t(MODE_KEYS[mode])}</span>
        {/* FXBTN: one spaced action row: apply is the single primary,
            dismiss reads quiet. */}
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button
          type="button"
          data-testid="quickfix-accept"
          onClick={() => {
            props.onApply({ providerId: props.providerId, model: props.model });
          }}
        >
          {t("chat.approval.accept")}
        </button>
        {props.onDismiss === undefined ? null : (
          <button
            type="button"
            data-testid="quickfix-dismiss"
            data-variant="quiet"
            onClick={props.onDismiss}
          >
            {t("chat.approval.reject")}
          </button>
        )}
        </div>
      </div>
    </Card>
  );
}
