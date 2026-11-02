// Lane A ApprovalCard: the three-button decision card for a completed chat
// proposal (accept, edit, reject). Every visible string resolves through the
// locale; the proposal itself is record data. Production caller: ChatArea in
// frontend/src/chat/index.tsx (wave-3 App chat route mounts ChatArea).

import { useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";

export interface ApprovalCardProps {
  proposal: string;
  onAccept(): void;
  onEdit(next: string): void;
  onReject(): void;
}

export function ApprovalCard(props: ApprovalCardProps): ReactElement {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(props.proposal);
  return (
    <div data-testid="approval-card">
      <p data-testid="approval-text">{props.proposal}</p>
      {editing ? (
        <div>
          <textarea
            data-testid="approval-edit-field"
            aria-label={t("chat.approval.edit")}
            value={editText}
            onChange={(event) => {
              setEditText(event.target.value);
            }}
          />
          <button
            type="button"
            data-testid="approval-edit-save"
            onClick={() => {
              props.onEdit(editText);
              setEditing(false);
            }}
          >
            {t("chat.composer.send")}
          </button>
        </div>
      ) : null}
      <button
        type="button"
        data-testid="approval-accept"
        onClick={props.onAccept}
      >
        {t("chat.approval.accept")}
      </button>
      {/* FXDESIGN5 S4: accept is the single primary; edit and reject
          read as quiet secondaries. */}
      <button
        type="button"
        data-testid="approval-edit"
        className="fx-btn-quiet"
        onClick={() => {
          setEditText(props.proposal);
          setEditing(true);
        }}
      >
        {t("chat.approval.edit")}
      </button>
      <button
        type="button"
        data-testid="approval-reject"
        className="fx-btn-quiet"
        onClick={props.onReject}
      >
        {t("chat.approval.reject")}
      </button>
    </div>
  );
}
