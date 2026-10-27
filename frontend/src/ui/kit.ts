// Frozen-contract compat shim: the canonical kit components stay in
// frontend/src/ui/Card.tsx and frontend/src/ui/MetricCard.tsx; this module
// only re-exports them (plus their prop types) under the frozen
// frontend/src/ui/kit path.
export { Card } from "./Card";
export { MetricCard } from "./MetricCard";
export type { CardProps, MetricCardProps } from "./iface";
