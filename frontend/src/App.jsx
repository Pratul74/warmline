// The route table: every URL of the app in one place. Each page is loaded on demand
// (React.lazy), so a chat visitor downloads the chat page's code and not the dashboard's.
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";
import RequireAuth from "@/auth/RequireAuth";

// The owner area's frame (sidebar, account menu) is only downloaded by logged-in owners.
const AppShell = lazy(() =>
  import("@/components/layout/AppShell").then((module) => ({ default: module.AppShell })),
);
const LandingPage = lazy(() => import("@/pages/LandingPage"));
const LoginPage = lazy(() => import("@/pages/LoginPage"));
const RegisterPage = lazy(() => import("@/pages/RegisterPage"));
const IntegrationsPage = lazy(() => import("@/pages/IntegrationsPage"));
const FaqPage = lazy(() => import("@/pages/FaqPage"));
const ChatPage = lazy(() => import("@/pages/ChatPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

// While a page's code downloads: an empty screen with a status for screen readers. It is
// usually too quick to see, so a spinner would only flicker.
function PageLoading() {
  return (
    <p role="status" className="sr-only">
      Loading…
    </p>
  );
}

export default function App() {
  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/c/:publicId" element={<ChatPage />} />

        <Route element={<RequireAuth />}>
          <Route path="/app" element={<AppShell />}>
            <Route index element={<Navigate to="integrations" replace />} />
            <Route path="integrations" element={<IntegrationsPage />} />
            <Route path="faq" element={<FaqPage />} />
          </Route>
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
