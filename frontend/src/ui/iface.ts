// Lane A frozen UI kit contract. Types plus declare signatures only.

import type { ReactElement, ReactNode } from "react";

export type UiTokenName =
  | "--agent-si-surface"
  | "--agent-si-ink"
  | "--agent-si-accent"
  | "--agent-si-card-border"
  | "--agent-si-chart-a"
  | "--agent-si-chart-b"
  | "--agent-si-chart-c";

export declare const UI_TOKENS: ReadonlyArray<UiTokenName>;

export interface VoidAction {
  (): void;
}

export interface CollapseToggle {
  (expanded: boolean): void;
}

export interface CardProps {
  cardId: string;
  titleKey: string;
  collapsed: boolean;
  onToggle: CollapseToggle;
  children: ReactNode;
}

export interface StackSegment {
  segmentKey: string;
  fraction: number;
}

export interface MetricCardProps {
  cardId: string;
  titleKey: string;
  totalKey: string;
  segments: StackSegment[];
  collapsed: boolean;
  onToggle: CollapseToggle;
}

export interface DataColumn {
  key: string;
  headerKey: string;
}

export interface DataTableProps {
  cardId: string;
  titleKey: string;
  columns: DataColumn[];
  rows: Array<Record<string, string>>;
  collapsed: boolean;
  onToggle: CollapseToggle;
}

export interface EmptyStateProps {
  stateKey: string;
  actionKey: string | null;
  onAction: VoidAction | null;
}

export interface ErrorPanelProps {
  errorKey: string;
  code: string;
  onRetry: VoidAction | null;
}

export interface LoadingStateProps {
  loadingKey: string;
}

export interface DisclosureProps {
  disclosureId: string;
  summaryKey: string;
  expanded: boolean;
  onToggle: CollapseToggle;
  children: ReactNode;
}

export interface PlainTextProps {
  textKey: string;
}

export declare function Card(props: CardProps): ReactElement;

export declare function MetricCard(props: MetricCardProps): ReactElement;

export declare function DataTable(props: DataTableProps): ReactElement;

export declare function EmptyState(props: EmptyStateProps): ReactElement;

export declare function ErrorPanel(props: ErrorPanelProps): ReactElement;

export declare function LoadingState(props: LoadingStateProps): ReactElement;

export declare function Disclosure(props: DisclosureProps): ReactElement;

export declare function PlainText(props: PlainTextProps): ReactElement;

export interface CollapsedStore {
  read(cardId: string): boolean | null;
  write(cardId: string, collapsed: boolean): void;
}

export declare function collapsedStorageKey(cardId: string): string;
