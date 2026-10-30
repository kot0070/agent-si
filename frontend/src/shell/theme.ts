// OC-K07 (DESIGN1 D02): explicit theme state for the K07 shell. The page
// exposes exactly one theme at a time through documentElement data-theme
// (dark default, matching the :root token set); the choice persists in
// localStorage and the toggle in the top bar plus the appearance settings
// section is the only writer.

export const THEME_STORAGE_KEY = "agentsi.theme";

export type ThemeName = "dark" | "light";

export const THEME_NAMES: readonly ThemeName[] = ["dark", "light"];

export function readTheme(): ThemeName {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === "dark" || raw === "light") {
      return raw;
    }
  } catch {
    // Storage unavailable: fall through to the default.
  }
  return "dark";
}

export function applyTheme(theme: ThemeName): void {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage unavailable: the attribute still re-renders the page.
  }
}
