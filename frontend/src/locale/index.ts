import { createContext, createElement, useContext, useEffect, useRef } from 'react';
import type { ReactElement, ReactNode } from 'react';
import en from './en.json';
import uk from './uk.json';

export type SupportedLocale = 'en' | 'uk';

export type LocaleErrorCode = 'MISSING_LOCALE_KEY' | 'UNSUPPORTED_LOCALE';

export const DEFAULT_LOCALE: SupportedLocale = 'en';

export const LOCALE_STORAGE_KEY = 'agentsi.locale';

type LocaleTable = Record<string, unknown>;

const TABLES: Record<SupportedLocale, LocaleTable> = {
  en: en as LocaleTable,
  uk: uk as LocaleTable,
};

let currentLocale: SupportedLocale = DEFAULT_LOCALE;

function codedError(code: LocaleErrorCode, message: string): Error {
  const error = new Error(message) as Error & { code: LocaleErrorCode };
  error.code = code;
  return error;
}

function lookup(table: LocaleTable, key: string): string | undefined {
  let node: unknown = table;
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) {
      return undefined;
    }
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === 'string' ? node : undefined;
}

function readStoredLocale(): SupportedLocale | undefined {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    return stored === 'en' || stored === 'uk' ? stored : undefined;
  } catch {
    return undefined;
  }
}

function persistLocale(locale: SupportedLocale): void {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Storage unavailable (private mode, SSR probe): locale still applies in memory.
  }
}

export function t(key: string, params?: Record<string, string | number>): string {
  const template = lookup(TABLES[currentLocale], key);
  if (template === undefined) {
    throw codedError('MISSING_LOCALE_KEY', `Unknown locale key: ${key}`);
  }
  if (params === undefined) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

export function setLocale(locale: SupportedLocale): void {
  if (locale !== 'en' && locale !== 'uk') {
    throw codedError('UNSUPPORTED_LOCALE', `Unsupported locale: ${String(locale)}`);
  }
  currentLocale = locale;
  persistLocale(locale);
}

const LocaleContext = createContext<{ locale: SupportedLocale }>({ locale: DEFAULT_LOCALE });

export function useLocale(): { locale: SupportedLocale } {
  return useContext(LocaleContext);
}

export interface LocaleProviderProps {
  children: ReactNode;
  initialLocale?: SupportedLocale;
}

export function LocaleProvider(props: LocaleProviderProps): ReactElement {
  const locale = props.initialLocale ?? readStoredLocale() ?? DEFAULT_LOCALE;
  // FXSAVED item 4: apply the stored locale during the first render,
  // before children render (not in an effect), so t() already reads it
  // on first paint even when no TopBar is mounted yet.
  const appliedRef = useRef<SupportedLocale | null>(null);
  if (appliedRef.current !== locale) {
    appliedRef.current = locale;
    setLocale(locale);
  }
  useEffect(() => {
    persistLocale(locale);
  }, [locale]);
  return createElement(LocaleContext.Provider, { value: { locale } }, props.children);
}

export function detectOsLocale(): SupportedLocale {
  try {
    const language = window.navigator.language.toLowerCase();
    if (language.startsWith('uk')) {
      return 'uk';
    }
    if (language.startsWith('en')) {
      return 'en';
    }
  } catch {
    // Navigator unavailable: fall through to the default.
  }
  return DEFAULT_LOCALE;
}

function bcp47(locale: SupportedLocale): string {
  return locale === 'uk' ? 'uk-UA' : 'en-US';
}

export function formatDate(date: Date, locale?: SupportedLocale): string {
  return new Intl.DateTimeFormat(bcp47(locale ?? currentLocale), {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).format(date);
}

/** Long locale date ("11 Feb 2026" / "11 лют. 2026"); invalid input falls back to the raw value. */
export function formatDateLong(value: string, locale?: SupportedLocale): string {
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(bcp47(locale ?? currentLocale), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(stamp);
}

/** Local date+time ("11 Feb 2026, 06:42"); invalid input falls back to raw. */
export function formatDateTime(value: string, locale?: SupportedLocale): string {
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(bcp47(locale ?? currentLocale), {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(stamp);
}

export function formatNumber(value: number, locale?: SupportedLocale): string {
  return new Intl.NumberFormat(bcp47(locale ?? currentLocale)).format(value);
}

export function resetLocaleForTests(): void {
  currentLocale = DEFAULT_LOCALE;
  try {
    window.localStorage.removeItem(LOCALE_STORAGE_KEY);
  } catch {
    // Storage unavailable in this probe: in-memory default is still restored.
  }
}
