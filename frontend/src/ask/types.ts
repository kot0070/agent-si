// Lane A ASK-UI contract types: data shapes for the TS side, no logic.
//
// Frozen contract:
// - G4 ASK card: {askId, kind, summary, options, resumeToken}.
// - G5 SecretRef is opaque and must never appear in logs.

export type AskId = string;
export type ResumeToken = string;
export type AskKind = 'approval' | 'choice' | 'confirm';

export interface AskOption {
  optionId: string;
  label: string;
}

export interface AskCard {
  askId: AskId;
  kind: AskKind;
  summary: string;
  options: AskOption[];
  resumeToken: ResumeToken;
}

export interface ApprovalResult {
  askId: AskId;
  approvedOptionId: string;
  resumeToken: ResumeToken;
}

export interface SessionSummary {
  sessionId: string;
  title: string;
}

// G5: opaque handle; the real implementation must keep the raw value out of
// logs and serialised payloads. Branded so it cannot be confused with plain
// strings at compile time (still just a string at runtime until STEP2).
export type SecretRef = string & { readonly __secretRefBrand: unique symbol };

// Frozen snake<->camel field map (data only, no logic). Backend (Python)
// field name on the left, TS (camelCase) field name on the right.
export const SNAKE_TO_CAMEL: Record<string, string> = {
  ask_id: 'askId',
  kind: 'kind',
  summary: 'summary',
  options: 'options',
  resume_token: 'resumeToken',
  option_id: 'optionId',
  label: 'label',
  approved_option_id: 'approvedOptionId',
  session_id: 'sessionId',
  title: 'title',
  store_path: 'storePath',
  secret_ref: 'secretRef',
};
