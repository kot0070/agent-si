/** @vitest-environment jsdom */
// L0B-04: the project card shows the human-readable name plus a
// locale-formatted date; the raw project_id and the ISO string are gone.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import {
  formatDate,
  resetLocaleForTests,
  setLocale,
} from "../../locale/index";
import type { SupportedLocale } from "../../locale/index";
import { ProjectsPage } from "../ProjectsPage";

const CREATED_AT = "2026-01-01T00:00:00.000Z";

function fixtureClient(): FakeApiClient {
  return new FakeApiClient({
    projects: [{ project_id: "p-9", name: "n-9", created_at: CREATED_AT }],
  });
}

async function cardText(locale: SupportedLocale): Promise<string> {
  setLocale(locale);
  const shown = render(
    <ApiClientProvider client={fixtureClient()}>
      <ProjectsPage />
    </ApiClientProvider>,
  );
  const row = await screen.findByTestId("project-row-p-9");
  const text = row.textContent ?? "";
  shown.unmount();
  cleanup();
  return text;
}

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

describe("l0b04 project card display format", () => {
  it("shows the name plus a locale-formatted date, never the raw id or ISO stamp", async () => {
    const expectedEn = formatDate(new Date(CREATED_AT), "en");
    const textEn = await cardText("en");
    expect(textEn).toContain("n-9");
    expect(textEn).toContain(expectedEn);
    expect(textEn).not.toContain("p-9");
    expect(textEn).not.toContain(CREATED_AT);

    const expectedUk = formatDate(new Date(CREATED_AT), "uk");
    const textUk = await cardText("uk");
    expect(textUk).toContain("n-9");
    expect(textUk).toContain(expectedUk);
    expect(textUk).not.toContain("p-9");
    expect(textUk).not.toContain(CREATED_AT);
  });

  it("does not crash on an invalid date stamp", async () => {
    setLocale("en");
    render(
      <ApiClientProvider
        client={
          new FakeApiClient({
            projects: [
              { project_id: "p-bad", name: "n-bad", created_at: "t-0" },
            ],
          })
        }
      >
        <ProjectsPage />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("project-row-p-bad")).toBeTruthy();
  });
});
