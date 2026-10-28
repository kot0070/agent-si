/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { ApiClientProvider } from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/client";
import { ENDPOINTS } from "../../api/endpoints";
import { App } from "../../app/App";
import { resetLocaleForTests, setLocale, t } from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";

type LocalAiTable = { settings: { localAi: { title: string } } };
const EN_ENDPOINT_LABEL = (en as unknown as LocalAiTable).settings.localAi
  .title;
const UK_ENDPOINT_LABEL = (uk as unknown as LocalAiTable).settings.localAi
  .title;

beforeEach(() => {
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
  setLocale("en");
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

function renderAppAt(route: string): void {
  const router = createMemoryRouter([{ path: "*", element: <App /> }], {
    initialEntries: [route],
  });
  render(
    <ApiClientProvider client={new FakeApiClient({})}>
      <RouterProvider router={router} />
    </ApiClientProvider>,
  );
}

describe.each(["models", "routing", "optimization", "capabilityDB"])(
  "settings %s section mounts ProvidersPage",
  (section) => {
    it("renders provider cards plus the search box inside the section body", async () => {
      renderAppAt(`/settings/${section}`);
      const body = await screen.findByTestId("settings-section-body");
      expect(body).toBeTruthy();
      const cards = await screen.findAllByTestId("provider-card");
      expect(cards.length).toBeGreaterThan(0);
      expect(
        screen.getByPlaceholderText("Search providers or models"),
      ).toBeTruthy();
    });
  },
);

describe("settings localbench section mounts LocalBenchTab", () => {
  it("renders the idle bench tab inside the section body", async () => {
    renderAppAt("/settings/localbench");
    const body = await screen.findByTestId("settings-section-body");
    expect(body).toBeTruthy();
    expect(await screen.findByTestId("localbench-tab")).toBeTruthy();
    expect(screen.getByTestId("localbench-path")).toBeTruthy();
    expect(screen.getByTestId("localbench-scan")).toBeTruthy();
  });
});

describe("settings project section keeps its editors", () => {
  it("renders the role profile editor plus the accepted-risk switch", async () => {
    renderAppAt("/settings/project");
    expect(await screen.findByText(t("settings.roleProfile.title"))).toBeTruthy();
    expect(await screen.findByText(t("settings.risk.label"))).toBeTruthy();
  });
});

describe("settings localAI section labels the endpoint", () => {
  it("shows a locale label while the endpoint value stays exact", async () => {
    renderAppAt("/settings/localAI");
    expect(await screen.findByTestId("localai-stored")).toBeTruthy();
    expect(screen.getByTestId("localai-endpoint-label").textContent).toBe(
      EN_ENDPOINT_LABEL,
    );
    expect(screen.getByTestId("localai-endpoint").textContent).toBe(
      ENDPOINTS.agentsLive,
    );
    expect(screen.getByTestId("localai-endpoint-label").textContent).not.toBe(
      ENDPOINTS.agentsLive,
    );
  });

  it("renders the uk endpoint label through the locale", async () => {
    setLocale("uk");
    renderAppAt("/settings/localAI");
    expect(await screen.findByTestId("localai-stored")).toBeTruthy();
    expect(screen.getByTestId("localai-endpoint-label").textContent).toBe(
      UK_ENDPOINT_LABEL,
    );
    expect(screen.getByTestId("localai-endpoint").textContent).toBe(
      ENDPOINTS.agentsLive,
    );
  });
});
