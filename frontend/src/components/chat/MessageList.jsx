// The conversation. role="log" tells screen readers that new messages are added at the end
// and should be read out as they arrive. The newest message is scrolled into view.
import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";

export function MessageList({ greeting, messages, sending, onRetry, retryDisabled }) {
  const endRef = useRef(null);

  useEffect(() => {
    // scrollIntoView is missing in some test environments, hence the "?.".
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, sending]);

  return (
    // role="log" sits on the wrapper: on the <ol> it would replace the list role, and screen
    // readers would then no longer announce the messages as a list.
    <div role="log" aria-label="Conversation" className="flex-1 overflow-y-auto px-4 py-6">
      <ol className="mx-auto flex max-w-2xl flex-col gap-4">
        {/* The greeting is only shown on screen; the assistant never receives it. */}
        <MessageBubble message={{ id: "greeting", role: "assistant", text: greeting }} />
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onRetry={onRetry}
            retryDisabled={retryDisabled}
          />
        ))}
        {sending && <TypingIndicator />}
      </ol>
      <div ref={endRef} />
    </div>
  );
}
