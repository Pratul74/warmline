// The hosted chat's public API. No owner token is ever sent from the chat page: the link's
// public_id is the only context, and the backend finds the business from it.
import { apiFetch } from "./client";

// Same limit as MAX_MESSAGE_CHARS in app/api/schemas.py.
export const MAX_MESSAGE_LENGTH = 2000;

// Returns {name, greeting (or null), business_name}. 404 = unknown link, 403 = disabled.
export function getChatProfile(publicId) {
  return apiFetch(`/public/c/${encodeURIComponent(publicId)}`);
}

// conversationToken is null for the first message; the reply carries the token for the next
// ones. Returns {conversation_token, reply}. 429 = too many messages (see retryAfter).
export function sendChatMessage(publicId, message, conversationToken) {
  return apiFetch(`/public/c/${encodeURIComponent(publicId)}/messages`, {
    method: "POST",
    body: { message, conversation_token: conversationToken },
  });
}
