// Top of the chat: the business's initials, its name, and a clear "AI assistant" label so
// customers know they are not talking to a person.
import { initialsOf } from "@/utils/initials";

export function ChatHeader({ businessName, linkName }) {
  return (
    <header className="flex items-center gap-3 border-b bg-card px-4 py-3">
      <span
        className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
        aria-hidden="true"
      >
        {initialsOf(businessName)}
      </span>
      <div className="min-w-0">
        <h1 className="truncate font-display text-lg leading-tight font-semibold">
          {businessName}
        </h1>
        <p className="truncate text-xs text-muted-foreground">
          AI assistant <span aria-hidden="true">·</span> {linkName}
        </p>
      </div>
    </header>
  );
}
