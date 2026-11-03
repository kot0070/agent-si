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

describe('LIVE0-05 first-run wizard setup steps', () => {
  it('renders every required setup step in order with the first current', () => {
    const { container } = render(<FirstRunFlow onComplete={() => undefined} />);
    expect(screen.getByText(en.firstrun.title)).toBeTruthy();
    const ordered = [
      en.firstrun.steps.connectProvider,
      en.firstrun.steps.oneClickTeam,
      en.firstrun.steps.projectFolder,
      en.firstrun.steps.firstTask,
    ];
    for (const title of ordered) {
      expect(screen.getByText(title)).toBeTruthy();
    }
    const items = container.querySelectorAll('ol > li');
    expect(items.length).toBe(4);
    expect(items[0]?.textContent).toBe(ordered[0]);
    expect(items[1]?.textContent).toBe(ordered[1]);
    expect(items[2]?.textContent).toBe(ordered[2]);
    expect(items[3]?.textContent).toBe(ordered[3]);
    expect(currentStep(container)).toBe(en.firstrun.steps.connectProvider);
  });

  it('walks Next through each setup step to the first-task form, then completes', () => {
    let done = false;
    const { container } = render(
      <FirstRunFlow onComplete={() => { done = true; }} />,
    );
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(currentStep(container)).toBe(en.firstrun.steps.oneClickTeam);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(currentStep(container)).toBe(en.firstrun.steps.projectFolder);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(currentStep(container)).toBe(en.firstrun.steps.firstTask);
    expect(done).toBe(false);
    expect(screen.getByRole('heading', { name: en.tasks.creator.title })).toBeTruthy();
    expect(screen.queryByRole('button', { name: en.firstrun.next })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: en.tasks.creator.create }));
    expect(done).toBe(true);
  });

  it('Back retreats without completing', () => {
    let done = false;
    const { container } = render(
      <FirstRunFlow onComplete={() => { done = true; }} />,
    );
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(currentStep(container)).toBe(en.firstrun.steps.projectFolder);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.back }));
    expect(currentStep(container)).toBe(en.firstrun.steps.oneClickTeam);
    expect(done).toBe(false);
  });

  it('lists the optional steps as one quiet skippable list on the last step', () => {
    render(<FirstRunFlow onComplete={() => undefined} />);
    expect(screen.queryAllByRole('button', { name: en.firstrun.skip }).length).toBe(1);
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    fireEvent.click(screen.getByRole('button', { name: en.firstrun.next }));
    expect(screen.getAllByRole('button', { name: en.firstrun.skip }).length).toBe(4);
    for (const title of Object.values(en.firstrun.optional)) {
      expect(screen.getByText(title)).toBeTruthy();
    }
  });
});
