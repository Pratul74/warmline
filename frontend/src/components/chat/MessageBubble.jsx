// One chat message. The text is always rendered as plain text by React (never as HTML), so a
// reply or a message containing "<script>" is shown as those characters and cannot run.
// A failed message gets a "Not sent" note and a Retry button.
import { RotateCw } from "lucide-react";
import { formatTime } from "@/utils/formatDate";
import { cn } from "@/utils/cn";

export function MessageBubble({ message, onRetry, retryDisabled }) {
  const mine = message.role === "user";
  return (
    <li className={cn("flex flex-col gap-1", mine ? "items-end" : "items-start")}>
      <p className="sr-only">{mine ? "You said:" : "Assistant said:"}</p>
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed break-words whitespace-pre-wrap sm:max-w-[75%]",
          mine ? "rounded-br-md bg-secondary" : "rounded-bl-md border bg-card",
          message.failed && "border border-dashed border-destructive/60 bg-destructive-soft",
        )}
      >
        {message.text}
      </div>
      {message.failed ? (
        <p className="flex items-center gap-2 text-xs text-destructive">
          Not sent
          <button
            type="button"
            onClick={() => onRetry(message.id)}
            disabled={retryDisabled}
            className="inline-flex cursor-pointer items-center gap-1 rounded font-medium underline underline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RotateCw className="size-3" aria-hidden="true" /> Retry
          </button>
        </p>
      ) : (
        message.at && (
          <time
            className="px-1 text-xs text-muted-foreground"
            dateTime={new Date(message.at).toISOString()}
          >
            {formatTime(message.at)}
          </time>
        )
      )}
    </li>
  );
}
