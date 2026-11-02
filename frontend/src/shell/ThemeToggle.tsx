// OC-K07 (DESIGN1 D02/D08): the working theme switch. Labels reuse the
// appearance settings keys (the needItNow copy already promises a dark /
// light switch); the dark/light option values are machine tokens in the
// same class as the en/uk language options, never prose.

import { useState } from "react";
import type { ReactElement } from "react";
import { applyTheme, readTheme } from "./theme";
import type { ThemeName } from "./theme";
import { t } from "../locale/index";

function nextTheme(current: ThemeName): ThemeName {
  return current === "dark" ? "light" : "dark";
}

export function ThemeToggle(): ReactElement {
  const [theme, setTheme] = useState<ThemeName>(readTheme);
  function toggle(): void {
    const next = nextTheme(theme);
    applyTheme(next);
    setTheme(next);
  }
  return (
    <button
      type="button"
      data-testid="theme-toggle"
      data-theme-value={theme}
      title={t("settings.appearance.needItNow")}
      onClick={toggle}
    >
      {t("settings.appearance.title")}:{" "}
    {t(theme === "dark" ? "settings.appearance.dark" : "settings.appearance.light")}
    </button>
  );
}
