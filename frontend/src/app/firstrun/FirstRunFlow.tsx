import { useState } from 'react';
import type { FormEvent, ReactElement } from 'react';
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
  const [index, setIndex] = useState<number>(() => {
    const at = REQUIRED_STEPS.indexOf(props.initialStep ?? 'connectProvider');
    return at < 0 ? 0 : at;
  });
  const [taskTitle, setTaskTitle] = useState<string>('');
  const current: FirstRunStep = REQUIRED_STEPS[index] ?? 'connectProvider';
  const previous: FirstRunStep | undefined = index > 0 ? REQUIRED_STEPS[index - 1] : undefined;
  const skip = (step: OptionalFirstRunStep): void => {
    setSkipped((prev: OptionalFirstRunStep[]) => (prev.includes(step) ? prev : [...prev, step]));
  };
  const goNext = (): void => {
    setIndex((at: number) => Math.min(at + 1, REQUIRED_STEPS.length - 1));
  };
  const goBack = (): void => {
    setIndex((at: number) => Math.max(at - 1, 0));
  };
  const submitTask = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    props.onComplete();
  };
  return (
    <section>
      <h2>{t('firstrun.title')}</h2>
      <ol>
        {REQUIRED_STEPS.map((step) => (
          <li
            key={step}
            aria-current={step === current ? 'step' : undefined}
            aria-label={t(`firstrun.steps.${step}`)}
          >
            {step === current ? (
              <h3>{t(`firstrun.steps.${step}`)}</h3>
            ) : (
              <span aria-hidden="true">{t(`firstrun.steps.${step}`)}</span>
            )}
          </li>
        ))}
      </ol>
      <section>
        {current === 'connectProvider' ? (
          <label>
            {t('settings.roleProfile.providerLabel')}
            <input
              type="text"
              aria-label={t('settings.roleProfile.providerLabel')}
              placeholder={t('chat.composer.prompt')}
            />
          </label>
        ) : null}
        {current === 'oneClickTeam' ? (
          <label>
            <input type="checkbox" aria-label={t('settings.roleProfile.modeLabel')} />
            {t('settings.roleProfile.modeLabel')}
          </label>
        ) : null}
        {current === 'projectFolder' ? (
          <label>
            {t('settings.localbench.pathLabel')}
            <input
              type="text"
              aria-label={t('settings.localbench.pathLabel')}
              placeholder={t('settings.localbench.pathHint')}
            />
          </label>
        ) : null}
        {current === 'firstTask' ? (
          <form onSubmit={submitTask}>
            <h4>{t('tasks.creator.title')}</h4>
            <label>
              {t('tasks.creator.title')}
              <input
                type="text"
                value={taskTitle}
                onChange={(event) => setTaskTitle(event.target.value)}
              />
            </label>
            <button type="submit">{t('tasks.creator.create')}</button>
          </form>
        ) : (
          <>
            {previous === undefined ? null : (
              <button type="button" onClick={goBack}>
                {t(`firstrun.steps.${previous}`)}
              </button>
            )}
            <button type="button" onClick={goNext}>
              {t('firstrun.next')}
            </button>
          </>
        )}
      </section>
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
    </section>
  );
}
