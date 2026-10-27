import type { ReactElement } from 'react';
import { t } from '../locale/index';
import type { SupportedLocale } from '../locale/index';
import en from '../locale/en.json';
import uk from '../locale/uk.json';

export const HOW_IT_WORKS_KEYS = {
  runsTitle: 'howItWorks.runs.title',
  runsBody: 'howItWorks.runs.body',
  codeTestsTitle: 'howItWorks.codeTests.title',
  codeTestsBody: 'howItWorks.codeTests.body',
  localTestsTitle: 'howItWorks.localTests.title',
  localTestsBody: 'howItWorks.localTests.body',
} as const;

export interface HowItWorksProps {
  locale?: SupportedLocale;
}

type LocaleTable = Record<string, unknown>;

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

function text(key: string, locale: SupportedLocale | undefined): string {
  if (locale === undefined) {
    return t(key);
  }
  const table = (locale === 'en' ? en : uk) as unknown as LocaleTable;
  return lookup(table, key) ?? t(key);
}

export function HowItWorks(props: HowItWorksProps): ReactElement {
  const entries = [
    { titleKey: HOW_IT_WORKS_KEYS.runsTitle, bodyKey: HOW_IT_WORKS_KEYS.runsBody },
    { titleKey: HOW_IT_WORKS_KEYS.codeTestsTitle, bodyKey: HOW_IT_WORKS_KEYS.codeTestsBody },
    { titleKey: HOW_IT_WORKS_KEYS.localTestsTitle, bodyKey: HOW_IT_WORKS_KEYS.localTestsBody },
  ];
  return (
    <section>
      {entries.map((entry) => (
        <article key={entry.titleKey}>
          <h2>{text(entry.titleKey, props.locale)}</h2>
          <p>{text(entry.bodyKey, props.locale)}</p>
          <code>{entry.titleKey}</code>
          <code>{entry.bodyKey}</code>
        </article>
      ))}
    </section>
  );
}
