// kit BUILD_PLAN:1480 M-R-UX-2 one H2 plus explainer; jargon carries a Why chip
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
      <button type="button" data-testid="settings-why-chip">
        {t('projects.why_this_model.title')}
      </button>
      {props.children}
      {props.advanced}
    </section>
  );
}
