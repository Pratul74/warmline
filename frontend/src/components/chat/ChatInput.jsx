// The message box. Enter sends, Shift+Enter adds a new line (and Enter while an input method
// is still composing a character, e.g. Japanese, does not send). A counter appears near the
// 2000-character limit.
import { SendHorizontal } from "lucide-react";
import { useState } from "react";
import { MAX_MESSAGE_LENGTH } from "@/api/publicChat";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function ChatInput({ onSend, disabled }) {
  const [draft, setDraft] = useState("");

  function submit(event) {
    event.preventDefault();
    if (onSend(draft)) setDraft("");
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  }

  const nearLimit = draft.length > MAX_MESSAGE_LENGTH - 200;
  return (
    <form onSubmit={submit} className="flex items-end gap-2">
      <div className="flex-1">
        <Textarea
          rows={1}
          maxLength={MAX_MESSAGE_LENGTH}
          placeholder="Type your message…"
          aria-label="Message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          className="max-h-40 min-h-11 resize-none py-2.5"
        />
        {nearLimit && (
          <p className="mt-1 text-right text-xs text-muted-foreground">
            {draft.length} / {MAX_MESSAGE_LENGTH}
          </p>
        )}
      </div>
      <Button
        type="submit"
        size="icon"
        className="size-11 rounded-full"
        disabled={disabled || !draft.trim()}
      >
        <SendHorizontal aria-hidden="true" />
        <span className="sr-only">Send</span>
      </Button>
    </form>
  );
}
