// The one way pages load data. Give it a function that returns a promise (wrapped in
// useCallback, so it only changes when its inputs change) and it runs it, keeps the result,
// and tells the page what to show.
//
//   const loadEntries = useCallback(() => listFaqEntries(token, page, 10), [token, page]);
//   const { data, error, loading, reload, setData } = useApiRequest(loadEntries);
//
// - loading: true until the current request has answered (show a skeleton).
// - data:    the last successful result. While a new page loads it still holds the old one,
//            so tables don't flash empty between pages.
// - error:   an ApiError from the current request, or null (show it with a Retry button).
// - reload:  runs the request again (the Retry button).
// - setData: changes the kept result after a local change, e.g. a new item was created.
import { useEffect, useState } from "react";
import { asApiError } from "@/api/client";

export function useApiRequest(load) {
  const [attempt, setAttempt] = useState(0);
  // The answer is stored together with the request it belongs to. "loading" is then simply
  // "the stored answer is for an older request", which avoids resetting state inside the
  // effect and never shows an old error for a new request.
  const [answer, setAnswer] = useState({ load: null, attempt: -1, data: undefined, error: null });

  useEffect(() => {
    let cancelled = false; // ignore answers that arrive after the page moved on
    load().then(
      (data) => {
        if (!cancelled) setAnswer({ load, attempt, data, error: null });
      },
      (error) => {
        if (!cancelled) {
          setAnswer((previous) => ({
            load,
            attempt,
            data: previous.data,
            error: asApiError(error),
          }));
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load, attempt]);

  const isCurrent = answer.load === load && answer.attempt === attempt;
  return {
    data: answer.data,
    error: isCurrent ? answer.error : null,
    loading: !isCurrent,
    reload: () => setAttempt((count) => count + 1),
    setData: (change) => setAnswer((previous) => ({ ...previous, data: change(previous.data) })),
  };
}
