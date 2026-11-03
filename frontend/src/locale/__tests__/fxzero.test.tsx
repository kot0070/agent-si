/** @vitest-environment jsdom */
/// <reference types="vite/client" />
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  pluralUnit,
  resetLocaleForTests,
  setLocale,
} from '../index';

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
});

afterEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
});

describe('fxzero R3 watcher count plurals', () => {
  it('en singular vs plural', () => {
    setLocale('en');
    expect(pluralUnit('shell.cards.watcher.runs', 1)).toBe('run');
    expect(pluralUnit('shell.cards.watcher.runs', 0)).toBe('runs');
    expect(pluralUnit('shell.cards.watcher.runs', 98)).toBe('runs');
    expect(pluralUnit('shell.cards.watcher.agents', 1)).toBe('agent');
    expect(pluralUnit('shell.cards.watcher.agents', 2)).toBe('agents');
  });

  it('uk one/few/many', () => {
    setLocale('uk');
    expect(pluralUnit('shell.cards.watcher.runs', 1)).toBe('запуск');
    expect(pluralUnit('shell.cards.watcher.runs', 2)).toBe('запуски');
    expect(pluralUnit('shell.cards.watcher.runs', 5)).toBe('запусків');
    expect(pluralUnit('shell.cards.watcher.agents', 1)).toBe('агент');
    expect(pluralUnit('shell.cards.watcher.agents', 3)).toBe('агенти');
    expect(pluralUnit('shell.cards.watcher.agents', 98)).toBe('агентів');
  });
});
