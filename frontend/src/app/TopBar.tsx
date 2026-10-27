// Frozen-contract compat shim: the canonical TopBar implementation stays
// in frontend/src/shell/TopBar.tsx; this module only re-exports it (plus
// its prop types and TOPBAR events) under the frozen
// frontend/src/app/TopBar path.
export { TOPBAR_LOCALE_EVENT, TOPBAR_STOP_EVENT, TopBar } from "../shell/TopBar";
export type { TopBarProps } from "./iface";
