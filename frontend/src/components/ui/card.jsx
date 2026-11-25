// Card (from shadcn/ui, adapted): a white panel with a border on the paper background.
import { cn } from "@/utils/cn";

// `as` changes the element, e.g. as="li" when cards form a list.
function Card({ className, as: Element = "div", ...props }) {
  return (
    <Element
      data-slot="card"
      className={cn(
        "flex flex-col gap-4 rounded-lg border bg-card p-5 text-card-foreground shadow-card",
        className,
      )}
      {...props}
    />
  );
}

function CardHeader({ className, ...props }) {
  return (
    <div data-slot="card-header" className={cn("flex flex-col gap-1", className)} {...props} />
  );
}

// A real heading (h2 by default) so screen-reader users can jump between cards.
function CardTitle({ className, as: Heading = "h2", ...props }) {
  return (
    <Heading
      data-slot="card-title"
      className={cn("text-lg leading-snug font-semibold", className)}
      {...props}
    />
  );
}

function CardDescription({ className, ...props }) {
  return (
    <p
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

export { Card, CardDescription, CardHeader, CardTitle };
