// FXTABS T3: a run id reads as its first 8 chars with a quiet copy
// affordance; the full id rides the title tooltip, never a 32-hex wall
// as the main text. Short ids render unchanged.
import { useState } from "react";
import type { ReactElement } from "react";
import { humanRunRef } from "./viewsApi";

export function shortRunId(value: string): string {
  if (value.length > 12 && /^[0-9a-f]+$/i.test(value)) {
    return value.slice(0, 8);
  }
  return value;
}

export function RunId(props: { id: string }): ReactElement {
  const [copied, setCopied] = useState(false);
  const ref = humanRunRef(props.id);
  const full = ref.title ?? props.id;
  const shown = shortRunId(ref.text);
  if (shown === ref.text) {
    return (
      <span title={ref.title}>{ref.text}</span>
    );
  }
  async function copy(): Promise<void> {
    try {
      const clipboard = (
        window.navigator as Navigator & {
          clipboard?: { writeText(value: string): Promise<void> };
        }
      ).clipboard;
      if (clipboard !== undefined) {
        await clipboard.writeText(full);
        setCopied(true);
      }
    } catch {
      setCopied(false);
    }
  }
  return (
    <span>
      <span data-testid="run-id-short" title={full}>
        {shown}
      </span>
      <button
        type="button"
        data-testid="run-id-copy"
        className="fxpv-copy"
        title={full}
        aria-label={`Copy run id ${full}`}
        onClick={() => {
          void copy();
        }}
      >
        {copied ? "\u2713" : "\u2398"}
      </button>
    </span>
  );
}
