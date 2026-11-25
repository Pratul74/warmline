// Catches a crash while React draws the page and shows the error page instead of a blank
// screen. It must be a class: React has no hook for this. It also catches a lazy page whose
// file failed to download (for example after a new deploy), which the error page explains.
import { Component } from "react";
import { reportError } from "@/utils/reportError";
import ErrorPage from "@/pages/ErrorPage";

export class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    reportError(error, { source: "ErrorBoundary", componentStack: info.componentStack });
  }

  render() {
    if (this.state.error) return <ErrorPage />;
    return this.props.children;
  }
}
