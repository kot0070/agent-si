/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  ApiClientProvider,
  useCurrentProject,
} from "../../app/ApiClientProvider";
import { FakeApiClient } from "../../api/__tests__/fakeApiClient";
import { resetLocaleForTests, setLocale } from "../../locale/index";
import { ProjectsPage } from "../ProjectsPage";
import { ProjectView } from "../ProjectView";
import { RunHistory } from "../RunHistory";
import {
  PROJECT_VIEWS,
  computeAgeDays,
  projectMenuTestId,
} from "../projectsApi";
import type { ProjectViewName } from "../projectsApi";
import en from "../../locale/en.json";

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  resetLocaleForTests();
  window.localStorage.clear();
});

const CREATED_AT = "2026-01-01T00:00:00.000Z";

function fixtureClient(): FakeApiClient {
  return new FakeApiClient({
    projects: [{ project_id: "p-9", name: "n-9", created_at: CREATED_AT }],
    tasksByProject: {
      "p-9": [
        {
          task_id: "t-9",
          project_id: "p-9",
          title: "task nine",
          status: "RUNNING",
          created_at: CREATED_AT,
        },
        {
          task_id: "t-10",
          project_id: "p-9",
          title: "task ten",
          status: "QUEUED",
          created_at: CREATED_AT,
        },
      ],
    },
    ledgerByProject: {
      "p-9": [
        { package_id: "pkg-9", agents: 3, peak_concurrency: 2, wall_time_s: 90 },
      ],
    },
    budgetByProject: {
      "p-9": {
        project_id: "p-9",
        hard_limit: 100,
        spent: 10,
        reserved: 5,
        currency: "u-9",
      },
    },
    routingWhyByDecision: {
      "d-9": {
        decision: { decision_id: "d-9", policy_ref: "pol-9" },
        assignments: [
          {
            decision_id: "d-9",
            role: "manager",
            provider_id: "prov-9",
            model: "mod-9",
          },
        ],
        snapshot: {
          decision_id: "d-9",
          snapshot_ref: "snap-9",
          captured_at: "t-9",
        },
        reason: {
          task_class: "tc-9",
          fit_basis: "stored reason nine",
          price_basis: "KNOWN",
          quality_basis: "MEASURED",
          rejected: ["r-1"],
        },
      },
    },
    nudgeByPackage: {
      "pkg-9": {
        row: {
          package_id: "pkg-9",
          agents: 3,
          peak_concurrency: 2,
          wall_time_s: 90,
        },
        nudge: "pkg-10",
        auto_push: false,
      },
    },
    liveRows: [
      { agent: "n-local", scope: "s-1", deliverable: "d-1", status: "RUNNING" },
      { agent: "n-cloud", scope: "s-2", deliverable: "d-2", status: "QUEUED" },
    ],
  });
}

function SelectedProbe(): ReactElement {
  const current = useCurrentProject();
  return (
    <span data-testid="selected-project">{current.projectId ?? "none"}</span>
  );
}

describe("projects page", () => {
  it("adds, opens, pauses, resumes and archives a project", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectsPage />
        <SelectedProbe />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("project-row-p-9")).toBeTruthy();

    fireEvent.change(await screen.findByTestId("project-add-name"), {
      target: { value: "n-new" },
    });
    fireEvent.change(await screen.findByTestId("project-add-folder"), {
      target: { value: "f-new" },
    });
    fireEvent.click(await screen.findByTestId("project-add-submit"));
    expect(await screen.findByTestId("project-row-p-2")).toBeTruthy();

    fireEvent.click(await screen.findByTestId("project-open-p-9"));
    expect(await screen.findByTestId("selected-project")).toBeTruthy();
    expect((await screen.findByTestId("selected-project")).textContent).toBe(
      "p-9",
    );

    fireEvent.click(await screen.findByTestId("project-pause-p-9"));
    expect(await screen.findByTestId("project-resume-p-9")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("project-resume-p-9"));
    expect(await screen.findByTestId("project-pause-p-9")).toBeTruthy();

    fireEvent.click(await screen.findByTestId("project-archive-p-9"));
    await waitFor(() => {
      expect(screen.queryByTestId("project-row-p-9")).toBeNull();
    });
    expect(await screen.findByTestId("project-row-p-2")).toBeTruthy();
  });
});

describe("project views", () => {
  it("shows the menu for every named view", async () => {
    for (const view of PROJECT_VIEWS) {
      const client = fixtureClient();
      const shown = render(
        <ApiClientProvider client={client}>
          <ProjectView
            projectId="p-9"
            view={view as ProjectViewName}
            decisionId="d-9"
          />
        </ApiClientProvider>,
      );
      expect(await screen.findByTestId(projectMenuTestId(view))).toBeTruthy();
      shown.unmount();
      cleanup();
    }
  });

  it("traces overview numbers to fixture record rows", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="overview" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("overview-wall-total")).textContent).toContain("90");
    expect((await screen.findByTestId("overview-agents-total")).textContent).toContain("3");
    expect((await screen.findByTestId("overview-task-count")).textContent).toContain("2");
    expect((await screen.findByTestId("overview-package-count")).textContent).toContain("1");
    expect((await screen.findByTestId("overview-budget-spent")).textContent).toContain("10");
    expect((await screen.findByTestId("overview-budget-remaining")).textContent).toContain("85");
    expect((await screen.findByTestId("overview-name")).textContent).toContain("n-9");
    expect((await screen.findByTestId("overview-age-days")).textContent).toContain(
      String(computeAgeDays(CREATED_AT, Date.now())),
    );
  });

  it("shows WHY_THIS_MODEL from the stored snapshot", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView
          projectId="p-9"
          view="routing-decisions"
          decisionId="d-9"
        />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("why-this-model")).toBeTruthy();
    expect((await screen.findByTestId("why-this-model-reason")).textContent).toBe(
      "stored reason nine",
    );
  });

  it("labels derived report lines and keeps measured rows", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="reports" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("project-report-derived")).textContent).toContain(
      en.projects.derived.label,
    );
    expect((await screen.findByTestId("project-report-export")).textContent).toContain(
      "pkg-9",
    );
    expect((await screen.findByTestId("project-report-export")).textContent).toContain(
      "agent-si-report/1",
    );
  });

  it("renders runs, time, cost, models and placement views from records", async () => {
    const client = fixtureClient();
    const shown = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="runs" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("runhistory-ledger-pkg-9")).toBeTruthy();
    expect((await screen.findByTestId("runhistory-install")).textContent).toContain(
      "pkg-10",
    );
    shown.unmount();
    cleanup();

    const time = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="time" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("time-wall-total")).textContent).toContain("90");
    time.unmount();
    cleanup();

    const cost = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="cost" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("cost-limit")).textContent).toContain("100");
    expect((await screen.findByTestId("cost-remaining")).textContent).toContain("85");
    cost.unmount();
    cleanup();

    const models = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="models" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect((await screen.findByTestId("model-row-0")).textContent).toContain(
      "prov-9/mod-9 manager",
    );
    models.unmount();
    cleanup();

    const local = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="local-ai" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("place-row-n-local")).toBeTruthy();
    expect(screen.queryByTestId("place-row-n-cloud")).toBeNull();
    local.unmount();
    cleanup();

    const cloud = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="cloud-ai" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("place-row-n-cloud")).toBeTruthy();
    expect(screen.queryByTestId("place-row-n-local")).toBeNull();
    cloud.unmount();
    cleanup();
  });

  it("keeps served-data views honest when a view has no records", async () => {
    const client = fixtureClient();
    const shown = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="tokens" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText(en.ui.table.empty)).toBeTruthy();
    shown.unmount();
    cleanup();

    const audits = render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="p-9" view="audits" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByText(en.ui.table.empty)).toBeTruthy();
    audits.unmount();
    cleanup();
  });
});

describe("project errors", () => {
  it("surfaces the stored failure code instead of loading forever", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <ProjectView projectId="no-such" view="errors" decisionId="d-9" />
      </ApiClientProvider>,
    );
    expect(await screen.findByTestId("kit-error-panel")).toBeTruthy();
    expect((await screen.findByTestId("kit-error-code")).textContent).toBe(
      "CONTEXT_MISSING",
    );
  });
});

describe("run history", () => {
  it("renders the ledger with human end reasons plus parts and install cards", async () => {
    const client = fixtureClient();
    render(
      <ApiClientProvider client={client}>
        <RunHistory projectId="p-9" packageId="pkg-9" />
      </ApiClientProvider>,
    );
    const ledger = await screen.findByTestId("runhistory-ledger-pkg-9");
    expect(ledger.textContent).toContain("90");
    expect(ledger.textContent).toContain("3");
    expect(
      (await screen.findByTestId("runhistory-part-n-local")).textContent,
    ).toContain(en.tasks.status.running);
    expect(
      (await screen.findByTestId("runhistory-part-n-cloud")).textContent,
    ).toContain(en.tasks.status.queued);
    expect((await screen.findByTestId("runhistory-install")).textContent).toContain(
      "pkg-10",
    );
  });
});
