// K07NEXT3 B0B-UNCOVERED_MVP_ACCEPT-199: the bench scan browser screen.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { t } from "../locale/index";
import { readBenchScanDoc } from "./k07next3Api";
import type { BenchScanDoc } from "./k07next3Api";

export function BenchScanBrowser(): ReactElement {
  const [doc, setDoc] = useState<BenchScanDoc | null>(null);
  useEffect(() => {
    let alive = true;
    void readBenchScanDoc()
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
  return (
    <section data-testid="k07next3-bench-scan">
      <h2>{t("projects.list.title")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : doc.length === 0 ? (
        <p>{t("projects.list.empty")}</p>
      ) : (
        <ol>
          {doc.map((model) => (
            <li key={model}>{model}</li>
          ))}
        </ol>
      )}
    </section>
  );
}
