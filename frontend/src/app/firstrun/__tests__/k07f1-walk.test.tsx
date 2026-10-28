/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { FirstRunFlow } from '../FirstRunFlow';
import { resetLocaleForTests, setLocale } from '../../../locale/index';
import en from '../../../locale/en.json';

beforeEach(() => {
  resetLocaleForTests();
  setLocale('en');
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

function currentStep(container: HTMLElement): string | null {
  const items = container.querySelectorAll('li[aria-current="step"]');
  expect(items.length).toBe(1);
  const first = items[0];
  return first === undefined ? null : first.textContent;
}

describe('K07F1 first-run walk', () => {
  it('starts on the first step with progress marked current', () => {
    const { container } = render(<FirstRunFlow onComplete={() => undefined} />);
    expect(screen.getByText(en.firstrun.title)).toBeTruthy();
    expect(currentStep(container)).toBe(en.firstrun.steps.connectProvider);
    expect(screen.getByRole('heading', { name: en.firstrun.steps.connectProvider })).toBeTruthy();
  });

  it('one Next from step 1 does not complete but advances one step', () => {
    let done = false;
    const { container } = render(
      <FirstRunFlow onComplete={() => { done = true; }} />,
    );
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(done).toBe(false);
    expect(currentStep(container)).toBe(en.firstrun.steps.oneClickTeam);
    expect(screen.getByRole('heading', { name: en.firstrun.steps.oneClickTeam })).toBeTruthy();
  });

  it('Next advances and Back retreats under the previous step title', () => {
    render(<FirstRunFlow onComplete={() => undefined} />);
    expect(screen.getAllByRole('button').length).toBe(5);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    const back = screen.getByRole('button', { name: en.firstrun.steps.connectProvider });
    expect(back).toBeTruthy();
    fireEvent.click(back);
    expect(screen.getByRole('heading', { name: en.firstrun.steps.connectProvider })).toBeTruthy();
    expect(screen.getAllByRole('button').length).toBe(5);
  });

  it('respects the initialStep prop', () => {
    const { container } = render(
      <FirstRunFlow initialStep="projectFolder" onComplete={() => undefined} />,
    );
    expect(currentStep(container)).toBe(en.firstrun.steps.projectFolder);
    expect(screen.getByRole('heading', { name: en.firstrun.steps.projectFolder })).toBeTruthy();
  });

  it('skip hides an optional step, 4 -> 3', () => {
    render(<FirstRunFlow onComplete={() => undefined} />);
    expect(screen.getAllByRole('button', { name: en.firstrun.skip }).length).toBe(4);
    fireEvent.click(screen.getAllByRole('button', { name: en.firstrun.skip })[0]!);
    expect(screen.getAllByRole('button', { name: en.firstrun.skip }).length).toBe(3);
  });

  it('firstTask has no Next; submitting its form calls onComplete', () => {
    let done = false;
    render(<FirstRunFlow initialStep="firstTask" onComplete={() => { done = true; }} />);
    expect(screen.queryByRole('button', { name: en.firstrun.next })).toBeNull();
    expect(screen.getByRole('heading', { name: en.tasks.creator.title })).toBeTruthy();
    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'My first task' } });
    expect(done).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect(done).toBe(true);
  });

  it('walking Next to the end reaches the task form before completing', () => {
    let done = false;
    const { container } = render(
      <FirstRunFlow onComplete={() => { done = true; }} />,
    );
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(currentStep(container)).toBe(en.firstrun.steps.firstTask);
    expect(done).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect(done).toBe(true);
  });

  it('each required step title matches getByText exactly once', () => {
    const { container } = render(<FirstRunFlow onComplete={() => undefined} />);
    for (const step of Object.values(en.firstrun.steps)) {
      expect(screen.getByText(step)).toBeTruthy();
    }
    expect(currentStep(container)).toBe(en.firstrun.steps.connectProvider);
    expect(screen.getByRole('heading', { name: en.firstrun.steps.connectProvider })).toBeTruthy();
  });

  it('each required step before the task shows a locale-named control and Next still advances empty', () => {
    render(<FirstRunFlow onComplete={() => undefined} />);
    expect(screen.getByRole('textbox', { name: en.settings.roleProfile.providerLabel })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(screen.getByRole('checkbox', { name: en.settings.roleProfile.modeLabel })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(screen.getByRole('textbox', { name: en.settings.localbench.pathLabel })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(screen.getByRole('heading', { name: en.tasks.creator.title })).toBeTruthy();
  });

  it('submitting the firstTask form with an empty input calls onComplete', () => {
    let done = false;
    render(<FirstRunFlow initialStep="firstTask" onComplete={() => { done = true; }} />);
    expect((screen.getByRole('textbox') as HTMLInputElement).value).toBe('');
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect(done).toBe(true);
  });

  it('Back retreats one step at a time across the walk', () => {
    const { container } = render(<FirstRunFlow onComplete={() => undefined} />);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(currentStep(container)).toBe(en.firstrun.steps.projectFolder);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.steps.oneClickTeam }));
    expect(currentStep(container)).toBe(en.firstrun.steps.oneClickTeam);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.steps.connectProvider }));
    expect(currentStep(container)).toBe(en.firstrun.steps.connectProvider);
  });
});
