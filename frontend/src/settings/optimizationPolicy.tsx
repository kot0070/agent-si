// ARCH-528: the AI SETTINGS Optimization Policy view presents the
// required quality, the risk ceiling and the weights from the served
// optimization policy (kit BUILD_PLAN.md:1594).

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { t } from "../locale/index";
import {
  readOptimizationPolicy,
  type OptimizationPolicy,
} from "./optimizationPolicyApi";

function errorKeyOf(error: unknown): string {
  if (error instanceof ApiError) {
    return apiErrorLocaleKey(error.code);
  }
  return "errors.generic";
}

export function OptimizationPolicySection(): ReactElement {
  const [policy, setPolicy] = useState<OptimizationPolicy | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void readOptimizationPolicy().then(
      (loaded) => {
        if (!alive) {
          return;
        }
        setPolicy(loaded);
        setErrorKey(null);
      },
      (error: unknown) => {
        if (!alive) {
          return;
        }
        setErrorKey(errorKeyOf(error));
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  if (errorKey !== null) {
    return (
      <section data-testid="optimization-policy-section">
        <h2>{t("settings.optimization.title")}</h2>
        <div data-testid="optimization-policy-error">
          <span>{t(errorKey)}</span>
        </div>
      </section>
    );
  }

  if (policy === null) {
    return (
      <section data-testid="optimization-policy-section">
        <h2>{t("settings.optimization.title")}</h2>
        <p>{t("ui.loading.more")}</p>
      </section>
    );
  }

  return (
    <section data-testid="optimization-policy-section">
      <h2>{t("settings.optimization.title")}</h2>
      <p>{t("settings.optimization.purpose")}</p>
      <dl>
        <dt>{t("settings.optimization.requiredQuality")}</dt>
        <dd data-testid="optimization-policy-quality">
          {String(policy.required_quality)}
        </dd>
        <dt>{t("settings.optimization.riskCeiling")}</dt>
        <dd data-testid="optimization-policy-risk">{policy.max_risk}</dd>
        <dt>{t("settings.optimization.weights")}</dt>
        <dd data-testid="optimization-policy-weights">
          {`quality ${String(policy.weights.weight_quality)} · cost ${String(policy.weights.weight_cost)} · latency ${String(policy.weights.weight_latency)} · cloud ${String(policy.weights.weight_cloud_tokens)}`}
        </dd>
      </dl>
    </section>
  );
}
