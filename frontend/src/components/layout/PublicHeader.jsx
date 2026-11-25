// Top bar of the public pages: logo, and Log in / Get started (or "Open dashboard" when the
// visitor is already logged in).
import { Link } from "react-router";
import { useAuth } from "@/auth/AuthContext";
import { Button } from "@/components/ui/button";
import { Logo } from "./Logo";

export function PublicHeader() {
  const { token } = useAuth();
  return (
    <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
      <Logo />
      <nav aria-label="Account" className="flex items-center gap-2">
        {token ? (
          <Button asChild>
            <Link to="/app/integrations">Open dashboard</Link>
          </Button>
        ) : (
          <>
            <Button variant="ghost" asChild>
              <Link to="/login">Log in</Link>
            </Button>
            <Button asChild>
              <Link to="/register">Get started</Link>
            </Button>
          </>
        )}
      </nav>
    </header>
  );
}
