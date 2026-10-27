import { useState } from 'react';
import type { ReactElement } from 'react';
import { t } from '../../locale/index';

export type FirstRunStep = 'connectProvider' | 'oneClickTeam' | 'projectFolder' | 'firstTask';

export type OptionalFirstRunStep = 'localAI' | 'watcherPreset' | 'automations' | 'kbs';

export interface FirstRunFlowProps {
  initialStep?: FirstRunStep;
  onComplete: () => void;
}

const REQUIRED_STEPS: FirstRunStep[] = ['connectProvider', 'oneClickTeam', 'projectFolder', 'firstTask'];

const OPTIONAL_STEPS: OptionalFirstRunStep[] = ['localAI', 'watcherPreset', 'automations', 'kbs'];

export function FirstRunFlow(props: FirstRunFlowProps): ReactElement {
  const [skipped, setSkipped] = useState<OptionalFirstRunStep[]>([]);
  const current = props.initialStep ?? REQUIRED_STEPS[0];
  const skip = (step: OptionalFirstRunStep): void => {
    setSkipped((prev: OptionalFirstRunStep[]) => (prev.includes(step) ? prev : [...prev, step]));
  };
  return (
    <section>
      <h2>{t('firstrun.title')}</h2>
      <ol>
        {REQUIRED_STEPS.map((step) => (
          <li key={step} aria-current={step === current ? 'step' : undefined}>
            {t(`firstrun.steps.${step}`)}
          </li>
        ))}
      </ol>
      <p>{t('firstrun.optionalNote')}</p>
      <ul>
        {OPTIONAL_STEPS.map((step) => (
          <li key={step}>
            {t(`firstrun.optional.${step}`)}
            {skipped.includes(step) ? null : (
              <button type="button" onClick={() => skip(step)}>
                {t('firstrun.skip')}
              </button>
            )}
          </li>
        ))}
      </ul>
      <button type="button" onClick={props.onComplete}>
        {t('firstrun.next')}
      </button>
    </section>
  );
}
