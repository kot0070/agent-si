// FXLOOK D1+D7: one shared single-row project tab strip (data views).
// One row always: nowrap + horizontal scroll, tabs never shrink, labels
// never wrap. `‹` `›` appear only while overflow exists in that
// direction (measured on scroll + resize), each scrolls 160px; a soft
// fade marks the clipped edge. ArrowLeft/Right/Home/End move focus;
// the selected tab scrolls into view (block-nearest inline-nearest).
// The Chat tab is a real tab (same look, D7): first, selected with
// fxpv-tab-selected + aria-current when the chat view is active.

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactElement } from "react";
import { t } from "../locale/index";
import {
  PROJECT_VIEWS,
  projectMenuTestId,
  projectViewTitleKey,
} from "./projectsApi";
import type { ProjectViewName } from "./projectsApi";

export type ProjectTabsSelection = ProjectViewName | "chat";

export interface ProjectTabsNavProps {
  selected: ProjectTabsSelection;
  onSelect: (view: ProjectViewName | "chat") => void;
}

export const TABS_SCROLL_STEP = 160;

export function ProjectTabsNav(props: ProjectTabsNavProps): ReactElement {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const selectedRef = useRef<HTMLButtonElement | null>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  function measure(): void {
    const el = scrollRef.current;
    if (el === null) {
      return;
    }
    setCanLeft(el.scrollLeft > 0);
    setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("resize", measure);
    };
  }, []);

  // FXLOOK D1: the selected tab scrolls into view on selection change.
  useEffect(() => {
    const el = selectedRef.current;
    if (el !== null && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [props.selected]);

  function scrollStep(direction: 1 | -1): void {
    const el = scrollRef.current;
    if (el === null) {
      return;
    }
    if (typeof el.scrollBy === "function") {
      el.scrollBy({ left: direction * TABS_SCROLL_STEP });
    } else {
      el.scrollLeft += direction * TABS_SCROLL_STEP;
    }
  }

  function moveFocus(event: KeyboardEvent<HTMLDivElement>): void {
    if (
      event.key !== "ArrowLeft" &&
      event.key !== "ArrowRight" &&
      event.key !== "Home" &&
      event.key !== "End"
    ) {
      return;
    }
    const el = scrollRef.current;
    if (el === null) {
      return;
    }
    const tabs = Array.from(
      el.querySelectorAll<HTMLButtonElement>("button.fxpv-tab"),
    );
    if (tabs.length === 0) {
      return;
    }
    const active = document.activeElement as HTMLButtonElement | null;
    const at = active === null ? -1 : tabs.indexOf(active);
    event.preventDefault();
    let next = at;
    if (event.key === "ArrowRight") {
      next = at < 0 ? 0 : Math.min(tabs.length - 1, at + 1);
    } else if (event.key === "ArrowLeft") {
      next = at < 0 ? tabs.length - 1 : Math.max(0, at - 1);
    } else if (event.key === "Home") {
      next = 0;
    } else {
      next = tabs.length - 1;
    }
    tabs[next]?.focus();
  }

  function select(name: ProjectTabsSelection): void {
    props.onSelect(name);
  }

  function tabClass(name: ProjectTabsSelection): string {
    return props.selected === name
      ? "fxpv-tab fxpv-tab-selected"
      : "fxpv-tab";
  }

  const wrapClass =
    "fxpv-tabs-wrap" +
    (canLeft ? " fxpv-clip-left" : "") +
    (canRight ? " fxpv-clip-right" : "");

  return (
    <div data-testid="project-tabs" className={wrapClass}>
      {canLeft ? (
        <button
          type="button"
          data-testid="project-tabs-prev"
          className="fxpv-tabs-arrow"
          aria-label={t("projectView.tabs.scrollPrev")}
          title={t("projectView.tabs.scrollPrev")}
          onClick={() => {
            scrollStep(-1);
          }}
        >
          {"\u2039"}
        </button>
      ) : null}
      <div
        ref={scrollRef}
        className="fxpv-tabs-scroll"
        onScroll={measure}
        onKeyDown={moveFocus}
      >
        <nav aria-label={t("projectView.tabsLabel")} className="fxpv-tabs">
          <button
            type="button"
            ref={props.selected === "chat" ? selectedRef : undefined}
            data-testid="project-chat-tab"
            className={tabClass("chat")}
            aria-selected={props.selected === "chat" ? "true" : "false"}
            aria-current={props.selected === "chat" ? "true" : undefined}
            onClick={() => {
              select("chat");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                select("chat");
              }
            }}
          >
            {t("shell.sidebar.chat")}
          </button>
          {PROJECT_VIEWS.map((name) => (
            <button
              key={name}
              type="button"
              ref={props.selected === name ? selectedRef : undefined}
              data-testid={projectMenuTestId(name)}
              aria-current={props.selected === name ? "true" : undefined}
              aria-selected={props.selected === name ? "true" : "false"}
              className={tabClass(name)}
              onClick={() => {
                select(name);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  select(name);
                }
              }}
            >
              {t(projectViewTitleKey(name))}
            </button>
          ))}
        </nav>
      </div>
      {canRight ? (
        <button
          type="button"
          data-testid="project-tabs-next"
          className="fxpv-tabs-arrow"
          aria-label={t("projectView.tabs.scrollNext")}
          title={t("projectView.tabs.scrollNext")}
          onClick={() => {
            scrollStep(1);
          }}
        >
          {"\u203A"}
        </button>
      ) : null}
    </div>
  );
}
