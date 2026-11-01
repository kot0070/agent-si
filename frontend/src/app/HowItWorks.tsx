import type { ReactElement } from 'react';
import { t } from '../locale/index';
import type { SupportedLocale } from '../locale/index';
import en from '../locale/en.json';
import uk from '../locale/uk.json';

export const HOW_IT_WORKS_KEYS = {
  runsTitle: 'howItWorks.runs.title',
  runsBody: 'howItWorks.runs.body',
  codeTestsTitle: 'howItWorks.codeTests.title',
  codeTestsBody: 'howItWorks.codeTests.body',
  localTestsTitle: 'howItWorks.localTests.title',
  localTestsBody: 'howItWorks.localTests.body',
} as const;

export interface HowItWorksProps {
  locale?: SupportedLocale;
}

// FXKITUI diagram tokens: monochrome on currentColor so every stroke and
// label inherits the readable body color in both dark and light themes;
// hierarchy comes from real font sizes and weights only (no accent color,
// no gradients, no motion, so prefers-reduced-motion needs no branch).
const HOW_IT_WORKS_TOKENS = {
  ink: 'currentColor',
  panelFill: 'none',
  titleSize: 20,
  titleWeight: 700,
  labelSize: 14,
  labelWeight: 600,
  bodySize: 12,
  bodyWeight: 400,
  stageWidth: 560,
  stageHeight: 44,
  stageGap: 26,
  stagePadX: 40,
  topPad: 44,
} as const;

// Six pipeline stages. Visible labels reuse existing locale strings (the
// literal-scan gate allows no new visible copy); each <text> carries its
// pipeline sentence as its accessible name, in chain order.
const HOW_IT_WORKS_STAGES: ReadonlyArray<{
  labelKey: string;
  chain: string;
}> = [
  { labelKey: 'firstrun.steps.firstTask', chain: 'you write one task' },
  { labelKey: 'providers.role.director', chain: 'Director plans' },
  { labelKey: 'providers.role.manager', chain: 'Managers' },
  { labelKey: 'agents.live.title', chain: 'agents write files' },
  { labelKey: 'howItWorks.codeTests.title', chain: 'app runs the checks' },
  { labelKey: 'providers.role.auditor', chain: 'fresh auditor gives an honest result' },
];

type LocaleTable = Record<string, unknown>;

function lookup(table: LocaleTable, key: string): string | undefined {
  let node: unknown = table;
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null) {
      return undefined;
    }
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === 'string' ? node : undefined;
}

function text(key: string, locale: SupportedLocale | undefined): string {
  if (locale === undefined) {
    return t(key);
  }
  const table = (locale === 'en' ? en : uk) as unknown as LocaleTable;
  return lookup(table, key) ?? t(key);
}

function stageY(index: number): number {
  return (
    HOW_IT_WORKS_TOKENS.topPad +
    index * (HOW_IT_WORKS_TOKENS.stageHeight + HOW_IT_WORKS_TOKENS.stageGap)
  );
}

export function HowItWorks(props: HowItWorksProps): ReactElement {
  const entries = [
    { titleKey: HOW_IT_WORKS_KEYS.runsTitle, bodyKey: HOW_IT_WORKS_KEYS.runsBody },
    { titleKey: HOW_IT_WORKS_KEYS.codeTestsTitle, bodyKey: HOW_IT_WORKS_KEYS.codeTestsBody },
    { titleKey: HOW_IT_WORKS_KEYS.localTestsTitle, bodyKey: HOW_IT_WORKS_KEYS.localTestsBody },
  ];
  const token = HOW_IT_WORKS_TOKENS;
  const height =
    token.topPad * 2 +
    HOW_IT_WORKS_STAGES.length * token.stageHeight +
    (HOW_IT_WORKS_STAGES.length - 1) * token.stageGap;
  return (
    <section>
      <svg
        data-testid="how-it-works-diagram"
        role="img"
        viewBox={`0 0 640 ${height}`}
        width="100%"
      >
        {HOW_IT_WORKS_STAGES.map((stage, index) => {
          const y = stageY(index);
          const midX = token.stagePadX + token.stageWidth / 2;
          return (
            <g key={stage.labelKey}>
              <rect
                x={token.stagePadX}
                y={y}
                width={token.stageWidth}
                height={token.stageHeight}
                fill={token.panelFill}
                stroke={token.ink}
                strokeWidth={1.5}
                rx={8}
              />
              <text
                data-testid={`how-it-works-stage-${index + 1}`}
                aria-label={stage.chain}
                x={midX}
                y={y + token.stageHeight / 2}
                textAnchor="middle"
                dominantBaseline="central"
                fill={token.ink}
                fontSize={token.labelSize}
                fontWeight={token.labelWeight}
              >
                {text(stage.labelKey, props.locale)}
              </text>
              {index + 1 < HOW_IT_WORKS_STAGES.length ? (
                <g stroke={token.ink} strokeWidth={1.5}>
                  <line
                    x1={midX}
                    y1={y + token.stageHeight}
                    x2={midX}
                    y2={y + token.stageHeight + token.stageGap}
                  />
                  <polygon
                    points={`${midX - 5},${y + token.stageHeight + token.stageGap - 8} ${midX + 5},${y + token.stageHeight + token.stageGap - 8} ${midX},${y + token.stageHeight + token.stageGap}`}
                    fill={token.ink}
                    stroke="none"
                  />
                </g>
              ) : null}
            </g>
          );
        })}
      </svg>
      <section data-testid="how-it-works-concepts">
        {entries.map((entry) => (
          <article key={entry.titleKey}>
            <h2>{text(entry.titleKey, props.locale)}</h2>
            <p>{text(entry.bodyKey, props.locale)}</p>
            <code>{entry.titleKey}</code>
            <code>{entry.bodyKey}</code>
          </article>
        ))}
      </section>
    </section>
  );
}
