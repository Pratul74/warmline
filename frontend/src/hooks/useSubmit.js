// The one way forms and buttons send changes. It blocks double submits, remembers the error
// to show, and tells the caller whether it worked.
//
//   const { submit, submitting, error } = useSubmit((values) => createIntegration(token, values));
//   const { ok, result, error } = await submit(values);
//
// The button uses `submitting` to disable itself and show "Saving…"; `error` is an ApiError
// with the server's message, shown as it is.
import { useRef, useState } from "react";
import { asApiError } from "@/api/client";

export function useSubmit(action) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  // State updates are not instant, so two quick clicks could both see submitting === false.
  // A ref changes immediately and closes that gap.
  const running = useRef(false);

  async function submit(...args) {
    if (running.current) return { ok: false, result: undefined, error: null };
    running.current = true;
    setSubmitting(true);
    setError(null);
    try {
      return { ok: true, result: await action(...args), error: null };
    } catch (caught) {
      const apiError = asApiError(caught);
      setError(apiError);
      return { ok: false, result: undefined, error: apiError };
    } finally {
      running.current = false;
      setSubmitting(false);
    }
  }

  return { submit, submitting, error, clearError: () => setError(null) };
}
