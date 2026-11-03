import { useEffect, useState } from "react";
import { formatScreenTime } from "../locale/index";

/** Frozen apps-card payload: stored facts only, never computed values. */
export interface AppsCardData {
  project_id: string;
  service_ids: string[];
  paused: boolean;
  generated_at: string;
}

/** Frozen HTTP surface for the apps card (GET, no session token). */
export const APPS_CARD_ROUTE = "/api/v1/apps/card";

/** Closing prompt rendered under the card facts. */
export const CLOSING_PROMPT =
  "Review the facts above, then close this card to continue.";

/** Fetch the stored apps-card facts verbatim; never computes values. */
export async function fetchAppsCard(projectId: string): Promise<AppsCardData> {
  const response = await fetch(
    `${APPS_CARD_ROUTE}?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!response.ok) {
    throw new Error(`apps card request failed: ${response.status}`);
  }
  const body = await response.json();
  return {
    project_id: body.project_id,
    service_ids: [...body.service_ids],
    paused: body.paused,
    generated_at: body.generated_at,
  };
}

/** Presentational card: renders stored facts plus paused state as received. */
export function AppsCard({ data }: { data: AppsCardData }) {
  return (
    <section data-testid="apps-card">
      <h2 data-testid="apps-card-project">{data.project_id}</h2>
      <p data-testid="apps-card-paused">{data.paused ? "Paused" : "Active"}</p>
      <ul data-testid="apps-card-services">
        {data.service_ids.map((id) => (
          <li key={id}>{id}</li>
        ))}
      </ul>
      <p data-testid="apps-card-generated">{data.generated_at !== "" ? formatScreenTime(data.generated_at) : data.generated_at}</p>
      <p data-testid="apps-card-closing">{CLOSING_PROMPT}</p>
    </section>
  );
}

/** Real page: loads stored facts over fetch, then renders the card. */
export function AppsCardPage({ projectId }: { projectId: string }) {
  const [data, setData] = useState<AppsCardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    fetchAppsCard(projectId).then(
      (card) => {
        if (live) {
          setData(card);
        }
      },
      (err: unknown) => {
        if (live) {
          setError(err instanceof Error ? err.message : "request failed");
        }
      },
    );
    return () => {
      live = false;
    };
  }, [projectId]);
  if (error !== null) {
    return <p data-testid="apps-card-error">{error}</p>;
  }
  if (data === null) {
    return <p data-testid="apps-card-loading">Loading...</p>;
  }
  return <AppsCard data={data} />;
}
