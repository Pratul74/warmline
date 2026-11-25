// The hosted chat's conversation state, kept apart from the drawing so it can be tested alone.
//
// - messages: [{id, role: "user" | "assistant", text, at (ms), failed}]
// - The conversation token lives in memory only: closing or reloading the page starts a new chat.
// - A message that could not be sent stays in the list marked failed, with a Retry button.
// - 429: wait `retryAfter` seconds (countdown shown) before anything can be sent again.
// - 403/404 in the middle of a chat: the link was disabled or rotated, so the chat is closed.
import { useEffect, useState } from "react";
import { sendChatMessage } from "@/api/publicChat";
import { asApiError } from "@/api/client";

let nextId = 1;

export function useChat(publicId) {
  const [messages, setMessages] = useState([]);
  const [conversationToken, setConversationToken] = useState(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null); // the last send error, shown under the messages
  const [closedStatus, setClosedStatus] = useState(null); // 403 or 404 once the link stopped working
  const [secondsLeft, setSecondsLeft] = useState(0); // rate-limit countdown

  // One tick per second while a countdown runs.
  useEffect(() => {
    if (secondsLeft <= 0) return;
    const timer = setTimeout(() => setSecondsLeft((seconds) => seconds - 1), 1000);
    return () => clearTimeout(timer);
  }, [secondsLeft]);

  const blocked = sending || secondsLeft > 0 || closedStatus !== null;

  async function deliver(id, text) {
    setSending(true);
    setError(null);
    try {
      const result = await sendChatMessage(publicId, text, conversationToken);
      setConversationToken(result.conversation_token);
      setMessages((current) => [
        ...current,
        { id: nextId++, role: "assistant", text: result.reply, at: Date.now(), failed: false },
      ]);
    } catch (caught) {
      const apiError = asApiError(caught);
      setMessages((current) => current.map((m) => (m.id === id ? { ...m, failed: true } : m)));
      if (apiError.status === 403 || apiError.status === 404) {
        setClosedStatus(apiError.status);
      } else {
        if (apiError.status === 429) setSecondsLeft(apiError.retryAfter ?? 10);
        setError(apiError);
      }
    } finally {
      setSending(false);
    }
  }

  // Returns true when the message was accepted for sending (so the input box can be cleared).
  function send(rawText) {
    const text = rawText.trim();
    if (!text || blocked) return false;
    const id = nextId++;
    setMessages((current) => [
      ...current,
      { id, role: "user", text, at: Date.now(), failed: false },
    ]);
    deliver(id, text);
    return true;
  }

  // Sends a failed message again. It moves to the end, so the order on screen is the order
  // the assistant actually received the messages in.
  function retry(id) {
    const message = messages.find((m) => m.id === id);
    if (!message || blocked) return;
    setMessages((current) => [
      ...current.filter((m) => m.id !== id),
      { ...message, failed: false, at: Date.now() },
    ]);
    deliver(id, message.text);
  }

  return { messages, sending, error, closedStatus, secondsLeft, blocked, send, retry };
}
