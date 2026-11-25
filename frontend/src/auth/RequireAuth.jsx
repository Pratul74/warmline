import { Navigate, useLocation } from "react-router";
import ErrorBanner from "../components/ErrorBanner.jsx";
import Spinner from "../components/Spinner.jsx";
import { useAuth } from "./AuthContext.jsx";

export default function RequireAuth({ children }) {
  const { token, account, checkError, retryCheck } = useAuth();
  const location = useLocation();

  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (checkError) {
    return (
      <main className="page-center">
        <ErrorBanner message={checkError.message} onRetry={retryCheck} />
      </main>
    );
  }
  if (!account) {
    return (
      <main className="page-center">
        <Spinner label="Checking your session…" />
      </main>
    );
  }
  return children;
}
