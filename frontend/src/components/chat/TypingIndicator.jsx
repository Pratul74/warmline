// Three dots while the assistant prepares a reply. The dots are decoration; screen readers
// get the words "Assistant is typing".
export function TypingIndicator() {
  return (
    <li className="flex items-start">
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-md border bg-card px-4 py-3.5">
        <span className="sr-only">Assistant is typing…</span>
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            aria-hidden="true"
            className="size-1.5 animate-pulse rounded-full bg-muted-foreground"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
      </div>
    </li>
  );
}
