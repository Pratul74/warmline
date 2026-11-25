// Footer of the public pages. No fake company links: only what exists.
import { Link } from "react-router";
import { LogoMark } from "./Logo";

export function Footer() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p className="flex items-center gap-2">
          <LogoMark className="size-5" /> Warmline
        </p>
        <nav aria-label="Footer" className="flex gap-5">
          <Link to="/login" className="hover:text-foreground">
            Log in
          </Link>
          <Link to="/register" className="hover:text-foreground">
            Create an account
          </Link>
        </nav>
      </div>
    </footer>
  );
}
