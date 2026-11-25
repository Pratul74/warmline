// Guards owner pages. No token: go to /login and remember where the owner was going.
// Token not yet confirmed by the server: show a loading screen. Confirmed: show the page.
// This is only for a good experience; the real protection is the backend refusing requests
// without a valid token.
import { Navigate, Outlet, useLocation } from "react-router";
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "./AuthContext";

export default function RequireAuth() {
  const { token, account, checkError, retryCheck } = useAuth();
  const location = useLocation();

  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (checkError) {
    return (
      <main className="mx-auto max-w-md px-4 py-24">
        <ErrorMessage error={checkError} onRetry={retryCheck} />
      </main>
    );
  }
  if (!account) {
    return (
      <main className="mx-auto max-w-md space-y-3 px-4 py-24" aria-busy="true">
        <p className="sr-only" role="status">
          Checking your session…
        </p>
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24 w-full" />
      </main>
    );
  }
  return <Outlet />;
}
