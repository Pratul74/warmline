// The single place where unexpected frontend errors are reported. Today it writes to the
// browser console; an error tracking service can be added here later without touching
// any other file. Expected API errors (wrong password, validation) are not reported.

export function reportError(error, context = {}) {
  console.error("[warmline] unexpected error", { ...context, error });
}

// Catches errors that escape React (event handlers, timers, failed promises nobody awaited).
export function installGlobalErrorHandlers() {
  window.addEventListener("error", (event) => {
    reportError(event.error ?? event.message, { source: "window.error" });
  });
  window.addEventListener("unhandledrejection", (event) => {
    reportError(event.reason, { source: "unhandledrejection" });
  });
}
