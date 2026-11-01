// kit BUILD_PLAN:1480 M-R-UX-2 one H2 plus explainer; jargon carries a Why chip
import type { ReactElement, ReactNode } from 'react';
import { useInRouterContext, useNavigate } from 'react-router-dom';
import { t } from '../locale/index';
import { useCurrentProject } from '../app/ApiClientProvider';

export interface SettingsLayoutProps {
  titleKey: string;
  purposeKey: string;
  needItNowKey: string;
  children: ReactNode;
  advanced?: ReactNode;
}

// W10: the Why chip navigates to the routing-decisions view (project
// route when a project is selected, settings routing page otherwise).
// Router-aware only when a router is present so bare renders keep working.
function WhyChipWithRouter(): ReactElement {
  const navigate = useNavigate();
  let projectId: string | null = null;
  try {
    projectId = useCurrentProject().projectId;
  } catch {
    projectId = null;
  }
  function open(): void {
    navigate(
      projectId === null
        ? '/settings/routing'
        : `/projects/${projectId}/routing-decisions`,
    );
  }
  return (
    <button type="button" data-testid="settings-why-chip" onClick={open}>
      {t('projects.why_this_model.title')}
    </button>
  );
}

export function SettingsLayout(props: SettingsLayoutProps): ReactElement {
  const inRouter = useInRouterContext();
  return (
    <section>
      <h2>{t(props.titleKey)}</h2>
      <p>{t(props.purposeKey)}</p>
      <p>{t(props.needItNowKey)}</p>
      {inRouter ? (
        <WhyChipWithRouter />
      ) : (
        <button type="button" data-testid="settings-why-chip">
          {t('projects.why_this_model.title')}
        </button>
      )}
      {props.children}
      {props.advanced}
    </section>
  );
}
