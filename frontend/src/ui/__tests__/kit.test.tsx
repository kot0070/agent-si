/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import type { ReactElement } from "react";
import {
  resetLocaleForTests,
  setLocale,
  t,
} from "../../locale/index";
import en from "../../locale/en.json";
import uk from "../../locale/uk.json";
import { Card, collapsedStorageKey } from "../Card";
import { MetricCard } from "../MetricCard";
import { DataTable } from "../DataTable";
import { EmptyState } from "../EmptyState";
import { ErrorPanel } from "../ErrorPanel";
import { LoadingState } from "../LoadingState";
import { Disclosure } from "../Disclosure";
import { PlainText } from "../PlainText";

type Nested = Record<string, unknown>;

function leafValues(node: Nested, acc: string[] = []): string[] {
  for (const key of Object.keys(node)) {
    const value = node[key];
    if (typeof value === "object" && value !== null) {
      leafValues(value as Nested, acc);
    } else {
      acc.push(value as string);
    }
  }
  return acc;
}

const LOCALE_TEXT = new Set<string>([
  ...leafValues(en as unknown as Nested),
  ...leafValues(uk as unknown as Nested),
]);

function visibleTexts(container: HTMLElement): string[] {
  const walker = container.ownerDocument.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
  );
  const out: string[] = [];
  let node = walker.nextNode();
  while (node) {
    const text = (node.textContent ?? "").trim();
    if (text.length > 0) {
      out.push(text);
    }
    node = walker.nextNode();
  }
  return out;
}

function expectLocaleClean(container: HTMLElement, extra: string[]): void {
  const allowed = new Set<string>([...LOCALE_TEXT, ...extra]);
  const stray = visibleTexts(container).filter((text) => !allowed.has(text));
  expect(stray).toEqual([]);
}

beforeEach(() => {
  resetLocaleForTests();
  setLocale("en");
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  resetLocaleForTests();
  window.localStorage.clear();
});

const TITLE_KEY = "settings.general.title";
const PURPOSE_KEY = "settings.general.purpose";
const TOTAL_KEY = "telemetry.tokens";
const COST_KEY = "telemetry.cost";
const EMPTY_KEY = "empty.generic";
const ERROR_KEY = "errors.generic";
const NEXT_KEY = "firstrun.next";

const PARITY_KEYS = [TITLE_KEY, PURPOSE_KEY, EMPTY_KEY, ERROR_KEY, TOTAL_KEY];

function RememberedCard(props: { cardId: string }): ReactElement {
  const storageKey = collapsedStorageKey(props.cardId);
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem(storageKey) !== "false",
  );
  return (
    <Card
      cardId={props.cardId}
      titleKey={TITLE_KEY}
      collapsed={collapsed}
      onToggle={(expanded) => {
        window.localStorage.setItem(storageKey, String(!expanded));
        setCollapsed(!expanded);
      }}
    >
      <span data-testid="kit-child" />
    </Card>
  );
}

describe("kit collapse plus expand plus remembered state", () => {
  it("collapses, expands, and remembers the choice across remount", async () => {
    const first = render(<RememberedCard cardId="card-remembered" />);
    expect(await screen.findByTestId("kit-collapsed-line")).toBeTruthy();
    fireEvent.click(await screen.findByTestId("kit-toggle-card-remembered"));
    expect(await screen.findByTestId("kit-child")).toBeTruthy();
    expect(
      window.localStorage.getItem(
        collapsedStorageKey("card-remembered"),
      ),
    ).toBe("false");
    first.unmount();
    cleanup();
    render(<RememberedCard cardId="card-remembered" />);
    expect(await screen.findByTestId("kit-child")).toBeTruthy();
  });

  it("metric card switches between summary line and bar plus legend plus list", async () => {
    const segments = [
      { segmentKey: TOTAL_KEY, fraction: 0.5 },
      { segmentKey: COST_KEY, fraction: 0.5 },
    ];
    const { rerender } = render(
      <MetricCard
        cardId="card-metric"
        titleKey={TITLE_KEY}
        totalKey={TOTAL_KEY}
        segments={segments}
        collapsed={true}
        onToggle={() => undefined}
      />,
    );
    expect(await screen.findByTestId("kit-collapsed-line")).toBeTruthy();
    rerender(
      <MetricCard
        cardId="card-metric"
        titleKey={TITLE_KEY}
        totalKey={TOTAL_KEY}
        segments={segments}
        collapsed={false}
        onToggle={() => undefined}
      />,
    );
    expect(await screen.findByTestId("kit-expanded-bar")).toBeTruthy();
    expect(await screen.findByTestId("kit-expanded-legend")).toBeTruthy();
    const list = await screen.findByTestId("kit-expanded-list");
    expect(list.childElementCount).toBe(segments.length);
  });

  it("disclosure toggles between summary and detail", async () => {
    render(
      <Disclosure
        disclosureId="disc-1"
        summaryKey={TITLE_KEY}
        expanded={false}
        onToggle={() => undefined}
      >
        <span data-testid="kit-detail" />
      </Disclosure>,
    );
    expect(await screen.findByTestId("kit-collapsed-line")).toBeTruthy();
    expect(screen.queryByTestId("kit-detail")).toBeNull();
  });
});

describe("kit locale parity", () => {
  it("resolves every used key in both frozen locales with differing text", () => {
    for (const key of PARITY_KEYS) {
      setLocale("en");
      const english = t(key);
      setLocale("uk");
      const ukrainian = t(key);
      expect(english.length).toBeGreaterThan(0);
      expect(ukrainian.length).toBeGreaterThan(0);
      expect(ukrainian).not.toBe(english);
    }
  });

  it("renders parity for every component across locales", async () => {
    const segments = [{ segmentKey: TOTAL_KEY, fraction: 1 }];
    const columns = [{ key: "name", headerKey: TITLE_KEY }];
    const rows = [{ name: "row-1" }];
    const renderAll = (): ReactElement => (
      <div>
        <Card cardId="parity-card" titleKey={TITLE_KEY} collapsed={true} onToggle={() => undefined}>
          <span />
        </Card>
        <MetricCard cardId="parity-metric" titleKey={TITLE_KEY} totalKey={TOTAL_KEY} segments={segments} collapsed={false} onToggle={() => undefined} />
        <DataTable cardId="parity-table" titleKey={TITLE_KEY} columns={columns} rows={rows} collapsed={false} onToggle={() => undefined} />
        <EmptyState stateKey={EMPTY_KEY} actionKey={NEXT_KEY} onAction={() => undefined} />
        <ErrorPanel errorKey={ERROR_KEY} code="SCOPE_OVERLAP" onRetry={() => undefined} />
        <LoadingState loadingKey={TITLE_KEY} />
        <Disclosure disclosureId="parity-disc" summaryKey={TITLE_KEY} expanded={true} onToggle={() => undefined}>
          <span />
        </Disclosure>
        <PlainText textKey={PURPOSE_KEY} />
      </div>
    );
    setLocale("en");
    const view = render(renderAll());
    const english = view.container.textContent ?? "";
    expect(english).toContain(en.settings.general.title);
    view.unmount();
    cleanup();
    setLocale("uk");
    const viewUk = render(renderAll());
    const ukrainian = viewUk.container.textContent ?? "";
    expect(ukrainian).toContain(uk.settings.general.title);
    expect(ukrainian).not.toBe(english);
    expect(/[\u0400-\u04FF]/.test(english)).toBe(false);
  });
});

describe("kit literal scan", () => {
  it("renders no hard-coded strings outside locale files", () => {
    const segments = [{ segmentKey: TOTAL_KEY, fraction: 1 }];
    const columns = [{ key: "name", headerKey: TITLE_KEY }];
    const rows = [{ name: "row-1" }];
    const views = [
      render(
        <Card cardId="scan-card" titleKey={TITLE_KEY} collapsed={false} onToggle={() => undefined}>
          <span>row-1</span>
        </Card>,
      ),
      render(
        <MetricCard cardId="scan-metric" titleKey={TITLE_KEY} totalKey={TOTAL_KEY} segments={segments} collapsed={false} onToggle={() => undefined} />,
      ),
      render(
        <DataTable cardId="scan-table" titleKey={TITLE_KEY} columns={columns} rows={rows} collapsed={false} onToggle={() => undefined} />,
      ),
      render(
        <EmptyState stateKey={EMPTY_KEY} actionKey={NEXT_KEY} onAction={() => undefined} />,
      ),
      render(
        <ErrorPanel errorKey={ERROR_KEY} code="SCOPE_OVERLAP" onRetry={() => undefined} />,
      ),
      render(<LoadingState loadingKey={TITLE_KEY} />),
      render(
        <Disclosure disclosureId="scan-disc" summaryKey={TITLE_KEY} expanded={true} onToggle={() => undefined}>
          <span>row-1</span>
        </Disclosure>,
      ),
      render(<PlainText textKey={PURPOSE_KEY} />),
    ];
    for (const view of views) {
      expectLocaleClean(view.container, ["row-1", "SCOPE_OVERLAP"]);
      view.unmount();
    }
  });
});
