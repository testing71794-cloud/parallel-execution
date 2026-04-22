import { useCallback, useEffect, useRef } from "react";

type FetchList = () => void | Promise<void>;

/**
 * 1) Load list on first open (replaces "blank until I click something").
 * 2) Re-fetch when the user comes back to the tab (optional, keeps data fresh).
 * Pass a stable `fetchList` (wrap with useCallback) that calls the same API as "Refresh list".
 */
export function useReviewListOnOpen(fetchList: FetchList) {
  const run = useRef(fetchList);
  run.current = fetchList;

  const load = useCallback(() => {
    void run.current();
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") void run.current();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);
}
