/** @vitest-environment jsdom */
/// <reference types="vite/client" />
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup } from '@testing-library/react';
import {
  resetLocaleForTests,
  setLocale,
} from '../../locale/index';
import {
  engineVerdictLine,
  summarizeEngineTurn,
} from '../index';

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('fxzero R1 zero-part runs never say Done', () => {
  it('empty plan text is not done, en', () => {
    const summary = summarizeEngineTurn('log line 1\nlog line 2', 'ok');
    expect(summary.parts).toBe(0);
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toContain('Nothing was built');
    expect(engineVerdictLine(summary)).toContain('plan had no parts');
    expect(engineVerdictLine(summary)).not.toContain('Done');
  });

  it('empty plan sentence is Ukrainian in uk', () => {
    setLocale('uk');
    const summary = summarizeEngineTurn('log line 1\nlog line 2', 'ok');
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toContain('Нічого не створено');
    expect(engineVerdictLine(summary)).not.toContain('Done');
  });

  it('a real plan still says Done with its parts', () => {
    const summary = summarizeEngineTurn(
      'Part p1: PASS\nrun success: all 1 parts PASS',
      'ok',
    );
    expect(summary.parts).toBe(1);
    expect(summary.done).toBe(true);
  });

  it("a success count line without Part rows still counts", () => {
    const summary = summarizeEngineTurn(
      "Director: plan of 2 parts\nTotal: 10 input\nrun success: all 2 parts PASS",
      "ok",
    );
    expect(summary.parts).toBe(2);
    expect(summary.done).toBe(true);
    expect(engineVerdictLine(summary)).toContain("Done");
  });

  it("an announced plan without verdicts reads failed with its count", () => {
    const summary = summarizeEngineTurn("Director: plan of 2 parts", "ok");
    expect(summary.parts).toBe(2);
    expect(summary.done).toBe(false);
    expect(engineVerdictLine(summary)).toContain("Failed");
  });

  it("team-off solo success keeps Done", () => {
    const summary = summarizeEngineTurn(
      "Team off: one worker, no audit\nDone, not audited.",
      "ok",
    );
    expect(summary.done).toBe(true);
  });
});
