import type { ReactElement } from 'react';
import { t } from '../locale/index';
import type { SupportedLocale } from '../locale/index';
import en from '../locale/en.json';
import uk from '../locale/uk.json';
import { THIRD_PARTY_NOTICES } from './thirdPartyNotices';

export const AGENT_SI_NAME = 'Agent SI';

export const APP_ID = 'com.agentsi.app';

export const LICENCE_LINE = 'Copyright (c) 2026 Ivan Soprun';

export const MIT_LICENSE_REF = 'about.licence.mitText';

export interface AboutProps {
  locale?: SupportedLocale;
  showThirdParty?: boolean;
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

function mitText(locale: SupportedLocale | undefined): string {
  if (locale === undefined) {
    return t(MIT_LICENSE_REF);
  }
  const table = (locale === 'en' ? en : uk) as unknown as LocaleTable;
  return lookup(table, MIT_LICENSE_REF) ?? t(MIT_LICENSE_REF);
}

export function About(props: AboutProps): ReactElement {
  return (
    <section>
      <h2>{AGENT_SI_NAME}</h2>
      <p>{LICENCE_LINE}</p>
      <p>{mitText(props.locale)}</p>
      {props.showThirdParty !== true ? null : (
        <div data-testid="about-third-party">
          <h3>{t('about.thirdParty.title')}</h3>
          <ul>
            {THIRD_PARTY_NOTICES.map((notice) => (
              <li
                key={notice.name}
                data-testid={`third-party-${notice.name}`}
              >
                <span>{notice.name}</span>
                <span>{notice.version}</span>
                <span>{notice.licence}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
