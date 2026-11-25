// An error box for a failed request: the server's message, plus a "Try again" button when the
// caller passes onRetry. role="alert" makes screen readers read it out as soon as it appears.
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/utils/cn";

export function ErrorMessage({ error, onRetry, className }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : error.message;
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-md border border-destructive/25 bg-destructive-soft p-3 text-sm text-destructive",
        className,
      )}
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <p className="flex-1">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="text-foreground">
          Try again
        </Button>
      )}
    </div>
  );
}
