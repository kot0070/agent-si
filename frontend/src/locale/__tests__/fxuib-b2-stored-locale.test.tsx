/** @vitest-environment jsdom */
// FXUIB-B2: a stored uk locale applies without TopBar (first run +
// splash): the provider syncs the module locale, not just storage.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import {
  LOCALE_STORAGE_KEY,
  LocaleProvider,
  resetLocaleForTests,
  t,
} from "../index";
import uk from "../uk.json";

function Probe(): React.JSX.Element {
  return <p data-testid="title">{t("tasks.creator.title")}</p>;
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("FXUIB-B2 stored locale without TopBar", () => {
  it("stored uk renders Ukrainian with no TopBar mounted", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "uk");
    render(
      <LocaleProvider>
        <Probe />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("title").textContent).toBe(
      uk.tasks.creator.title,
    );
  });
});
