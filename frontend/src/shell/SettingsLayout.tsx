// kit BUILD_PLAN:1480 M-R-UX-2 one H2 plus explainer; jargon carries a Why chip
import type { ReactElement, ReactNode } from 'react';
import { useInRouterContext, useNavigate } from 'react-router-dom';
import { t } from '../locale/index';
import { useCurrentProject } from '../app/ApiClientProvider';

export interface SettingsLayoutProps {
  titleKey: string;
  purposeKey: string;
  // R6: the need-it-now block shows only on Models and Routing; other
  // sections omit the key and render no block.
  needItNowKey?: string;
  children: ReactNode;
  advanced?: ReactNode;
  // FXNAV P16-needitnow: optional kit probe id on the section (the
  // Settings Project page carries kit-card-needitnow-project).
  sectionTestId?: string;
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
    <button
      type="button"
      data-testid="settings-why-chip"
      className="fx-why-quiet"
      onClick={open}
    >
      {t('projects.why_this_model.title')}
    </button>
  );
}

export function SettingsLayout(props: SettingsLayoutProps): ReactElement {
  const inRouter = useInRouterContext();
  return (
    <section data-testid={props.sectionTestId}>
      <h2>{t(props.titleKey)}</h2>
      <p data-testid="settings-purpose">{t(props.purposeKey)}</p>
      {props.needItNowKey !== undefined ? (
        <p data-testid="settings-need-it-now">{t(props.needItNowKey)}</p>
      ) : null}
      {inRouter ? (
        <WhyChipWithRouter />
      ) : (
        <button
          type="button"
          data-testid="settings-why-chip"
          className="fx-why-quiet"
        >
          {t('projects.why_this_model.title')}
        </button>
      )}
      <p data-testid="settings-why-detail">
        {t('projects.why_this_model.detail')}
      </p>
      {props.children}
      {props.advanced}
    </section>
  );
}
