// The app's starting point: global error reporting, then the providers every page relies on
// (error page, router, login session, toasts), then the routes.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { ErrorBoundary } from "./components/feedback/ErrorBoundary";
import { Toaster } from "./components/feedback/Toaster";
import { installGlobalErrorHandlers } from "./utils/reportError";
import "./index.css";

installGlobalErrorHandlers();

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <Toaster>
            <App />
          </Toaster>
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);
