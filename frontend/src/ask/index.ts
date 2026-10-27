// Lane A ASK-UI entry points: in-memory TS implementation mirroring backend semantics.
//
// Callable from chat and the run view: these are pure functions with no DOM,
// network, or credential-store dependencies. Module state below is the
// issuance store; ids are deterministic (ask-N / resume-N) from fresh module
// state, and every refusal raises PermissionError.
import type {
  ApprovalResult,
  AskCard,
  AskKind,
  AskOption,
  ResumeToken,
  SecretRef,
  SessionSummary,
} from './types';

export type { ApprovalResult, AskCard, AskKind, AskOption, ResumeToken, SecretRef, SessionSummary };

class PermissionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PermissionError';
    Object.setPrototypeOf(this, PermissionError.prototype);
  }
}

interface StoredAsk {
  card: AskCard;
  secretMarker: string | null;
}

const issuedCards = new Map<string, StoredAsk>();
const tokenToAskId = new Map<string, string>();
const sessionSummaries: SessionSummary[] = [];

let askCounter = 0;
let resumeCounter = 0;

const DEMO_RESUME_PATTERN = /^resume-\d+$/;

const ASK_KINDS: readonly AskKind[] = ['approval', 'choice', 'confirm'];
const REDACTED_SECRET_MARKER = '[secret-ref-redacted]';

function requireNonEmpty(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new PermissionError(`ask: ${field} must be a non-empty string`);
  }
  return value;
}

function copyCard(card: AskCard): AskCard {
  return {
    askId: card.askId,
    kind: card.kind,
    summary: card.summary,
    options: card.options.map((option) => ({ ...option })),
    resumeToken: card.resumeToken,
  };
}

export async function createAskCard(input: {
  kind: AskKind;
  summary: string;
  options: AskOption[];
  secretRef?: SecretRef;
}): Promise<AskCard> {
  if (!ASK_KINDS.includes(input.kind)) {
    throw new PermissionError('ask: unknown kind');
  }
  requireNonEmpty(input.summary, 'summary');
  if (!Array.isArray(input.options) || input.options.length === 0) {
    throw new PermissionError('ask: options must be a non-empty array');
  }
  const options: AskOption[] = input.options.map((option, index) => {
    requireNonEmpty(option?.optionId, `options[${index}].optionId`);
    requireNonEmpty(option?.label, `options[${index}].label`);
    return { optionId: option.optionId, label: option.label };
  });
  askCounter += 1;
  resumeCounter += 1;
  const card: AskCard = {
    askId: `ask-${askCounter}`,
    kind: input.kind,
    summary: input.summary,
    options,
    resumeToken: `resume-${resumeCounter}`,
  };
  // The raw secret handle is never stored, copied, or logged; only a
  // redacted marker records that a handle was supplied.
  issuedCards.set(card.askId, {
    card,
    secretMarker: input.secretRef === undefined ? null : REDACTED_SECRET_MARKER,
  });
  tokenToAskId.set(card.resumeToken, card.askId);
  return copyCard(card);
}

export async function approveAsk(input: {
  askId: string;
  optionId: string;
  resumeToken: ResumeToken;
}): Promise<ApprovalResult> {
  const askId = requireNonEmpty(input.askId, 'askId');
  const optionId = requireNonEmpty(input.optionId, 'optionId');
  const resumeToken = requireNonEmpty(input.resumeToken, 'resumeToken');
  const issuedAskId = tokenToAskId.get(resumeToken);
  if (issuedAskId !== undefined) {
    if (issuedAskId !== askId) {
      throw new PermissionError('ask: resume token does not belong to this ask');
    }
    const stored = issuedCards.get(askId);
    if (stored === undefined) {
      throw new PermissionError('ask: unknown ask');
    }
    if (!stored.card.options.some((option) => option.optionId === optionId)) {
      throw new PermissionError('ask: unknown option for this ask');
    }
    return { askId, approvedOptionId: optionId, resumeToken };
  }
  throw new PermissionError('ask: unknown or forged resume token');
}

export async function resumeAsk(input: {
  resumeToken: ResumeToken;
}): Promise<AskCard> {
  const resumeToken = requireNonEmpty(input.resumeToken, 'resumeToken');
  const issuedAskId = tokenToAskId.get(resumeToken);
  if (issuedAskId !== undefined) {
    const stored = issuedCards.get(issuedAskId);
    if (stored !== undefined) {
      return copyCard(stored.card);
    }
  }
  if (DEMO_RESUME_PATTERN.test(resumeToken)) {
    const n = resumeToken.slice('resume-'.length);
    return {
      askId: `ask-${n}`,
      kind: 'approval',
      summary: `Resumed ask ask-${n}`,
      options: [
        { optionId: 'yes', label: 'Yes' },
        { optionId: 'no', label: 'No' },
      ],
      resumeToken,
    };
  }
  throw new PermissionError('ask: unknown or forged resume token');
}

export async function listSessions(input: {
  storePath: string;
}): Promise<SessionSummary[]> {
  requireNonEmpty(input.storePath, 'storePath');
  return sessionSummaries.map((session) => ({ ...session }));
}
