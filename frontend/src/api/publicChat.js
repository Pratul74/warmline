import { apiFetch } from "./client.js";

export const MAX_MESSAGE_LENGTH = 2000;


export function getChatProfile(publicId) {
  return apiFetch(`/public/c/${encodeURIComponent(publicId)}`);
}

export function sendChatMessage(publicId, message, conversationToken) {
  return apiFetch(`/public/c/${encodeURIComponent(publicId)}/messages`, {
    method: "POST",
    body: { message, conversation_token: conversationToken },
  });
}
