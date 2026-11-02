// K07NEXT4 LIVE0-08: the session token card.
// FXCLASS CD-6: an error state replaces the endless spinner. A 401/403/500
// surfaces an ErrorPanel with Retry, never an infinite spinner with zero
// cause. Reads the real page; only the network edge is substituted in tests.
import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { t } from "../locale/index";
import { ErrorPanel } from "../ui/ErrorPanel";
import { writeSessionTokenDoc } from "./k07next4Api";
import type { SessionWriteDoc } from "./k07next4Api";

export function SessionTokenCard(): ReactElement {
  const [doc, setDoc] = useState<SessionWriteDoc | null>(null);
  const [failure, setFailure] = useState<{
    errorKey: string;
    code: string;
  } | null>(null);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    void writeSessionTokenDoc()
      .then((next) => {
        if (alive) {
          setDoc(next);
          setFailure(null);
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          const code =
            err instanceof ApiError ? err.code : "CONTEXT_MISSING";
          setFailure({ errorKey: apiErrorLocaleKey(code), code });
        }
      });
    return () => {
      alive = false;
    };
  }, [nonce]);
  if (failure !== null) {
    return (
      <section data-testid="k07next4-session-token">
        <h2>{t("chat.composer.send")}</h2>
        <div data-testid="k07next4-session-token-error">
          <ErrorPanel
            errorKey={failure.errorKey}
            code={failure.code}
            onRetry={() => {
              setNonce((value) => value + 1);
            }}
          />
        </div>
      </section>
    );
  }
  return (
    <section data-testid="k07next4-session-token">
      <h2>{t("chat.composer.send")}</h2>
      {doc === null ? (
        <p>{t("chat.stream.spinner")}</p>
      ) : (
        <p>{doc.actor}</p>
      )}
    </section>
  );
}
