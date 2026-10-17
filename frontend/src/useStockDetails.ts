import { useEffect, useState } from "react";
import { fetchOpenDataStockDetails, type OpenDataStockSnapshot } from "./api";

export function useStockDetails(summary: OpenDataStockSnapshot) {
  const [details, setDetails] = useState<OpenDataStockSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setDetails(null);
    setError(null);
    fetchOpenDataStockDetails(summary).then((snapshot) => {
      if (active) setDetails(snapshot);
    }).catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : "Financial history unavailable.");
    });
    return () => { active = false; };
  }, [summary.ticker, summary.generated_at, summary.detail_path, attempt]);
  const current = details?.ticker === summary.ticker && details.generated_at === summary.generated_at ? details : null;
  return { snapshot: current ?? summary, loading: Boolean(summary.detail_path && !current && !error), error, retry: () => setAttempt((value) => value + 1) };
}
