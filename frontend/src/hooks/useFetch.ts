import { useEffect, useState, useCallback } from "react";

interface FetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

// The one data-fetching primitive the app needs: local state + fetch, no
// query-library dependency (nothing here needs caching, retries, or
// background refetch across screens). Re-run whenever `deps` changes, and
// guard against a stale response landing after a newer request started --
// the same "drop it if the selection moved on" rule mockups/api.js applies
// to /explain (see renderExplain there).
export function useFetch<T>(fn: () => Promise<T>, deps: readonly unknown[]): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fn()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return { data, loading, error, reload };
}
