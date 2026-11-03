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
  // FXSAVED item 4: storage-sourced mode only (no explicit
  // initialLocale) applies the stored locale to the module during the
  // first render, before children render, so t() already reads it on
  // first paint (the production main.tsx outer provider; no TopBar
  // mounted yet). An explicit initialLocale is scoped mode: context
  // plus persistence only, never disturbs module t (laneB.step2
  // contract: provider with a prop must not switch the module locale).
  const appliedRef = useRef<SupportedLocale | null>(null);
  if (props.initialLocale === undefined && appliedRef.current !== locale) {
    appliedRef.current = locale;
    setLocale(locale);
  }
  useEffect(() => {
    if (props.initialLocale === undefined) {
      setLocale(locale);
    } else {
      // Scoped mode: the prop persists (remounts restore it) but never
      // switches the module t (laneB.step2 contract).
      persistLocale(locale);
    }
  }, [locale, props.initialLocale]);
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

/** FXTIME: short month names per locale (CLDR short form). */
const EN_MONTHS_SHORT = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/** FXTIME: short month names per locale (CLDR short form). */
const UK_MONTHS_SHORT = [
  'січ.', 'лют.', 'бер.', 'квіт.', 'трав.', 'черв.',
  'лип.', 'серп.', 'вер.', 'жовт.', 'лист.', 'груд.',
];

/** FXTIME: the ONE helper for every time on screen (en + uk, 24-hour).
 *
 * Same form in both locales: "HH:mm" when the stamp falls on the local
 * day, otherwise "d MMM HH:mm" with the locale month name (uk months in
 * uk). Hours are always 24-hour, zero-padded, from the PC-local zone
 * (served UTC ISO stamps render in the viewer's zone). Invalid or empty
 * input falls back to the raw value, never an invented time.
 */
export function formatScreenTime(
  value: string | number | Date,
  locale?: SupportedLocale,
): string {
  const raw = value instanceof Date ? value.toString() : String(value);
  const stamp = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(stamp.getTime())) {
    return raw === 'Invalid Date' ? String(value) : raw;
  }
  const pad = (n: number): string => String(n).padStart(2, '0');
  const hm = `${pad(stamp.getHours())}:${pad(stamp.getMinutes())}`;
  const now = new Date();
  if (
    stamp.getFullYear() === now.getFullYear() &&
    stamp.getMonth() === now.getMonth() &&
    stamp.getDate() === now.getDate()
  ) {
    return hm;
  }
  const months = (locale ?? currentLocale) === 'uk' ? UK_MONTHS_SHORT : EN_MONTHS_SHORT;
  return `${stamp.getDate()} ${months[stamp.getMonth()]} ${hm}`;
}

export function formatDate(date: Date, locale?: SupportedLocale): string {
  return formatScreenTime(date, locale);
}

/** Date stamp through the one screen-time helper (kept signature). */
export function formatDateLong(value: string, locale?: SupportedLocale): string {
  return formatScreenTime(value, locale);
}

/** Date+time stamp through the one screen-time helper (kept signature). */
export function formatDateTime(value: string, locale?: SupportedLocale): string {
  return formatScreenTime(value, locale);
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
