// Frozen-contract compat shim: the canonical Sidebar implementation stays
// in frontend/src/shell/Sidebar.tsx; this module only re-exports it (plus
// its prop types) under the frozen frontend/src/app/Sidebar path.
export { Sidebar } from "../shell/Sidebar";
export type { SidebarProps } from "./iface";
