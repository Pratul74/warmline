// A grey placeholder block shown while data loads, shaped like the content that will appear,
// so the page does not jump when it arrives. Hidden from screen readers: the page announces
// "Loading…" once instead.
import { cn } from "@/utils/cn";

function Skeleton({ className, ...props }) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export { Skeleton };
