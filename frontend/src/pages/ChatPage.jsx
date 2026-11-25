// /c/:publicId: the hosted chat a business's customers open from its "Chat" button. Public:
// no login, no owner token. Built phone-first: full height, the message box always at the bottom.
import { useCallback } from "react";
import { useParams } from "react-router";
import { getChatProfile } from "@/api/publicChat";
import { ChatHeader } from "@/components/chat/ChatHeader";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import { ErrorMessage } from "@/components/feedback/ErrorMessage";
import { CenteredMessage } from "@/components/layout/CenteredMessage";
import { Skeleton } from "@/components/ui/skeleton";
import { useApiRequest } from "@/hooks/useApiRequest";
import { useChat } from "@/hooks/useChat";

const LINK_PROBLEMS = {
  404: {
    title: "This chat link doesn't exist",
    text: "The link may be mistyped, or the business may have replaced it with a new one.",
  },
  403: {
    title: "This chat is currently unavailable",
    text: "The business has turned this chat off. Please try again later or contact them another way.",
  },
};

function Footer({ chat }) {
  if (chat.closedStatus) {
    const problem = LINK_PROBLEMS[chat.closedStatus];
    return (
      <div role="alert" className="rounded-md bg-muted p-3 text-sm">
        <strong>{problem.title}</strong>
        <p className="text-muted-foreground">{problem.text}</p>
      </div>
    );
  }
  const waitNote = chat.secondsLeft > 0 ? ` You can send again in ${chat.secondsLeft}s.` : "";
  return (
    <>
      {chat.error && (
        <ErrorMessage
          className="mb-3"
          error={
            chat.error.status === 429
              ? `Too many messages right now.${waitNote}`
              : chat.error.message
          }
        />
      )}
      <ChatInput onSend={chat.send} disabled={chat.blocked} />
    </>
  );
}

export default function ChatPage() {
  const { publicId } = useParams();
  const load = useCallback(() => getChatProfile(publicId), [publicId]);
  const { data: profile, error, reload } = useApiRequest(load);
  const chat = useChat(publicId);

  if (error) {
    const problem = LINK_PROBLEMS[error.status];
    if (problem) {
      return (
        <CenteredMessage title={problem.title}>
          <title>Chat unavailable</title>
          <p>{problem.text}</p>
        </CenteredMessage>
      );
    }
    return (
      <main className="mx-auto max-w-md px-4 py-24">
        <ErrorMessage error={error} onRetry={reload} />
      </main>
    );
  }

  if (!profile) {
    return (
      <main className="flex h-dvh flex-col" aria-busy="true">
        <p role="status" className="sr-only">
          Opening chat…
        </p>
        <div className="flex items-center gap-3 border-b bg-card px-4 py-3">
          <Skeleton className="size-10 rounded-full" />
          <Skeleton className="h-5 w-40" />
        </div>
        <div className="mx-auto w-full max-w-2xl p-4">
          <Skeleton className="h-16 w-3/4 rounded-2xl" />
        </div>
      </main>
    );
  }

  return (
    <div className="flex h-dvh flex-col bg-background">
      <title>{`Chat with ${profile.business_name}`}</title>
      <ChatHeader businessName={profile.business_name} linkName={profile.name} />
      <main className="flex min-h-0 flex-1 flex-col">
        <MessageList
          greeting={profile.greeting || `Hi! How can ${profile.business_name} help you today?`}
          messages={chat.messages}
          sending={chat.sending}
          onRetry={chat.retry}
          retryDisabled={chat.blocked}
        />
        <div className="border-t bg-card px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          <div className="mx-auto max-w-2xl">
            <Footer chat={chat} />
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Powered by Warmline · Replies are written by AI
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
