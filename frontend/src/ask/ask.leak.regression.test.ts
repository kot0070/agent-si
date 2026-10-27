// ASK leak regression (L-007): resume and session list are backend-backed.
//
// - An unissued resume token must be refused with PermissionError, never
//   answered with a fabricated card.
// - listSessions must reflect issued cards, never a fixed empty answer.
import { describe, expect, it } from 'vitest';
import { createAskCard, listSessions, resumeAsk } from './index';

describe('ASK leak regression (L-007)', () => {
  it('unissued resume token is refused, never fabricated', async () => {
    await expect(resumeAsk({ resumeToken: 'resume-9000' })).rejects.toThrow(
      'ask: unknown or forged resume token',
    );
  });

  it('listSessions reflects issued cards', async () => {
    const card = await createAskCard({
      kind: 'approval',
      summary: 'Approve the migration plan?',
      options: [
        { optionId: 'yes', label: 'Yes' },
        { optionId: 'no', label: 'No' },
      ],
    });
    const sessions = await listSessions({ storePath: ':memory:' });
    expect(
      sessions.some(
        (session) => session.sessionId === card.askId && session.title === card.summary,
      ),
    ).toBe(true);
  });
});
