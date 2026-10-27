import type { ReactElement, ReactNode } from 'react';
import { t } from '../locale/index';

export interface SettingsLayoutProps {
  titleKey: string;
  purposeKey: string;
  needItNowKey: string;
  children: ReactNode;
  advanced?: ReactNode;
}

export function SettingsLayout(props: SettingsLayoutProps): ReactElement {
  return (
    <section>
      <h2>{t(props.titleKey)}</h2>
      <p>{t(props.purposeKey)}</p>
      <p>{t(props.needItNowKey)}</p>
      {props.children}
      {props.advanced}
    </section>
  );
}
