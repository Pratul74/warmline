// The Warmline wordmark: a speech bubble with a warm dot (the "warm line" of a reply) and the
// name. Plain SVG, so it is sharp at any size and needs no image download.
import { Link } from "react-router";
import { cn } from "@/utils/cn";

export function LogoMark({ className }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden="true">
      <path
        d="M6 6h20a3 3 0 0 1 3 3v11a3 3 0 0 1-3 3H14l-6 5v-5H6a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3z"
        fill="var(--primary)"
      />
      <path d="M9 13.5h14M9 17h9" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ to = "/", className }) {
  return (
    <Link
      to={to}
      className={cn(
        "inline-flex items-center gap-2 rounded-md font-display text-xl font-semibold",
        className,
      )}
    >
      <LogoMark />
      Warmline
    </Link>
  );
}
