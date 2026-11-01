// K07NEXT R-334: the locale switch screen over the real provider.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { setLocale, t } from "../locale/index";
import type { SupportedLocale } from "../locale/index";
import { readLocaleSwitch } from "./k07nextApi";
import type { LocaleSwitchDoc } from "./k07nextApi";

export function LocaleSwitch(): ReactElement {
  const [doc, setDoc] = useState<LocaleSwitchDoc | null>(null);
  const [selected, setSelected] = useState<SupportedLocale>("en");
  useEffect(() => {
    let alive = true;
    void readLocaleSwitch()
      .then((next) => {
        if (alive) {
          setDoc(next);
        }
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);
  function choose(next: SupportedLocale): void {
    setLocale(next);
    setSelected(next);
  }
  return (
    <section data-testid="k07next-locale-switch">
      <h2>{t("settings.general.title")}</h2>
      <p>{t("shell.topbar.language")}</p>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <>
          <p data-testid="k07next-locale-options">{doc.locales.join(",")}</p>
          <p data-testid="k07next-locale-persist">{doc.persisted_via}</p>
          <button type="button" onClick={() => choose("en")}>
            English
          </button>
          <button type="button" onClick={() => choose("uk")}>
            Українська
          </button>
          <p data-testid="k07next-locale-current">{selected}</p>
        </>
      )}
    </section>
  );
}
