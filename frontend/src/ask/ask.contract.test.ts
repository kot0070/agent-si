// Lane A ASK-UI behaviour contract (STEP1: expected RED).
//
// Every test reaches the real implementation through the entry point
// './index'. STEP1 declares signatures only, so each test MUST fail until
// the real implementation lands.
import { describe, expect, it } from 'vitest';
import { approveAsk, createAskCard, listSessions, resumeAsk } from './index';
import { SNAKE_TO_CAMEL } from './types';
import { SecretRef } from './types';

// Tests-only placeholder secret handle. Never a real credential.
const FAKE_SECRET_REF = SecretRef.create('FAKE-OF-secret-ref-for-contract-test-only');

describe('Lane A ASK-UI contract (STEP1: expected RED)', () => {
  it('createAskCard returns a G4 ASK card', async () => {
    const card = await createAskCard({
      kind: 'approval',
      summary: 'Approve the migration plan?',
      options: [
        { optionId: 'yes', label: 'Yes' },
        { optionId: 'no', label: 'No' },
      ],
      secretRef: FAKE_SECRET_REF,
    });
    expect(card.askId).toBeTruthy();
    expect(card.kind).toBe('approval');
    expect(card.summary).toBeTruthy();
    expect(card.options.map((o) => o.optionId)).toEqual(['yes', 'no']);
    expect(card.resumeToken).toBeTruthy();
  });

  it('approveAsk returns a resolution', async () => {
    const card = await createAskCard({
      kind: 'approval',
      summary: 'Approve the migration plan?',
      options: [
        { optionId: 'yes', label: 'Yes' },
        { optionId: 'no', label: 'No' },
      ],
    });
    const result = await approveAsk({
      askId: card.askId,
      optionId: 'yes',
      resumeToken: card.resumeToken,
    });
    expect(result.askId).toBe(card.askId);
    expect(result.approvedOptionId).toBe('yes');
    expect(result.resumeToken).toBe(card.resumeToken);
  });

  it('approveAsk rejects unissued ids without a canned answer', async () => {
    await expect(
      approveAsk({ askId: 'ask-9000', optionId: 'yes', resumeToken: 'resume-9000' }),
    ).rejects.toThrow('ask: unknown or forged resume token');
  });

  it('resumeAsk returns the ASK card (chat + run view click-resume)', async () => {
    const card = await resumeAsk({ resumeToken: 'resume-1' });
    expect(card.askId).toBeTruthy();
    expect(card.resumeToken).toBeTruthy();
  });

  it('listSessions lists sessions after restart', async () => {
    const sessions = await listSessions({ storePath: ':memory:' });
    expect(Array.isArray(sessions)).toBe(true);
  });

  it('SecretRef stays opaque and never leaks into logs', async () => {
    const raw = 'FAKE-OF-secret-ref-for-contract-test-only';
    const ref = SecretRef.create(raw);
    expect(JSON.stringify({ ref })).not.toContain(raw);
  });

  it('snake<->camel field map covers every backend field in both directions', () => {
    // STEP1 data test: checks the SNAKE_TO_CAMEL table only, so it is
    // GREEN while the entry-point tests above stay RED on stubs.
    const expected: Record<string, string> = {
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
    // Forward: every snake key maps to its expected camel literal.
    expect(SNAKE_TO_CAMEL).toEqual(expected);
    expect(Object.keys(SNAKE_TO_CAMEL)).toHaveLength(12);
    // Reverse: invert ONLY the table; every camel value maps back.
    const camelToSnake: Record<string, string> = {};
    for (const [snake, camel] of Object.entries(SNAKE_TO_CAMEL)) {
      camelToSnake[camel] = snake;
    }
    expect(Object.keys(camelToSnake)).toHaveLength(12);
    for (const [snake, camel] of Object.entries(SNAKE_TO_CAMEL)) {
      expect(camelToSnake[camel]).toBe(snake);
      expect(expected[snake]).toBe(camel);
    }
  });
});
